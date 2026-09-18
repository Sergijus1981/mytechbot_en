import os
import pickle
import zipfile
import gdown
import requests
import numpy as np
import faiss
import sqlite3
import shutil
import subprocess
import io
import datetime as dt
import json
import time
import re
from datetime import timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, filters, CallbackQueryHandler, CommandHandler
from PIL import Image
import torch
from torchvision import transforms
from ultralytics import YOLO
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image as RLImage, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics, ttfonts
from reportlab.lib.fonts import addMapping

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

PHOTO_DB_URL = "https://github.com/Sergijus1981/mytechbot/releases/download/v1.0.0/photo_db.zip"
ETALONS_URL = "https://github.com/Sergijus1981/mytechbot/releases/download/v1.0.0/etalons.zip"

INDEX_PATH = "faiss_index.bin"
PATHS_PATH = "image_paths.pkl"
MODEL_PATH = "best.pt"
OWNER_ID = 8743362338

FREE_CHECKS_LIMIT = 5
USDT_WALLET = "TZ4bfpNTvMdMNRzQJt817pVjF3nEGtCKSH"
USDT_CONTRACT = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"
TRONGRID_API = "https://api.trongrid.io/v1/accounts/{address}/transactions/trc20"

def db_path():
    return "/data/users.db" if os.path.exists("/data") else "users.db"

# ========== ПЛАТЕЖИ ==========
def get_recent_transactions(limit=20):
    try:
        url = TRONGRID_API.format(address=USDT_WALLET)
        params = {"limit": limit, "only_confirmed": "true", "contract_address": USDT_CONTRACT, "only_to": "true"}
        r = requests.get(url, params=params, timeout=10)
        if r.status_code == 200:
            return r.json().get("data", [])
    except Exception as e:
        print(f"TronGrid error: {e}")
    return []

def check_payment(txid, expected_amount, user_id):
    txid = txid.strip().lower()
    if not txid.startswith("0x"):
        txid = "0x" + txid
    try:
        url = f"https://api.trongrid.io/v1/transactions/{txid}/events"
        r = requests.get(url, timeout=10)
        if r.status_code != 200:
            return None
        events = r.json().get("data", [])
        for ev in events:
            if ev.get("event_name") != "Transfer":
                continue
            result = ev.get("result", {})
            if result.get("to") != USDT_WALLET:
                continue
            if result.get("contract_address") != USDT_CONTRACT:
                continue
            raw_amount = int(result.get("value", 0))
            amount = raw_amount / 1_000_000
            if amount >= expected_amount - 0.01:
                return amount
    except Exception as e:
        print(f"Tx check error: {e}")
    return None

def check_payment_by_user(user_id, expected_amount, since_minutes=180):
    txs = get_recent_transactions()
    now = time.time() * 1000
    since = now - (since_minutes * 60 * 1000)
    for tx in txs:
        ts = int(tx.get("block_timestamp", 0))
        if ts < since:
            continue
        to_addr = tx.get("to", "")
        if to_addr != USDT_WALLET:
            continue
        if tx.get("token_info", {}).get("address") != USDT_CONTRACT:
            continue
        raw = int(tx.get("value", 0))
        amount = raw / 1_000_000
        if abs(amount - expected_amount) < 0.01:
            return tx.get("transaction_id"), amount
    return None, 0

def get_unique_amount(user_id, base=10):
    conn = sqlite3.connect(db_path())
    c = conn.cursor()
    r = c.execute("SELECT amount FROM pending_payments WHERE user_id = ?", (user_id,)).fetchone()
    if r:
        conn.close()
        return r[0]
    amount = base + (user_id % 99) / 100
    c.execute("INSERT OR REPLACE INTO pending_payments (user_id, amount, created_at) VALUES (?, ?, ?)",
              (user_id, amount, dt.datetime.now().isoformat()))
    conn.commit()
    conn.close()
    return amount

def clear_pending(user_id):
    conn = sqlite3.connect(db_path())
    c = conn.cursor()
    c.execute("DELETE FROM pending_payments WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

# ========== ЯЗЫКИ ==========
T = {
    "en": {
        "welcome": "Hello! 👋\nI'm a technical inspection bot. Send me a photo of electrical installation, and I'll find possible violations.\n\nJust send a photo!",
        "choose_language": "🌐 Choose your language:",
        "defects_list": "🔍 Found defects:",
        "standard": "📜 Standard:",
        "no_match": "❌ No similar examples found.",
        "report_ready": "📄 Your order is ready!",
        "no_defects": "📭 No defects recorded.",
        "report_action": "🛠 Recommended action: bring into compliance with standards.",
        "generate_order": "📄 Generate order",
        "order_title": "ORDER",
        "issue_date": "Issue date:",
        "defect": "Defect",
        "standard_label": "Standard:",
        "deadline": "Remediation deadline: _______________",
        "issued_by": "ISSUED BY:",
        "company": "Company: ___________________",
        "position": "Position: _________________",
        "full_name": "Full name: _______________________",
        "signature": "Signature: ___________________",
        "received_by": "RECEIVED BY:",
        "violation_photo": "Violation photo",
        "free_checks_left": "✅ You have {count} free checks left.",
        "free_checks_used": "⚠️ Free checks used up.",
        "buy_button": "💳 Buy checks",
        "buy_text": "You've used all 5 free checks.\n\nOptions:\n• 10 checks — $10 (10 USDT)\n• Unlimited (1 month) — $20 (20 USDT)\n\nSend EXACTLY {amount} USDT (TRC20) to:\n`{wallet}`\n\nAfter payment, press the button below.",
        "pay_sent": "✅ I've sent payment",
        "pay_check": "🔍 Checking payment...",
        "pay_success": "✅ Payment confirmed! {count} checks added to your account.",
        "pay_fail": "❌ Payment not found. Make sure you sent EXACTLY {amount} USDT TRC20 to the correct address.\n\nSend the transaction hash (TXID) here if you have it.",
        "pay_txid_prompt": "📋 Please send the TXID (transaction hash) or just the TXID text.",
        "balance_text": "Free checks left: {free}\nPaid checks left: {paid}",
        "stats_unauthorized": "⛔ Not authorized.",
        "change_lang": "🌐 Change language"
    },
    "ru": {
        "welcome": "Привет! 👋\nЯ бот технической инспекции. Отправь мне фото электроустановки, и я найду возможные нарушения.\n\nПросто отправь фото!",
        "choose_language": "🌐 Выберите язык:",
        "defects_list": "🔍 Найдены замечания:",
        "standard": "📜 Норматив:",
        "no_match": "❌ Похожих примеров не найдено.",
        "report_ready": "📄 Ваше предписание готово!",
        "no_defects": "📭 Нет замечаний.",
        "report_action": "🛠 Привести в соответствие с НТД.",
        "generate_order": "📄 Сформировать предписание",
        "order_title": "ПРЕДПИСАНИЕ",
        "issue_date": "Дата выдачи:",
        "defect": "Замечание",
        "standard_label": "Норматив:",
        "deadline": "Срок устранения: _______________",
        "issued_by": "ВЫДАЛ ПРЕДПИСАНИЕ:",
        "company": "Компания: ___________________",
        "position": "Должность: _________________",
        "full_name": "ФИО: _______________________",
        "signature": "Подпись: ___________________",
        "received_by": "ВЗЯЛ В РАБОТУ:",
        "violation_photo": "Фото нарушения",
        "free_checks_left": "✅ У вас осталось {count} бесплатных проверок.",
        "free_checks_used": "⚠️ Бесплатные проверки закончились.",
        "buy_button": "💳 Купить проверки",
        "buy_text": "Вы использовали все 5 бесплатных проверок.\n\nВарианты:\n• 10 проверок — $10 (10 USDT)\n• Безлимит (1 месяц) — $20 (20 USDT)\n\nОтправьте РОВНО {amount} USDT (TRC20) на:\n`{wallet}`\n\nПосле оплаты нажмите кнопку ниже.",
        "pay_sent": "✅ Я отправил оплату",
        "pay_check": "🔍 Проверяю оплату...",
        "pay_success": "✅ Оплата подтверждена! {count} проверок добавлено на ваш аккаунт.",
        "pay_fail": "❌ Оплата не найдена. Убедитесь, что вы отправили РОВНО {amount} USDT TRC20 на правильный адрес.\n\nЕсли у вас есть хеш транзакции (TXID), отправьте его сюда.",
        "pay_txid_prompt": "📋 Отправьте TXID (хеш транзакции) или текст с ним.",
        "balance_text": "Бесплатных проверок: {free}\nПлатных проверок: {paid}",
        "stats_unauthorized": "⛔ Вы не авторизованы.",
        "change_lang": "🌐 Сменить язык"
    },
    "de": {
        "welcome": "Hallo! 👋\nIch bin ein technischer Inspektionsbot. Senden Sie mir ein Foto einer elektrischen Anlage, und ich finde mögliche Verstöße.\n\nSenden Sie einfach ein Foto!",
        "choose_language": "🌐 Wählen Sie Ihre Sprache:",
        "defects_list": "🔍 Gefundene Mängel:",
        "standard": "📜 Norm:",
        "no_match": "❌ Keine ähnlichen Beispiele gefunden.",
        "report_ready": "📄 Ihre Anordnung ist fertig!",
        "no_defects": "📭 Keine Mängel erfasst.",
        "report_action": "🛠 Empfohlene Maßnahme: In Übereinstimmung mit den Normen bringen.",
        "generate_order": "📄 Anordnung erstellen",
        "order_title": "ANORDNUNG",
        "issue_date": "Ausstellungsdatum:",
        "defect": "Mangel",
        "standard_label": "Norm:",
        "deadline": "Frist zur Behebung: _______________",
        "issued_by": "AUSGESTELLT VON:",
        "company": "Unternehmen: ___________________",
        "position": "Position: _________________",
        "full_name": "Vollständiger Name: _______________________",
        "signature": "Unterschrift: ___________________",
        "received_by": "ERHALTEN VON:",
        "violation_photo": "Foto des Verstoßes",
        "free_checks_left": "✅ Sie haben noch {count} kostenlose Prüfungen.",
        "free_checks_used": "⚠️ Kostenlose Prüfungen aufgebraucht.",
        "buy_button": "💳 Prüfungen kaufen",
        "buy_text": "Sie haben alle 5 kostenlosen Prüfungen genutzt.\n\nOptionen:\n• 10 Prüfungen — 10 $ (10 USDT)\n• Unbegrenzt (1 Monat) — 20 $ (20 USDT)\n\nSenden Sie GENAU {amount} USDT (TRC20) an:\n`{wallet}`\n\nNach der Zahlung drücken Sie die Taste unten.",
        "pay_sent": "✅ Ich habe bezahlt",
        "pay_check": "🔍 Zahlung wird geprüft...",
        "pay_success": "✅ Zahlung bestätigt! {count} Prüfungen zu Ihrem Konto hinzugefügt.",
        "pay_fail": "❌ Zahlung nicht gefunden. Stellen Sie sicher, dass Sie GENAU {amount} USDT TRC20 an die richtige Adresse gesendet haben.\n\nWenn Sie die Transaktions-ID (TXID) haben, senden Sie sie hier.",
        "pay_txid_prompt": "📋 Senden Sie die TXID (Transaktionshash) oder den TXID-Text.",
        "balance_text": "Kostenlose Prüfungen: {free}\nBezahlte Prüfungen: {paid}",
        "stats_unauthorized": "⛔ Nicht autorisiert.",
        "change_lang": "🌐 Sprache ändern"
    },
    "it": {
        "welcome": "Ciao! 👋\nSono un bot di ispezione tecnica. Inviami una foto di un impianto elettrico e troverò possibili violazioni.\n\nInvia semplicemente una foto!",
        "choose_language": "🌐 Scegli la tua lingua:",
        "defects_list": "🔍 Difetti trovati:",
        "standard": "📜 Norma:",
        "no_match": "❌ Nessun esempio simile trovato.",
        "report_ready": "📄 Il tuo ordine è pronto!",
        "no_defects": "📭 Nessun difetto registrato.",
        "report_action": "🛠 Azione raccomandata: mettere in conformità con le norme.",
        "generate_order": "📄 Genera ordine",
        "order_title": "ORDINE",
        "issue_date": "Data di emissione:",
        "defect": "Difetto",
        "standard_label": "Norma:",
        "deadline": "Termine per la correzione: _______________",
        "issued_by": "EMESSO DA:",
        "company": "Azienda: ___________________",
        "position": "Posizione: _________________",
        "full_name": "Nome completo: _______________________",
        "signature": "Firma: ___________________",
        "received_by": "RICEVUTO DA:",
        "violation_photo": "Foto della violazione",
        "free_checks_left": "✅ Hai ancora {count} controlli gratuiti.",
        "free_checks_used": "⚠️ Controlli gratuiti esauriti.",
        "buy_button": "💳 Acquista controlli",
        "buy_text": "Hai usato tutti i 5 controlli gratuiti.\n\nOpzioni:\n• 10 controlli — 10 $ (10 USDT)\n• Illimitato (1 mese) — 20 $ (20 USDT)\n\nInvia ESATTAMENTE {amount} USDT (TRC20) a:\n`{wallet}`\n\nDopo il pagamento, premi il pulsante sotto.",
        "pay_sent": "✅ Ho inviato il pagamento",
        "pay_check": "🔍 Verifica del pagamento...",
        "pay_success": "✅ Pagamento confermato! {count} controlli aggiunti al tuo account.",
        "pay_fail": "❌ Pagamento non trovato. Assicurati di aver inviato ESATTAMENTE {amount} USDT TRC20 all'indirizzo corretto.\n\nSe hai l'hash della transazione (TXID), invialo qui.",
        "pay_txid_prompt": "📋 Invia il TXID (hash della transazione) o il testo del TXID.",
        "balance_text": "Controlli gratuiti: {free}\nControlli a pagamento: {paid}",
        "stats_unauthorized": "⛔ Non autorizzato.",
        "change_lang": "🌐 Cambia lingua"
    },
    "fr": {
        "welcome": "Bonjour ! 👋\nJe suis un bot d'inspection technique. Envoyez-moi une photo d'une installation électrique et je trouverai les violations possibles.\n\nEnvoyez simplement une photo !",
        "choose_language": "🌐 Choisissez votre langue :",
        "defects_list": "🔍 Défauts trouvés :",
        "standard": "📜 Norme :",
        "no_match": "❌ Aucun exemple similaire trouvé.",
        "report_ready": "📄 Votre ordre est prêt !",
        "no_defects": "📭 Aucun défaut enregistré.",
        "report_action": "🛠 Action recommandée : mettre en conformité avec les normes.",
        "generate_order": "📄 Générer l'ordre",
        "order_title": "ORDRE",
        "issue_date": "Date d'émission :",
        "defect": "Défaut",
        "standard_label": "Norme :",
        "deadline": "Délai de correction : _______________",
        "issued_by": "ÉMIS PAR :",
        "company": "Entreprise : ___________________",
        "position": "Poste : _________________",
        "full_name": "Nom complet : _______________________",
        "signature": "Signature : ___________________",
        "received_by": "REÇU PAR :",
        "violation_photo": "Photo de la violation",
        "free_checks_left": "✅ Il vous reste {count} vérifications gratuites.",
        "free_checks_used": "⚠️ Vérifications gratuites épuisées.",
        "buy_button": "💳 Acheter des vérifications",
        "buy_text": "Vous avez utilisé les 5 vérifications gratuites.\n\nOptions :\n• 10 vérifications — 10 $ (10 USDT)\n• Illimité (1 mois) — 20 $ (20 USDT)\n\nEnvoyez EXACTEMENT {amount} USDT (TRC20) à :\n`{wallet}`\n\nAprès paiement, appuyez sur le bouton ci-dessous.",
        "pay_sent": "✅ J'ai envoyé le paiement",
        "pay_check": "🔍 Vérification du paiement...",
        "pay_success": "✅ Paiement confirmé ! {count} vérifications ajoutées à votre compte.",
        "pay_fail": "❌ Paiement non trouvé. Assurez-vous d'avoir envoyé EXACTEMENT {amount} USDT TRC20 à la bonne adresse.\n\nSi vous avez le hash de transaction (TXID), envoyez-le ici.",
        "pay_txid_prompt": "📋 Envoyez le TXID (hash de transaction) ou le texte du TXID.",
        "balance_text": "Vérifications gratuites : {free}\nVérifications payantes : {paid}",
        "stats_unauthorized": "⛔ Non autorisé.",
        "change_lang": "🌐 Changer de langue"
    }
}

CATEGORIES = [
    {"keyword":"01_otsutstvuyut_birki", "etalon_prefix":"birki_etalon", "label_ru":"Бирки", "label_en":"Labels", "label_de":"Kennzeichnungen", "label_it":"Etichette", "label_fr":"Étiquettes",
     "text":{"en":"Missing cable/equipment labels.", "ru":"Отсутствуют бирки на оборудовании.", "de":"Fehlende Kennzeichnungen an Kabeln/Geräten.", "it":"Etichette mancanti su cavi/apparecchiature.", "fr":"Étiquettes manquantes sur les câbles/équipements."},
     "normative":{"en":"IEC 60445:2021 §6, HD 60364-5-52 §514.3", "ru":"ПУЭ п. 2.3.23, СП 76.13330.2016 п. 6.4.8", "de":"DIN VDE 0100-520:2023-04 §514.3, DIN EN 60445", "it":"CEI 64-8/5 Art. 514.3, CEI EN 60445", "fr":"NF C 15-100 Art. 514.3, NF EN 60445"},
     "normative_desc":{"en":"Identification of conductors and equipment.", "ru":"Идентификация проводников и оборудования.", "de":"Kennzeichnung von Leitern und Betriebsmitteln.", "it":"Identificazione di conduttori e apparecchiature.", "fr":"Identification des conducteurs et des équipements."}},
    {"keyword":"02_zadelka_prohodok", "etalon_prefix":"prohodki_etalon", "label_ru":"Проходки", "label_en":"Penetrations", "label_de":"Durchdringungen", "label_it":"Passaggi", "label_fr":"Traversées",
     "text":{"en":"Gaps in penetrations not sealed.", "ru":"Не выполнена заделка проходок.", "de":"Spalten in Durchdringungen nicht abgedichtet.", "it":"Fessure nei passaggi non sigillate.", "fr":"Interstices dans les traversées non scellés."},
     "normative":{"en":"IEC 60364-5-52:2009 §527.2, HD 60364-5-52 §527.2", "ru":"СП 76.13330.2016 п. 6.4.1.25", "de":"DIN VDE 0100-520:2023-04 §527.2, DIN 4102-12, MLAR §5", "it":"CEI 64-8/5 Art. 527.2, CEI 64-8/5 Art. 527.2.1", "fr":"NF C 15-100 Art. 527.2, NF C 15-100 Art. 527.2.1"},
     "normative_desc":{"en":"Fire sealing of cable and pipe penetrations.", "ru":"Огнезащита кабельных и трубных проходок.", "de":"Brandschutz bei Kabel- und Rohrdurchführungen.", "it":"Protezione contro la propagazione del fuoco nei passaggi.", "fr":"Protection contre la propagation du feu dans les traversées."}},
    {"keyword":"03_zazemlenie_ne_vypolneno", "etalon_prefix":"zazemlenie_etalon", "label_ru":"Заземление", "label_en":"Earthing", "label_de":"Erdung", "label_it":"Messa a terra", "label_fr":"Mise à la terre",
     "text":{"en":"Earthing not provided.", "ru":"Не выполнено заземление.", "de":"Erdung nicht vorhanden.", "it":"Messa a terra non fornita.", "fr":"Mise à la terre non réalisée."},
     "normative":{"en":"IEC 60364-5-54:2021 §542, HD 60364-5-54:2022 §542", "ru":"ПУЭ п. 1.7.76", "de":"DIN VDE 0100-540:2024-06 §542, §543, DIN VDE 0100-410 §411.3", "it":"CEI 64-8/54 Art. 542, Art. 543, CEI 64-8/41 Art. 411.3", "fr":"NF C 15-100 Art. 542, Art. 543, Art. 411.3"},
     "normative_desc":{"en":"Earthing arrangements and protective conductors.", "ru":"Заземляющие устройства и защитные проводники.", "de":"Erdungsanlagen und Schutzleiter.", "it":"Impianti di terra e conduttori di protezione.", "fr":"Installations de mise à la terre et conducteurs de protection."}},
    {"keyword":"04_shpilki_lotka_ne_srezany", "etalon_prefix":"shpilki_etalon", "label_ru":"Шпильки", "label_en":"Studs", "label_de":"Gewindebolzen", "label_it":"Perni", "label_fr":"Goujons",
     "text":{"en":"Cable tray studs not trimmed.", "ru":"Шпильки лотка не срезаны.", "de":"Gewindebolzen der Kabeltrasse nicht abgeschnitten.", "it":"Perni della canalina non tagliati.", "fr":"Goujons du chemin de câbles non coupés."},
     "normative":{"en":"IEC 61537:2020 §5, HD 60364-5-52 §522.8", "ru":"ГОСТ Р 50571.5.52-2011", "de":"DIN VDE 0100-520 §522.8, DIN EN 61537", "it":"CEI 64-8/5 Art. 522.8, CEI EN 61537", "fr":"NF C 15-100 Art. 522.8, NF EN 61537"},
     "normative_desc":{"en":"Cable tray systems — mechanical protection.", "ru":"Кабельные лотки — защита от механических повреждений.", "de":"Kabeltrassensysteme — Schutz gegen mechanische Beschädigung.", "it":"Sistemi di canalina — protezione meccanica.", "fr":"Systèmes de chemins de câbles — protection mécanique."}},
    {"keyword":"05_oksidy_rzhavchina", "etalon_prefix":"oksidy_etalon", "label_ru":"Окислы", "label_en":"Oxidation", "label_de":"Oxidation", "label_it":"Ossidazione", "label_fr":"Oxydation",
     "text":{"en":"Oxidation/rust on contacts.", "ru":"Окислы и ржавчина на контактах.", "de":"Oxidation/Rost an Kontakten.", "it":"Ossidazione/ruggine sui contatti.", "fr":"Oxydation/rouille sur les contacts."},
     "normative":{"en":"IEC 60204-1:2016 §4.4, IEC 60364-5-52 §522", "ru":"ПУЭ п. 1.8.4, ГОСТ 10434-82", "de":"DIN VDE 0100-520 §522.6, DIN EN 60204-1", "it":"CEI 64-8/5 Art. 522, CEI EN 60204-1", "fr":"NF C 15-100 Art. 522, NF EN 60204-1"},
     "normative_desc":{"en":"Protection against corrosion and external influences.", "ru":"Защита от коррозии и внешних воздействий.", "de":"Schutz gegen Korrosion und äußere Einflüsse.", "it":"Protezione contro la corrosione e influenze esterne.", "fr":"Protection contre la corrosion et les influences externes."}},
    {"keyword":"06_otsutstvie_shemy", "etalon_prefix":"shema_etalon", "label_ru":"Схема", "label_en":"Diagram", "label_de":"Schaltplan", "label_it":"Schema", "label_fr":"Schéma",
     "text":{"en":"Single-line diagram missing.", "ru":"Отсутствует однолинейная схема.", "de":"Einpoliger Schaltplan fehlt.", "it":"Schema unifilare mancante.", "fr":"Schéma unifilaire manquant."},
     "normative":{"en":"IEC 61082-1:2014 §4, HD 60364-6:2016 §6.4", "ru":"ПУЭ п. 1.8.4, СП 76.13330.2016 п. 6.4.8", "de":"DIN VDE 0100-100 §514.5, DIN EN 61082-1", "it":"CEI 64-8 Art. 514.5, CEI EN 61082-1", "fr":"NF C 15-100 Art. 514.5, NF EN 61082-1"},
     "normative_desc":{"en":"Documentation and preparation of electrotechnical documents.", "ru":"Документация и оформление электротехнических документов.", "de":"Dokumentation und Erstellung elektrotechnischer Dokumente.", "it":"Documentazione e preparazione di documenti elettrotecnici.", "fr":"Documentation et préparation de documents électrotechniques."}}
]

def init_db():
    conn = sqlite3.connect(db_path())
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        first_seen TEXT, last_seen TEXT,
        language TEXT DEFAULT "en",
        free_checks INTEGER DEFAULT 5,
        paid_checks INTEGER DEFAULT 0
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS sessions (
        user_id INTEGER, report_data TEXT, created_at TEXT,
        PRIMARY KEY (user_id)
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS pending_payments (
        user_id INTEGER, amount REAL, created_at TEXT,
        PRIMARY KEY (user_id)
    )''')
    conn.commit()
    conn.close()

def register_user(user_id):
    conn = sqlite3.connect(db_path())
    c = conn.cursor()
    now = dt.datetime.now().isoformat()
    r = c.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,)).fetchone()
    if r is None:
        c.execute("INSERT INTO users (user_id, first_seen, last_seen, language, free_checks, paid_checks) VALUES (?, ?, ?, 'en', ?, 0)",
                  (user_id, now, now, FREE_CHECKS_LIMIT))
    else:
        c.execute("UPDATE users SET last_seen = ? WHERE user_id = ?", (now, user_id))
    conn.commit()
    conn.close()

def get_lang(user_id):
    conn = sqlite3.connect(db_path())
    r = conn.execute("SELECT language FROM users WHERE user_id = ?", (user_id,)).fetchone()
    conn.close()
    return r[0] if r and r[0] else "en"

def set_lang(user_id, lang):
    conn = sqlite3.connect(db_path())
    conn.execute("UPDATE users SET language = ? WHERE user_id = ?", (lang, user_id))
    conn.commit()
    conn.close()

def get_balance(user_id):
    conn = sqlite3.connect(db_path())
    r = conn.execute("SELECT free_checks, paid_checks FROM users WHERE user_id = ?", (user_id,)).fetchone()
    conn.close()
    return (r[0], r[1]) if r else (0, 0)

def use_check(user_id):
    conn = sqlite3.connect(db_path())
    r = conn.execute("SELECT free_checks, paid_checks FROM users WHERE user_id = ?", (user_id,)).fetchone()
    if r:
        free, paid = r
        if free > 0:
            conn.execute("UPDATE users SET free_checks = free_checks - 1 WHERE user_id = ?", (user_id,))
        elif paid > 0:
            conn.execute("UPDATE users SET paid_checks = paid_checks - 1 WHERE user_id = ?", (user_id,))
        conn.commit()
    conn.close()

def add_paid_checks(user_id, count):
    conn = sqlite3.connect(db_path())
    conn.execute("UPDATE users SET paid_checks = paid_checks + ? WHERE user_id = ?", (count, user_id))
    conn.commit()
    conn.close()

def reset_checks(user_id):
    conn = sqlite3.connect(db_path())
    conn.execute("UPDATE users SET free_checks = 0, paid_checks = 0 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def get_stats():
    conn = sqlite3.connect(db_path())
    c = conn.cursor()
    total = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    today = dt.datetime.now().date().isoformat()
    today_count = c.execute("SELECT COUNT(*) FROM users WHERE date(first_seen) = ?", (today,)).fetchone()[0]
    week_ago = (dt.datetime.now() - timedelta(days=7)).date().isoformat()
    week_count = c.execute("SELECT COUNT(*) FROM users WHERE date(first_seen) >= ?", (week_ago,)).fetchone()[0]
    active_week = c.execute("SELECT COUNT(*) FROM users WHERE date(last_seen) >= ?", (week_ago,)).fetchone()[0]
    total_paid = c.execute("SELECT SUM(paid_checks) FROM users").fetchone()[0] or 0
    total_free = c.execute("SELECT SUM(free_checks) FROM users").fetchone()[0] or 0
    top_users = c.execute("SELECT user_id, paid_checks FROM users WHERE paid_checks > 0 ORDER BY paid_checks DESC LIMIT 5").fetchall()
    conn.close()
    return total, today_count, week_count, active_week, total_paid, total_free, top_users

def save_session(user_id, report_data):
    conn = sqlite3.connect(db_path())
    conn.execute("INSERT OR REPLACE INTO sessions (user_id, report_data, created_at) VALUES (?, ?, ?)", (user_id, json.dumps(report_data), dt.datetime.now().isoformat()))
    conn.commit()
    conn.close()

def load_session(user_id):
    conn = sqlite3.connect(db_path())
    r = conn.execute("SELECT report_data FROM sessions WHERE user_id = ?", (user_id,)).fetchone()
    conn.close()
    return json.loads(r[0]) if r else None

def delete_session(user_id):
    conn = sqlite3.connect(db_path())
    conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

try:
    pdfmetrics.registerFont(ttfonts.TTFont('DejaVuSans', 'DejaVuSans.ttf'))
    addMapping('DejaVuSans', 0, 0, 'DejaVuSans')
    FONT = 'DejaVuSans'
except:
    FONT = 'Helvetica'

index = None
image_paths = None
embedder = None
transform = None

def download_and_extract_photos():
    if os.path.exists("photo_db") and len(os.listdir("photo_db")) > 0:
        return
    gdown.download(PHOTO_DB_URL, "photo_db.zip", quiet=False)
    with zipfile.ZipFile("photo_db.zip", "r") as zf: zf.extractall(".")
    os.remove("photo_db.zip")
    if not os.path.exists("photo_db"):
        for item in os.listdir("."):
            if os.path.isdir(item) and item.startswith("photo_db"):
                os.rename(item, "photo_db"); break

def download_and_extract_etalons():
    if os.path.exists("etalons") and len(os.listdir("etalons")) > 0:
        return
    response = requests.get(ETALONS_URL, stream=True)
    with open("etalons.zip", "wb") as f:
        for chunk in response.iter_content(8192): f.write(chunk)
    with zipfile.ZipFile("etalons.zip", "r") as zf: zf.extractall(".")
    os.remove("etalons.zip")
    if not os.path.exists("etalons"):
        for item in os.listdir("."):
            if os.path.isdir(item) and item.startswith("etalons"):
                os.rename(item, "etalons"); break

def load_index():
    global index, image_paths
    if index is None:
        index = faiss.read_index(INDEX_PATH)
        with open(PATHS_PATH, "rb") as f: raw = pickle.load(f)
        image_paths = [os.path.join("photo_db", os.path.basename(p)) for p in raw]
        print(f"Index loaded, {len(image_paths)} images.")

def load_model():
    global embedder, transform
    if embedder is None:
        try:
            model = YOLO(MODEL_PATH)
            torch_model = model.model.model
            embedder = torch.nn.Sequential(*list(torch_model.children())[:-1]).eval()
            transform = transforms.Compose([
                transforms.Resize((224, 224)),
                transforms.ToTensor(),
                transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
            ])
            print("Model loaded.")
        except Exception as e:
            print(f"⚠️ Model not loaded: {e}")
            embedder = None

def get_embedding(image_path):
    if embedder is None:
        return None
    img = Image.open(image_path).convert('RGB')
    img_tensor = transform(img).unsqueeze(0)
    with torch.no_grad():
        return embedder(img_tensor).flatten().cpu().numpy()

def get_category_info(filename, lang):
    name = os.path.basename(filename)
    for cat in CATEGORIES:
        if name.startswith(cat["keyword"]):
            return {"text": cat["text"].get(lang, cat["text"]["en"]), "etalon_prefix": cat["etalon_prefix"], "normative": cat["normative"].get(lang, cat["normative"]["en"]), "normative_desc": cat.get("normative_desc", {}).get(lang, cat.get("normative_desc", {}).get("en", ""))}
    parts = name.split('_')
    for cat in CATEGORIES:
        if any(kp in parts for kp in cat["keyword"].split('_')):
            return {"text": cat["text"].get(lang, cat["text"]["en"]), "etalon_prefix": cat["etalon_prefix"], "normative": cat["normative"].get(lang, cat["normative"]["en"]), "normative_desc": cat.get("normative_desc", {}).get(lang, cat.get("normative_desc", {}).get("en", ""))}
    return {"text": f"Unknown defect (file: {name})", "etalon_prefix": None, "normative": None, "normative_desc": ""}

def find_etalon(prefix):
    if not prefix or not os.path.exists("etalons"): return None
    for f in os.listdir("etalons"):
        if f.startswith(prefix) and f.lower().endswith(('.jpg', '.jpeg', '.png')):
            return os.path.join("etalons", f)
    return None

def get_report_keyboard(lang):
    return InlineKeyboardMarkup([[InlineKeyboardButton(T[lang]['generate_order'], callback_data="generate_report")]])

def get_language_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")],
        [InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru")],
        [InlineKeyboardButton("🇩🇪 Deutsch", callback_data="lang_de")],
        [InlineKeyboardButton("🇮🇹 Italiano", callback_data="lang_it")],
        [InlineKeyboardButton("🇫🇷 Français", callback_data="lang_fr")]
    ])

def get_buy_keyboard(lang):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(T[lang]['buy_button'], callback_data="buy_checks")],
        [InlineKeyboardButton(T[lang]['change_lang'], callback_data="change_lang")]
    ])

def generate_pdf_report(report_data, lang):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    for s in styles.byName: styles[s].fontName = FONT
    title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=18, alignment=1, fontName=FONT)
    story = []
    t = T[lang]
    story.append(Paragraph(t['order_title'], title_style))
    story.append(Paragraph(f"{t['issue_date']} {dt.datetime.now().strftime('%d.%m.%Y')}", styles['Normal']))
    story.append(Spacer(1, 6*mm))
    if report_data:
        photo_path = report_data[0].get('photo_path')
        for i, item in enumerate(report_data, 1):
            story.append(Paragraph(f"<b>{t['defect']} #{i}</b>", styles['Heading2']))
            story.append(Paragraph(f"{item.get('text', '')}", styles['Normal']))
            story.append(Paragraph(f"{t['standard_label']} {item.get('normative', '—')}", styles['Normal']))
            if item.get('normative_desc'):
                story.append(Paragraph(f"→ {item['normative_desc']}", styles['Normal']))
            story.append(Paragraph(t['report_action'], styles['Normal']))
            story.append(Spacer(1, 4*mm))
        if photo_path and os.path.exists(photo_path):
            try:
                img = RLImage(photo_path, width=120*mm, height=80*mm)
                story.append(img)
                story.append(Paragraph(t['violation_photo'], styles['Normal']))
            except: pass
        story.append(Spacer(1, 6*mm))
        story.append(Paragraph(t['deadline'], styles['Normal']))
        story.append(Spacer(1, 4*mm))
        story.append(Paragraph(t['issued_by'], styles['Normal']))
        story.append(Paragraph(t['company'], styles['Normal']))
        story.append(Paragraph(t['position'], styles['Normal']))
        story.append(Paragraph(t['full_name'], styles['Normal']))
        story.append(Paragraph(t['signature'], styles['Normal']))
        story.append(Spacer(1, 4*mm))
        story.append(Paragraph(t['received_by'], styles['Normal']))
        story.append(Paragraph(t['company'], styles['Normal']))
        story.append(Paragraph(t['position'], styles['Normal']))
        story.append(Paragraph(t['full_name'], styles['Normal']))
        story.append(Paragraph(t['signature'], styles['Normal']))
    else:
        story.append(Paragraph(t['no_defects'], styles['Normal']))
    doc.build(story)
    buffer.seek(0)
    return buffer

async def handle_photo(update, context):
    user_id = update.effective_user.id
    register_user(user_id)
    lang = get_lang(user_id)
    t = T[lang]
    free, paid = get_balance(user_id)
    if free <= 0 and paid <= 0:
        amount = get_unique_amount(user_id)
        await update.message.reply_text(
            t['free_checks_used'] + "\n\n" + t['buy_text'].format(wallet=USDT_WALLET, amount=amount),
            reply_markup=get_buy_keyboard(lang)
        )
        return
    load_index(); load_model()
    photo = update.message.photo[-1]
    file = await photo.get_file()
    user_path = f"temp_{user_id}.jpg"
    await file.download_to_drive(user_path)
    emb = get_embedding(user_path)
    os.remove(user_path)
    if emb is None:
        await update.message.reply_text("⚠️ Service temporarily unavailable. Please try again later.")
        return
    emb = np.array([emb]).astype('float32')
    distances, indices = index.search(emb, 3)
    if len(indices[0]) == 0 or indices[0][0] == -1:
        await update.message.reply_text(t['no_match']); return
    use_check(user_id)
    free_left, paid_left = get_balance(user_id)
    review_dir = "review"
    os.makedirs(review_dir, exist_ok=True)
    timestamp = dt.datetime.now().strftime('%Y%m%d_%H%M%S')
    review_path = os.path.join(review_dir, f"{timestamp}.jpg")
    await file.download_to_drive(review_path)
    unique, seen = [], set()
    for idx in indices[0]:
        info = get_category_info(image_paths[idx], lang)
        key = info.get("etalon_prefix")
        if key and key not in seen:
            seen.add(key); unique.append(info)
            if len(unique) >= 3: break
    if not unique:
        await update.message.reply_text(t['no_match']); return
    response = t['defects_list'] + "\n"
    for i, d in enumerate(unique, 1):
        response += f"{i}. {d['text']}\n"
        if d.get('normative'): response += f"   {t['standard']} {d['normative']}\n"
        if d.get('normative_desc'): response += f"   → {d['normative_desc']}\n"
    if free_left > 0: response += f"\n{t['free_checks_left'].format(count=free_left)}"
    report_data = [{'text': d['text'], 'normative': d.get('normative'), 'normative_desc': d.get('normative_desc', ''), 'photo_path': review_path} for d in unique]
    save_session(user_id, report_data)
    context.user_data['report_data'] = report_data
    keyboard = get_report_keyboard(lang)
    if free_left == 0 and paid_left == 0: keyboard = get_buy_keyboard(lang)
    etalon_path = find_etalon(unique[0].get("etalon_prefix"))
    if etalon_path and os.path.exists(etalon_path):
        with open(etalon_path, 'rb') as f:
            await update.message.reply_photo(photo=f, caption=response, reply_markup=keyboard)
    else:
        await update.message.reply_text(response, reply_markup=keyboard)

async def handle_txid(update, context):
    user_id = update.effective_user.id
    lang = get_lang(user_id)
    t = T[lang]
    text = update.message.text.strip()
    if not re.match(r'^[0-9a-fA-Fx]{64,}$', text):
        return
    await update.message.reply_text(t['pay_check'])
    amount = check_payment(text, 10, user_id)
    if amount:
        add_paid_checks(user_id, 10)
        clear_pending(user_id)
        await update.message.reply_text(t['pay_success'].format(count=10))
    else:
        await update.message.reply_text(t['pay_fail'].format(amount=get_unique_amount(user_id)))

async def button_callback(update, context):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    register_user(user_id)
    lang = get_lang(user_id)
    t = T[lang]
    data = query.data

    if data == "change_lang":
        await query.edit_message_text(T[lang]['choose_language'], reply_markup=get_language_keyboard())
        return

    if data == "buy_checks":
        amount = get_unique_amount(user_id)
        await query.message.reply_text(
            t['buy_text'].format(wallet=USDT_WALLET, amount=amount),
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t['pay_sent'], callback_data="pay_sent")]])
        )
        return

    if data == "pay_sent":
        amount = get_unique_amount(user_id)
        await query.message.reply_text(t['pay_check'])
        txid, found = check_payment_by_user(user_id, amount, since_minutes=180)
        if txid:
            add_paid_checks(user_id, 10)
            clear_pending(user_id)
            await query.message.reply_text(t['pay_success'].format(count=10))
        else:
            await query.message.reply_text(t['pay_txid_prompt'])
        return

    if data == "generate_report":
        report_data = load_session(user_id) or context.user_data.get('report_data')
        if not report_data:
            await query.edit_message_text(t['no_defects']); return
        pdf_buffer = generate_pdf_report(report_data, lang)
        fname = f"Order_{dt.datetime.now().strftime('%d.%m.%Y')}.pdf"
        if lang == "ru": fname = f"Предписание_{dt.datetime.now().strftime('%d.%m.%Y')}.pdf"
        elif lang == "de": fname = f"Anordnung_{dt.datetime.now().strftime('%d.%m.%Y')}.pdf"
        elif lang == "it": fname = f"Ordine_{dt.datetime.now().strftime('%d.%m.%Y')}.pdf"
        elif lang == "fr": fname = f"Ordre_{dt.datetime.now().strftime('%d.%m.%Y')}.pdf"
        await query.message.reply_document(document=pdf_buffer, filename=fname, caption=t['report_ready'])
        delete_session(user_id)
        context.user_data.pop('report_data', None)
        await query.delete_message()
        return

    if data.startswith("lang_"):
        new_lang = data.split("_")[1]
        set_lang(user_id, new_lang)
        await query.edit_message_text(T[new_lang]['welcome'])
        return

async def start_command(update, context):
    user_id = update.effective_user.id
    register_user(user_id)
    lang = get_lang(user_id)
    t = T[lang]
    free, paid = get_balance(user_id)
    if free <= 0 and paid <= 0:
        amount = get_unique_amount(user_id)
        await update.message.reply_text(
            t['free_checks_used'] + "\n\n" + t['buy_text'].format(wallet=USDT_WALLET, amount=amount),
            reply_markup=get_buy_keyboard(lang)
        )
    else:
        await update.message.reply_text(T[lang]['choose_language'], reply_markup=get_language_keyboard())

async def balance_command(update, context):
    user_id = update.effective_user.id
    register_user(user_id)
    lang = get_lang(user_id)
    t = T[lang]
    free, paid = get_balance(user_id)
    await update.message.reply_text(
        t['balance_text'].format(free=free, paid=paid),
        reply_markup=get_buy_keyboard(lang)
    )

async def review_command(update, context):
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        await update.message.reply_text("⛔ Not authorized.")
        return
    review_dir = "review"
    if not os.path.exists(review_dir):
        os.makedirs(review_dir, exist_ok=True)
        await update.message.reply_text("📭 Review folder is empty.")
        return
    photos = []
    for root, _, files in os.walk(review_dir):
        for f in files:
            if f.lower().endswith(('.jpg', '.jpeg', '.png')):
                photos.append(os.path.join(root, f))
    if not photos:
        await update.message.reply_text("📭 Review folder is empty.")
        return
    await update.message.reply_text(f"📸 Found {len(photos)} photos.")
    for path in photos:
        try:
            with open(path, 'rb') as f:
                await update.message.reply_photo(photo=f)
        except Exception as e:
            print(f"❌ Error sending {path}: {e}")
    await update.message.reply_text("✅ All photos sent.")

async def stats_command(update, context):
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        await update.message.reply_text("⛔ Not authorized.")
        return
    total, today, week, active, paid, free, top = get_stats()
    text = (
        f"📊 **Bot Statistics**\n\n"
        f"👥 Total users: {total}\n"
        f"📈 New today: {today}\n"
        f"📅 New this week: {week}\n"
        f"🔥 Active this week: {active}\n"
        f"💰 Total paid checks: {paid}\n"
        f"🎁 Free checks left: {free}"
    )
    if top:
        text += "\n\n🏆 **Top paid users:**\n"
        for uid, p in top:
            text += f"• `{uid}` — {p} paid\n"
    await update.message.reply_text(text, parse_mode="Markdown")

async def addchecks_command(update, context):
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        await update.message.reply_text("⛔ Not authorized."); return
    args = context.args
    if len(args) != 2:
        await update.message.reply_text("Usage: /addchecks <user_id> <count>"); return
    try:
        add_paid_checks(int(args[0]), int(args[1]))
        await update.message.reply_text(f"✅ Added {args[1]} checks to user {args[0]}.")
    except:
        await update.message.reply_text("❌ Invalid arguments.")

async def resetchecks_command(update, context):
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        await update.message.reply_text("⛔ Not authorized."); return
    args = context.args
    if len(args) != 1:
        await update.message.reply_text("Usage: /resetchecks <user_id>"); return
    try:
        reset_checks(int(args[0]))
        await update.message.reply_text(f"✅ Reset all checks for user {args[0]}.")
    except:
        await update.message.reply_text("❌ Invalid arguments.")

if __name__ == "__main__":
    init_db()
    download_and_extract_photos()
    download_and_extract_etalons()
    load_index()
    load_model()
    app = Application.builder().token(TOKEN).read_timeout(60).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("balance", balance_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("review", review_command))
    app.add_handler(CommandHandler("addchecks", addchecks_command))
    app.add_handler(CommandHandler("resetchecks", resetchecks_command))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_txid))
    app.add_handler(CallbackQueryHandler(button_callback))
    print("🚀 Bot started (FINAL: 5 free checks, 10 USDT = 10 checks, auto payment, language switch).")
    app.run_polling()
