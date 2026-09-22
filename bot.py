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
import sys
import asyncio
import hashlib
import random
from datetime import timedelta
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
)
from telegram.ext import (
    Application, MessageHandler, filters, CallbackQueryHandler,
    CommandHandler, PreCheckoutQueryHandler
)
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

try:
    from translations import TRANSLATIONS, get_text
except ImportError:
    TRANSLATIONS = {}
    def get_text(lang, key, **kwargs):
        return key

SMETY_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'smety')
if SMETY_DIR not in sys.path:
    sys.path.insert(0, SMETY_DIR)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

import logging
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

PHOTO_DB_URL = "https://github.com/Sergijus1981/mytechbot/releases/download/v1.0.0/photo_db.zip"
ETALONS_URL = "https://github.com/Sergijus1981/mytechbot/releases/download/v1.0.0/etalons.zip"

INDEX_PATH = "faiss_index.bin"
PATHS_PATH = "image_paths.pkl"
MODEL_PATH = "best.pt"
OWNER_ID = 8743362338

FREE_CHECKS_LIMIT = 5
SMETA_PRICE_CHECKS = 5
PHOTO_PRICE_CHECKS = 1

USDT_WALLET = "TZ4bfpNTvMdMNRzQJt817pVjF3nEGtCKSH"
USDT_CONTRACT = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"
TRONGRID_API = "https://api.trongrid.io/v1/accounts/{address}/transactions/trc20"

STAR_PACKAGES = [
    {"id": "10",  "stars": 10,  "xtr": 10,  "usdt": None},
    {"id": "50",  "stars": 50,  "xtr": 50,  "usdt": 5},
    {"id": "100", "stars": 100, "xtr": 100, "usdt": 10},
    {"id": "250", "stars": 250, "xtr": None, "usdt": 25},
]


def db_path():
    return "/data/users.db" if os.path.exists("/data") else "users.db"


# ========== USDT ==========
def get_recent_transactions(limit=20):
    try:
        url = TRONGRID_API.format(address=USDT_WALLET)
        params = {"limit": limit, "only_confirmed": "true",
                  "contract_address": USDT_CONTRACT, "only_to": "true"}
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
        if tx.get("to", "") != USDT_WALLET:
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


T = {
    "en": {
        "welcome": "Hello! 👋\nI'm a technical inspection bot. Send me a photo of electrical installation, and I'll find possible violations.\n\nOr choose an action in the menu.",
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
        "free_checks_left": "✅ You have {count} ⭐ left.",
        "free_checks_used": "⚠️ You're out of stars.",
        "buy_button": "💳 Buy stars",
        "buy_text": "You're out of stars.\n\nBuy stars via Telegram (instant) or USDT TRC20.",
        "pay_sent": "✅ I've sent payment",
        "pay_check": "🔍 Checking payment...",
        "pay_success": "✅ Payment confirmed! +{count} ⭐",
        "pay_fail": "❌ Payment not found. Check amount and address.",
        "pay_txid_prompt": "📋 Send the TXID (transaction hash).",
        "balance_text": "Free stars: {free}\nPaid stars: {paid}",
        "stats_unauthorized": "⛔ Not authorized.",
        "change_lang": "🌐 Change language",
        "back_to_menu": "« Back to menu",
        "buy_welcome": "💳 Top up balance",
        "buy_stars": "⭐ Pay {xtr} Stars",
        "buy_usdt": "💎 Pay {usdt} USDT",
        "stars_success": "✅ Paid! +{stars} ⭐",
        "usdt_amount": "💎 Send EXACTLY {amount} USDT (TRC20) to:\n`{wallet}`\n\nAfter payment press the button.",
        "usdt_success": "✅ USDT received! +{stars} ⭐",
        "usdt_not_found": "❌ Payment not found. Try again or send TXID.",
        "main_menu": "🏠 Main menu",
        "smeta_menu": "📊 Estimates",
        "check_photo_menu": "📷 Check photo",
        "buy_menu": "💳 Buy stars",
        "balance_menu": "💰 Balance",
        "smeta_only_ru": "⚠️ Estimates are available only in Russian for now.",
        "smeta_button": "📊 Составить смету",
        "smeta_back": "« Назад в меню",
    },
    "ru": {
        "welcome": "Привет! 👋\nЯ Electrical Inspector Bot.\n\n📷 Фото-проверка — нахожу нарушения на электроустановках\n📊 Сметы — PDF спецификации → готовая смета в Excel (цены с ЭТМ, Петрович, Планета Света)\n📄 Предписания — формирую PDF для заказчика\n\nВыбери в меню или просто отправь фото/PDF.",
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
        "free_checks_left": "✅ У вас осталось {count} ⭐.",
        "free_checks_used": "⚠️ Звёзды закончились.",
        "buy_button": "💳 Купить звёзды",
        "buy_text": "У вас закончились звёзды.\n\nПополните баланс через Telegram Stars (мгновенно) или USDT TRC20.",
        "pay_sent": "✅ Я отправил оплату",
        "pay_check": "🔍 Проверяю оплату...",
        "pay_success": "✅ Оплата подтверждена! +{count} ⭐",
        "pay_fail": "❌ Оплата не найдена. Проверьте сумму и адрес.",
        "pay_txid_prompt": "📋 Отправьте TXID (хеш транзакции).",
        "balance_text": "Бесплатных звёзд: {free}\nПлатных звёзд: {paid}",
        "stats_unauthorized": "⛔ Вы не авторизованы.",
        "change_lang": "🌐 Сменить язык",
        "back_to_menu": "« Назад в меню",
        "buy_welcome": "💳 Пополнение баланса",
        "buy_stars": "⭐ Оплатить {xtr} Stars",
        "buy_usdt": "💎 Оплатить {usdt} USDT",
        "stars_success": "✅ Оплачено! +{stars} ⭐",
        "usdt_amount": "💎 Отправь РОВНО {amount} USDT (TRC20) на:\n`{wallet}`\n\nПосле оплаты нажми кнопку.",
        "usdt_success": "✅ USDT получен! +{stars} ⭐",
        "usdt_not_found": "❌ Платёж не найден. Попробуй снова или пришли TXID.",
        "main_menu": "🏠 Главное меню",
        "smeta_menu": "📊 Сметы",
        "check_photo_menu": "📷 Проверить фото",
        "buy_menu": "💳 Купить звёзды",
        "balance_menu": "💰 Баланс",
        "smeta_only_ru": "⚠️ Сметы пока доступны только на русском языке.",
        "smeta_button": "📊 Составить смету",
        "smeta_back": "« Назад в меню",
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
        "free_checks_left": "✅ Sie haben noch {count} ⭐.",
        "free_checks_used": "⚠️ Sterne aufgebraucht.",
        "buy_button": "💳 Sterne kaufen",
        "buy_text": "Sie haben keine Sterne mehr.\n\nKaufen Sie über Telegram Stars (sofort) oder USDT TRC20.",
        "pay_sent": "✅ Ich habe bezahlt",
        "pay_check": "🔍 Zahlung wird geprüft...",
        "pay_success": "✅ Zahlung bestätigt! +{count} ⭐",
        "pay_fail": "❌ Zahlung nicht gefunden. Prüfen Sie Betrag und Adresse.",
        "pay_txid_prompt": "📋 Senden Sie die TXID (Transaktionshash).",
        "balance_text": "Kostenlose Sterne: {free}\nBezahlte Sterne: {paid}",
        "stats_unauthorized": "⛔ Nicht autorisiert.",
        "change_lang": "🌐 Sprache ändern",
        "back_to_menu": "« Zurück zum Menü",
        "buy_welcome": "💳 Guthaben aufladen",
        "buy_stars": "⭐ {xtr} Sterne zahlen",
        "buy_usdt": "💎 {usdt} USDT zahlen",
        "stars_success": "✅ Bezahlt! +{stars} ⭐",
        "usdt_amount": "💎 Senden Sie GENAU {amount} USDT (TRC20) an:\n`{wallet}`\n\nNach Zahlung Taste drücken.",
        "usdt_success": "✅ USDT erhalten! +{stars} ⭐",
        "usdt_not_found": "❌ Zahlung nicht gefunden.",
        "main_menu": "🏠 Hauptmenü",
        "smeta_menu": "📊 Kostenvoranschläge",
        "check_photo_menu": "📷 Foto prüfen",
        "buy_menu": "💳 Sterne kaufen",
        "balance_menu": "💰 Guthaben",
        "smeta_only_ru": "⚠️ Kostenvoranschläge sind derzeit nur auf Russisch verfügbar.",
        "smeta_button": "📊 Kostenvoranschlag",
        "smeta_back": "« Zurück",
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
        "free_checks_left": "✅ Hai ancora {count} ⭐.",
        "free_checks_used": "⚠️ Stelle esaurite.",
        "buy_button": "💳 Acquista stelle",
        "buy_text": "Non hai più stelle.\n\nAcquista con Telegram Stars (istantaneo) o USDT TRC20.",
        "pay_sent": "✅ Ho inviato il pagamento",
        "pay_check": "🔍 Verifica del pagamento...",
        "pay_success": "✅ Pagamento confermato! +{count} ⭐",
        "pay_fail": "❌ Pagamento non trovato.",
        "pay_txid_prompt": "📋 Invia il TXID.",
        "balance_text": "Stelle gratuite: {free}\nStelle pagate: {paid}",
        "stats_unauthorized": "⛔ Non autorizzato.",
        "change_lang": "🌐 Cambia lingua",
        "back_to_menu": "« Torna al menu",
        "buy_welcome": "💳 Ricarica",
        "buy_stars": "⭐ Paga {xtr} Stars",
        "buy_usdt": "💎 Paga {usdt} USDT",
        "stars_success": "✅ Pagato! +{stars} ⭐",
        "usdt_amount": "💎 Invia ESATTAMENTE {amount} USDT (TRC20) a:\n`{wallet}`",
        "usdt_success": "✅ USDT ricevuto! +{stars} ⭐",
        "usdt_not_found": "❌ Pagamento non trovato.",
        "main_menu": "🏠 Menu principale",
        "smeta_menu": "📊 Preventivi",
        "check_photo_menu": "📷 Controlla foto",
        "buy_menu": "💳 Acquista stelle",
        "balance_menu": "💰 Saldo",
        "smeta_only_ru": "⚠️ I preventivi sono disponibili solo in russo.",
        "smeta_button": "📊 Preventivo",
        "smeta_back": "« Indietro",
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
        "free_checks_left": "✅ Il vous reste {count} ⭐.",
        "free_checks_used": "⚠️ Plus d'étoiles.",
        "buy_button": "💳 Acheter des étoiles",
        "buy_text": "Plus d'étoiles.\n\nAchetez via Telegram Stars (instantané) ou USDT TRC20.",
        "pay_sent": "✅ J'ai envoyé le paiement",
        "pay_check": "🔍 Vérification du paiement...",
        "pay_success": "✅ Paiement confirmé ! +{count} ⭐",
        "pay_fail": "❌ Paiement non trouvé.",
        "pay_txid_prompt": "📋 Envoyez le TXID.",
        "balance_text": "Étoiles gratuites : {free}\nÉtoiles payantes : {paid}",
        "stats_unauthorized": "⛔ Non autorisé.",
        "change_lang": "🌐 Changer de langue",
        "back_to_menu": "« Retour au menu",
        "buy_welcome": "💳 Recharger",
        "buy_stars": "⭐ Payer {xtr} Stars",
        "buy_usdt": "💎 Payer {usdt} USDT",
        "stars_success": "✅ Payé ! +{stars} ⭐",
        "usdt_amount": "💎 Envoyez EXACTEMENT {amount} USDT (TRC20) à :\n`{wallet}`",
        "usdt_success": "✅ USDT reçu ! +{stars} ⭐",
        "usdt_not_found": "❌ Paiement non trouvé.",
        "main_menu": "🏠 Menu principal",
        "smeta_menu": "📊 Devis",
        "check_photo_menu": "📷 Vérifier la photo",
        "buy_menu": "💳 Acheter des étoiles",
        "balance_menu": "💰 Solde",
        "smeta_only_ru": "⚠️ Les devis sont uniquement en russe.",
        "smeta_button": "📊 Devis",
        "smeta_back": "« Retour",
    }
}

CATEGORIES = [
    {"keyword":"01_otsutstvuyut_birki", "etalon_prefix":"birki_etalon", "label_ru":"Бирки", "label_en":"Labels", "label_de":"Kennzeichnungen", "label_it":"Etichette", "label_fr":"Étiquettes",
     "text":{"en":"Missing cable/equipment labels.", "ru":"Отсутствуют бирки на оборудовании.", "de":"Fehlende Kennzeichnungen an Kabeln/Geräten.", "it":"Etichette mancanti su cavi/apparecchiature.", "fr":"Étiquettes manquantes sur les câbles/équipements."},
     "normative":{"en":"IEC 60445:2021 §6, HD 60364-5-52 §514.3", "ru":"ПУЭ п. 2.3.23, СП 76.13330.2016 п. 6.4.8", "de":"DIN VDE 0100-520:2023-04 §514.3, DIN EN 60445", "it":"CEI 64-8/5 Art. 514.3, CEI EN 60445", "fr":"NF C 15-100 Art. 514.3, NF EN 60445"},
     "normative_desc":{"en":"Identification of conductors and equipment.", "ru":"Идентификация проводников и оборудования.", "de":"Kennzeichnung von Leitern und Betriebsmitteln.", "it":"Identificazione di conduttori e apparecchiature.", "fr":"Identification des conducteurs et des équipements."}},
    {"keyword":"02_zadelka_prohodok", "etalon_prefix":"prohodki_etalon", "label_ru":"Проходки", "label_en":"Penetrations", "label_de":"Durchdringungen", "label_it":"Passaggi", "label_fr":"Traversées",
     "text":{"en":"Gaps in penetrations not sealed.", "ru":"Не выполнена заделка проходок.", "de":"Spalten in Durchdringungen nicht abgedichtet.", "it":"Fessure nei passaggi non sigillate.", "fr":"Interstices dans les traversées non scellés."},
     "normative":{"en":"IEC 60364-5-52:2009 §527.2, HD 60364-5-52 §527.2", "ru":"СП 76.13330.2016 п. 6.4.1.25", "de":"DIN VDE 0100-520:2023-04 §527.2, DIN 4102-12, MLAR §5", "it":"CEI 64-8/5 Art. 527.2", "fr":"NF C 15-100 Art. 527.2"},
     "normative_desc":{"en":"Fire sealing of cable and pipe penetrations.", "ru":"Огнезащита кабельных и трубных проходок.", "de":"Brandschutz bei Kabel- und Rohrdurchführungen.", "it":"Protezione contro la propagazione del fuoco.", "fr":"Protection contre la propagation du feu."}},
    {"keyword":"03_zazemlenie_ne_vypolneno", "etalon_prefix":"zazemlenie_etalon", "label_ru":"Заземление", "label_en":"Earthing", "label_de":"Erdung", "label_it":"Messa a terra", "label_fr":"Mise à la terre",
     "text":{"en":"Earthing not provided.", "ru":"Не выполнено заземление.", "de":"Erdung nicht vorhanden.", "it":"Messa a terra non fornita.", "fr":"Mise à la terre non réalisée."},
     "normative":{"en":"IEC 60364-5-54:2021 §542", "ru":"ПУЭ п. 1.7.76", "de":"DIN VDE 0100-540:2024-06 §542", "it":"CEI 64-8/54 Art. 542", "fr":"NF C 15-100 Art. 542"},
     "normative_desc":{"en":"Earthing arrangements and protective conductors.", "ru":"Заземляющие устройства и защитные проводники.", "de":"Erdungsanlagen und Schutzleiter.", "it":"Impianti di terra.", "fr":"Installations de mise à la terre."}},
    {"keyword":"04_shpilki_lotka_ne_srezany", "etalon_prefix":"shpilki_etalon", "label_ru":"Шпильки", "label_en":"Studs", "label_de":"Gewindebolzen", "label_it":"Perni", "label_fr":"Goujons",
     "text":{"en":"Cable tray studs not trimmed.", "ru":"Шпильки лотка не срезаны.", "de":"Gewindebolzen nicht abgeschnitten.", "it":"Perni non tagliati.", "fr":"Goujons non coupés."},
     "normative":{"en":"IEC 61537:2020 §5", "ru":"ГОСТ Р 50571.5.52-2011", "de":"DIN VDE 0100-520 §522.8", "it":"CEI 64-8/5 Art. 522.8", "fr":"NF C 15-100 Art. 522.8"},
     "normative_desc":{"en":"Cable tray systems — mechanical protection.", "ru":"Кабельные лотки — защита от механических повреждений.", "de":"Kabeltrassensysteme — Schutz gegen Beschädigung.", "it":"Sistemi di canalina — protezione meccanica.", "fr":"Chemins de câbles — protection mécanique."}},
    {"keyword":"05_oksidy_rzhavchina", "etalon_prefix":"oksidy_etalon", "label_ru":"Окислы", "label_en":"Oxidation", "label_de":"Oxidation", "label_it":"Ossidazione", "label_fr":"Oxydation",
     "text":{"en":"Oxidation/rust on contacts.", "ru":"Окислы и ржавчина на контактах.", "de":"Oxidation/Rost an Kontakten.", "it":"Ossidazione/ruggine.", "fr":"Oxydation/rouille."},
     "normative":{"en":"IEC 60204-1:2016 §4.4", "ru":"ПУЭ п. 1.8.4, ГОСТ 10434-82", "de":"DIN VDE 0100-520 §522.6", "it":"CEI 64-8/5 Art. 522", "fr":"NF C 15-100 Art. 522"},
     "normative_desc":{"en":"Protection against corrosion.", "ru":"Защита от коррозии.", "de":"Schutz gegen Korrosion.", "it":"Protezione contro la corrosione.", "fr":"Protection contre la corrosion."}},
    {"keyword":"06_otsutstvie_shemy", "etalon_prefix":"shema_etalon", "label_ru":"Схема", "label_en":"Diagram", "label_de":"Schaltplan", "label_it":"Schema", "label_fr":"Schéma",
     "text":{"en":"Single-line diagram missing.", "ru":"Отсутствует однолинейная схема.", "de":"Einpoliger Schaltplan fehlt.", "it":"Schema unifilare mancante.", "fr":"Schéma unifilaire manquant."},
     "normative":{"en":"IEC 61082-1:2014 §4", "ru":"ПУЭ п. 1.8.4, СП 76.13330.2016", "de":"DIN VDE 0100-100 §514.5", "it":"CEI 64-8 Art. 514.5", "fr":"NF C 15-100 Art. 514.5"},
     "normative_desc":{"en":"Documentation of electrotechnical documents.", "ru":"Оформление электротехнических документов.", "de":"Erstellung elektrotechnischer Dokumente.", "it":"Documenti elettrotecnici.", "fr":"Documents électrotechniques."}}
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


def use_check(user_id, count=1):
    conn = sqlite3.connect(db_path())
    for _ in range(count):
        r = conn.execute("SELECT free_checks, paid_checks FROM users WHERE user_id = ?", (user_id,)).fetchone()
        if not r:
            break
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


def reset_all_users():
    conn = sqlite3.connect(db_path())
    conn.execute("UPDATE users SET free_checks = 5, paid_checks = 0")
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
    conn.execute("INSERT OR REPLACE INTO sessions (user_id, report_data, created_at) VALUES (?, ?, ?)",
                 (user_id, json.dumps(report_data), dt.datetime.now().isoformat()))
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
        print("[PHOTO] photo_db already exists, skip")
        return
    try:
        print("[PHOTO] Downloading photo_db.zip...")
        gdown.download(PHOTO_DB_URL, "photo_db.zip", quiet=False)
        size = os.path.getsize("photo_db.zip") if os.path.exists("photo_db.zip") else 0
        print(f"[PHOTO] Downloaded: {size} bytes")
        print("[PHOTO] Extracting...")
        with zipfile.ZipFile("photo_db.zip", "r") as zf:
            zf.extractall(".")
        print("[PHOTO] Extracted OK")
        os.remove("photo_db.zip")
        if not os.path.exists("photo_db"):
            for item in os.listdir("."):
                if os.path.isdir(item) and item.startswith("photo_db"):
                    os.rename(item, "photo_db")
                    print(f"[PHOTO] Renamed {item} -> photo_db")
                    break
        n = len(os.listdir("photo_db")) if os.path.exists("photo_db") else 0
        print(f"[PHOTO] Done. Files: {n}")
    except Exception as e:
        print(f"[PHOTO] ERROR: {e}")
        import traceback
        traceback.print_exc()


def download_and_extract_etalons():
    if os.path.exists("etalons") and len(os.listdir("etalons")) > 0:
        print("[ETALONS] etalons already exists, skip")
        return
    try:
        print("[ETALONS] Downloading etalons.zip...")
        response = requests.get(ETALONS_URL, stream=True)
        with open("etalons.zip", "wb") as f:
            for chunk in response.iter_content(8192):
                f.write(chunk)
        size = os.path.getsize("etalons.zip") if os.path.exists("etalons.zip") else 0
        print(f"[ETALONS] Downloaded: {size} bytes")
        print("[ETALONS] Extracting...")
        with zipfile.ZipFile("etalons.zip", "r") as zf:
            zf.extractall(".")
        print("[ETALONS] Extracted OK")
        os.remove("etalons.zip")
        if not os.path.exists("etalons"):
            for item in os.listdir("."):
                if os.path.isdir(item) and item.startswith("etalons"):
                    os.rename(item, "etalons")
                    print(f"[ETALONS] Renamed {item} -> etalons")
                    break
        n = len(os.listdir("etalons")) if os.path.exists("etalons") else 0
        print(f"[ETALONS] Done. Files: {n}")
    except Exception as e:
        print(f"[ETALONS] ERROR: {e}")
        import traceback
        traceback.print_exc()


def load_index():
    global index, image_paths
    if index is None:
        print("[INDEX] Loading FAISS index...")
        index = faiss.read_index(INDEX_PATH)
        with open(PATHS_PATH, "rb") as f:
            raw = pickle.load(f)
        image_paths = [os.path.join("photo_db", os.path.basename(p)) for p in raw]
        print(f"[INDEX] Index loaded, {len(image_paths)} images.")


def load_model():
    global embedder, transform
    if embedder is None:
        print("[MODEL] Loading YOLO...")
        try:
            model = YOLO(MODEL_PATH)
            torch_model = model.model.model
            embedder = torch.nn.Sequential(*list(torch_model.children())[:-1]).eval()
            transform = transforms.Compose([
                transforms.Resize((224, 224)),
                transforms.ToTensor(),
                transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
            ])
            print("[MODEL] Model loaded.")
        except Exception as e:
            print(f"[MODEL] ERROR: {e}")
            import traceback
            traceback.print_exc()
            embedder = None


def ensure_loaded():
    """Lazy-load: скачивает базы и загружает модель при первом вызове."""
    global index, image_paths, embedder, transform

    if not os.path.exists("photo_db") or len(os.listdir("photo_db")) == 0:
        download_and_extract_photos()

    if not os.path.exists("etalons") or len(os.listdir("etalons")) == 0:
        download_and_extract_etalons()

    if index is None:
        load_index()

    if embedder is None:
        load_model()

    if embedder is None:
        raise RuntimeError("Модель не загрузилась")


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
            return {"text": cat["text"].get(lang, cat["text"]["en"]),
                    "etalon_prefix": cat["etalon_prefix"],
                    "normative": cat["normative"].get(lang, cat["normative"]["en"]),
                    "normative_desc": cat.get("normative_desc", {}).get(lang, cat.get("normative_desc", {}).get("en", ""))}
    parts = name.split('_')
    for cat in CATEGORIES:
        if any(kp in parts for kp in cat["keyword"].split('_')):
            return {"text": cat["text"].get(lang, cat["text"]["en"]),
                    "etalon_prefix": cat["etalon_prefix"],
                    "normative": cat["normative"].get(lang, cat["normative"]["en"]),
                    "normative_desc": cat.get("normative_desc", {}).get(lang, cat.get("normative_desc", {}).get("en", ""))}
    return {"text": f"Unknown defect (file: {name})", "etalon_prefix": None, "normative": None, "normative_desc": ""}


def find_etalon(prefix):
    if not prefix or not os.path.exists("etalons"):
        return None
    for f in os.listdir("etalons"):
        if f.startswith(prefix) and f.lower().endswith(('.jpg', '.jpeg', '.png')):
            return os.path.join("etalons", f)
    return None


# ========== КЛАВИАТУРЫ ==========
def get_report_keyboard(lang):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(T[lang]['generate_order'], callback_data="generate_report")],
        [InlineKeyboardButton(T[lang].get('back_to_menu', '« Back to menu'), callback_data="main_menu")]
    ])


def get_language_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")],
        [InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru")],
        [InlineKeyboardButton("🇩🇪 Deutsch", callback_data="lang_de")],
        [InlineKeyboardButton("🇮🇹 Italiano", callback_data="lang_it")],
        [InlineKeyboardButton("🇫🇷 Français", callback_data="lang_fr")]
    ])


def get_main_menu_keyboard(lang):
    buttons = []
    if lang == "ru":
        buttons.append([InlineKeyboardButton(T[lang].get('smeta_button', '📊 Составить смету'), callback_data="menu_smeta")])
    buttons.append([InlineKeyboardButton(T[lang].get('check_photo_menu', '📷 Check photo'), callback_data="menu_photo")])
    buttons.append([InlineKeyboardButton(T[lang].get('balance_menu', '💰 Balance'), callback_data="menu_balance")])
    buttons.append([InlineKeyboardButton(T[lang].get('buy_menu', '💳 Buy stars'), callback_data="buy_checks")])
    buttons.append([InlineKeyboardButton(T[lang].get('change_lang', '🌐 Change language'), callback_data="change_lang")])
    return InlineKeyboardMarkup(buttons)


def get_buy_keyboard(lang):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(T[lang]['buy_button'], callback_data="buy_checks")],
        [InlineKeyboardButton(T[lang].get('back_to_menu', '« Back to menu'), callback_data="main_menu")]
    ])


def get_buy_packages_keyboard(lang):
    buttons = []
    for pkg in STAR_PACKAGES:
        if pkg["xtr"] and pkg["usdt"]:
            label = f"⭐ {pkg['stars']} ⭐ — {pkg['xtr']} Stars / 💎 {pkg['usdt']} USDT"
        elif pkg["xtr"]:
            label = f"⭐ {pkg['stars']} ⭐ — {pkg['xtr']} Stars"
        else:
            label = f"💎 {pkg['stars']} ⭐ — {pkg['usdt']} USDT"
        buttons.append([InlineKeyboardButton(label, callback_data=f"buy_pkg_{pkg['id']}")])
    buttons.append([InlineKeyboardButton(T[lang].get('back_to_menu', '« Back to menu'), callback_data="main_menu")])
    return InlineKeyboardMarkup(buttons)


def get_payment_method_keyboard(lang, pkg):
    buttons = []
    if pkg["xtr"]:
        buttons.append([InlineKeyboardButton(
            T[lang].get('buy_stars', '⭐ Pay {xtr} Stars').format(xtr=pkg["xtr"]),
            callback_data=f"pay_xtr_{pkg['id']}"
        )])
    if pkg["usdt"]:
        buttons.append([InlineKeyboardButton(
            T[lang].get('buy_usdt', '💎 Pay {usdt} USDT').format(usdt=pkg["usdt"]),
            callback_data=f"pay_usdt_{pkg['id']}"
        )])
    buttons.append([InlineKeyboardButton(T[lang].get('back_to_menu', '« Back'), callback_data="buy_checks")])
    return InlineKeyboardMarkup(buttons)


def generate_pdf_report(report_data, lang):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    for s in styles.byName:
        styles[s].fontName = FONT
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
            except:
                pass
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
        await update.message.reply_text(
            t['free_checks_used'] + "\n\n" + t['buy_text'],
            reply_markup=get_buy_keyboard(lang)
        )
        return

    try:
        await update.message.reply_text("⏳ Загружаю модель (первый раз, ~1 минута)...")
        ensure_loaded()
    except Exception as e:
        print(f"[LAZY] Error: {e}")
        import traceback
        traceback.print_exc()
        await update.message.reply_text("⚠️ Сервис временно недоступен. Попробуйте позже.")
        return

    photo = update.message.photo[-1]
    file = await photo.get_file()
    user_path = f"temp_{user_id}.jpg"
    await file.download_to_drive(user_path)
    emb = get_embedding(user_path)
    os.remove(user_path)
    if emb is None:
        await update.message.reply_text("⚠️ Service temporarily unavailable.")
        return
    emb = np.array([emb]).astype('float32')
    distances, indices = index.search(emb, 3)
    if len(indices[0]) == 0 or indices[0][0] == -1:
        await update.message.reply_text(t['no_match'])
        return
    use_check(user_id, PHOTO_PRICE_CHECKS)
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
            seen.add(key)
            unique.append(info)
            if len(unique) >= 3:
                break
    if not unique:
        await update.message.reply_text(t['no_match'])
        return
    response = t['defects_list'] + "\n"
    for i, d in enumerate(unique, 1):
        response += f"{i}. {d['text']}\n"
        if d.get('normative'):
            response += f"   {t['standard']} {d['normative']}\n"
        if d.get('normative_desc'):
            response += f"   → {d['normative_desc']}\n"
    if free_left > 0:
        response += f"\n{t['free_checks_left'].format(count=free_left)}"
    report_data = [{'text': d['text'], 'normative': d.get('normative'),
                    'normative_desc': d.get('normative_desc', ''),
                    'photo_path': review_path} for d in unique]
    save_session(user_id, report_data)
    context.user_data['report_data'] = report_data
    keyboard = get_report_keyboard(lang)
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
        await update.message.reply_text(t['pay_fail'])


async def safe_edit(query, text, **kwargs):
    try:
        await query.edit_message_text(text, **kwargs)
    except Exception as e:
        print(f"[SAFE_EDIT] edit failed: {e}")
        try:
            await query.message.reply_text(text, **kwargs)
        except Exception as e2:
            print(f"[SAFE_EDIT] reply failed: {e2}")


async def button_callback(update, context):
    query = update.callback_query
    try:
        await query.answer()
    except Exception as e:
        print(f"[CALLBACK] answer error: {e}")

    user_id = update.effective_user.id
    register_user(user_id)
    lang = get_lang(user_id)
    t = T[lang]
    data = query.data

    print(f"[CALLBACK] user={user_id} data={data}")

    try:
        if data == "main_menu":
            free, paid = get_balance(user_id)
            balance_line = f"\n\n💰 {t['balance_text'].format(free=free, paid=paid)}"
            await safe_edit(query, f"{t['welcome']}{balance_line}",
                            reply_markup=get_main_menu_keyboard(lang))
            return

        if data == "change_lang":
            await safe_edit(query, T[lang]['choose_language'], reply_markup=get_language_keyboard())
            return

        if data.startswith("lang_"):
            new_lang = data.split("_")[1]
            set_lang(user_id, new_lang)
            free, paid = get_balance(user_id)
            balance_line = f"\n\n💰 {T[new_lang]['balance_text'].format(free=free, paid=paid)}"
            await safe_edit(query, T[new_lang]['welcome'] + balance_line,
                            reply_markup=get_main_menu_keyboard(new_lang))
            return

        if data == "menu_balance":
            free, paid = get_balance(user_id)
            await safe_edit(query, t['balance_text'].format(free=free, paid=paid),
                            reply_markup=get_buy_keyboard(lang))
            return

        if data == "menu_photo":
            await safe_edit(query,
                f"📷 {t.get('check_photo_menu', 'Check photo')}\n\n"
                f"Send a photo of electrical installation — I'll find violations.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(t.get('back_to_menu', '« Back'), callback_data="main_menu")]
                ]))
            return

        if data == "menu_smeta":
            if lang != "ru":
                await safe_edit(query, t.get('smeta_only_ru', '⚠️ Estimates are only in Russian.'),
                                reply_markup=InlineKeyboardMarkup([
                                    [InlineKeyboardButton(t.get('back_to_menu', '« Back'), callback_data="main_menu")]
                                ]))
                return
            await safe_edit(query,
                "📊 <b>Составление смет</b>\n\n"
                "Пришли мне <b>PDF спецификации</b> (ЭОМ, ЭМ).\n\n"
                "• Первая <b>треть сметы — бесплатно</b>\n"
                "• Полная смета (все позиции + работы + НДС) — за <b>5 ⭐</b>\n\n"
                "📎 Пришли PDF-файл.",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("« Назад в меню", callback_data="main_menu")]
                ]))
            return

        if data == "buy_checks":
            free, paid = get_balance(user_id)
            balance_line = f"\n\n💰 {t['balance_text'].format(free=free, paid=paid)}"
            await safe_edit(query,
                f"{t.get('buy_welcome', '💳 Top up balance')}{balance_line}\n\n"
                f"⭐ Telegram Stars — мгновенно\n💎 USDT TRC20 — для крупных сумм",
                reply_markup=get_buy_packages_keyboard(lang))
            return

        if data.startswith("buy_pkg_"):
            pkg_id = data.replace("buy_pkg_", "")
            pkg = next((p for p in STAR_PACKAGES if p["id"] == pkg_id), None)
            if not pkg:
                return
            await safe_edit(query, f"Пакет: <b>{pkg['stars']} ⭐</b>\n\nВыбери способ оплаты:",
                            parse_mode="HTML",
                            reply_markup=get_payment_method_keyboard(lang, pkg))
            return

        if data.startswith("pay_xtr_"):
            pkg_id = data.replace("pay_xtr_", "")
            pkg = next((p for p in STAR_PACKAGES if p["id"] == pkg_id), None)
            if not pkg or not pkg["xtr"]:
                return
            try:
                await context.bot.send_invoice(
                    chat_id=user_id,
                    title=f"{pkg['stars']} ⭐",
                    description=f"Пополнение баланса на {pkg['stars']} звёзд",
                    payload=f"stars_{pkg['stars']}",
                    provider_token="",
                    currency="XTR",
                    prices=[LabeledPrice(label=f"{pkg['stars']} ⭐", amount=pkg["xtr"])],
                )
            except Exception as e:
                print(f"[STARS] Error: {e}")
                await query.message.reply_text(f"❌ Ошибка Stars: {e}")
            return

        if data.startswith("pay_usdt_"):
            pkg_id = data.replace("pay_usdt_", "")
            pkg = next((p for p in STAR_PACKAGES if p["id"] == pkg_id), None)
            if not pkg or not pkg["usdt"]:
                return
            amount = get_unique_amount(user_id, base=pkg["usdt"])
            text = t.get('usdt_amount',
                         '💎 Send EXACTLY {amount} USDT (TRC20) to:\n`{wallet}`\n\nAfter payment press the button.').format(
                amount=amount, wallet=USDT_WALLET)
            await safe_edit(query, text, parse_mode="Markdown",
                            reply_markup=InlineKeyboardMarkup([
                                [InlineKeyboardButton(t.get('pay_sent', '✅ I sent payment'), callback_data=f"usdt_sent_{pkg['id']}")],
                                [InlineKeyboardButton(t.get('back_to_menu', '« Back'), callback_data="buy_checks")]
                            ]))
            return

        if data.startswith("usdt_sent_"):
            pkg_id = data.replace("usdt_sent_", "")
            pkg = next((p for p in STAR_PACKAGES if p["id"] == pkg_id), None)
            if not pkg:
                return
            amount = get_unique_amount(user_id, base=pkg["usdt"])
            await safe_edit(query, t['pay_check'])
            txid, found = check_payment_by_user(user_id, amount, since_minutes=180)
            if txid:
                add_paid_checks(user_id, pkg["stars"])
                clear_pending(user_id)
                await safe_edit(query, t.get('usdt_success', '✅ USDT received! +{stars} ⭐').format(stars=pkg["stars"]))
            else:
                await safe_edit(query, t.get('usdt_not_found', '❌ Payment not found.'),
                                reply_markup=InlineKeyboardMarkup([
                                    [InlineKeyboardButton(t.get('back_to_menu', '« Back'), callback_data="buy_checks")]
                                ]))
            return

        if data == "generate_report":
            report_data = load_session(user_id) or context.user_data.get('report_data')
            if not report_data:
                await safe_edit(query, t['no_defects'])
                return
            pdf_buffer = generate_pdf_report(report_data, lang)
            fname = f"Order_{dt.datetime.now().strftime('%d.%m.%Y')}.pdf"
            if lang == "ru":
                fname = f"Предписание_{dt.datetime.now().strftime('%d.%m.%Y')}.pdf"
            elif lang == "de":
                fname = f"Anordnung_{dt.datetime.now().strftime('%d.%m.%Y')}.pdf"
            elif lang == "it":
                fname = f"Ordine_{dt.datetime.now().strftime('%d.%m.%Y')}.pdf"
            elif lang == "fr":
                fname = f"Ordre_{dt.datetime.now().strftime('%d.%m.%Y')}.pdf"
            await query.message.reply_document(document=pdf_buffer, filename=fname, caption=t['report_ready'])
            delete_session(user_id)
            context.user_data.pop('report_data', None)
            try:
                await query.delete_message()
            except:
                pass
            return

    except Exception as e:
        print(f"[CALLBACK] ERROR: {e}")
        import traceback
        traceback.print_exc()
        try:
            await query.message.reply_text(f"❌ Ошибка: {e}")
        except:
            pass


async def start_command(update, context):
    user_id = update.effective_user.id
    register_user(user_id)
    lang = get_lang(user_id)
    free, paid = get_balance(user_id)
    balance_line = f"\n\n💰 {T[lang]['balance_text'].format(free=free, paid=paid)}"
    await update.message.reply_text(
        T[lang]['welcome'] + balance_line,
        reply_markup=get_main_menu_keyboard(lang))


async def balance_command(update, context):
    user_id = update.effective_user.id
    register_user(user_id)
    lang = get_lang(user_id)
    free, paid = get_balance(user_id)
    await update.message.reply_text(
        T[lang]['balance_text'].format(free=free, paid=paid),
        reply_markup=get_buy_keyboard(lang))


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
    text = (f"📊 **Bot Statistics**\n\n"
            f"👥 Total users: {total}\n"
            f"📈 New today: {today}\n"
            f"📅 New this week: {week}\n"
            f"🔥 Active this week: {active}\n"
            f"💰 Total paid stars: {paid}\n"
            f"🎁 Free stars left: {free}")
    if top:
        text += "\n\n🏆 **Top paid users:**\n"
        for uid, p in top:
            text += f"• `{uid}` — {p} ⭐\n"
    await update.message.reply_text(text, parse_mode="Markdown")


async def addchecks_command(update, context):
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        await update.message.reply_text("⛔ Not authorized.")
        return
    args = context.args
    if len(args) != 2:
        await update.message.reply_text("Usage: /addchecks <user_id> <count>")
        return
    try:
        add_paid_checks(int(args[0]), int(args[1]))
        await update.message.reply_text(f"✅ Added {args[1]} ⭐ to user {args[0]}.")
    except:
        await update.message.reply_text("❌ Invalid arguments.")


async def resetchecks_command(update, context):
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        await update.message.reply_text("⛔ Not authorized.")
        return
    args = context.args
    if len(args) != 1:
        await update.message.reply_text("Usage: /resetchecks <user_id>")
        return
    try:
        reset_checks(int(args[0]))
        await update.message.reply_text(f"✅ Reset all stars for user {args[0]}.")
    except:
        await update.message.reply_text("❌ Invalid arguments.")


async def resetall_command(update, context):
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        await update.message.reply_text("⛔ Not authorized.")
        return
    reset_all_users()
    await update.message.reply_text("✅ Все пользователи обнулены: 5 бесплатных ⭐, 0 платных.")


async def buy_command(update, context):
    user_id = update.effective_user.id
    register_user(user_id)
    lang = get_lang(user_id)
    t = T[lang]
    free, paid = get_balance(user_id)
    balance_line = f"\n\n💰 {t['balance_text'].format(free=free, paid=paid)}"
    await update.message.reply_text(
        f"{t.get('buy_welcome', '💳 Top up balance')}{balance_line}\n\n"
        f"⭐ Telegram Stars — мгновенно\n💎 USDT TRC20 — для крупных сумм",
        reply_markup=get_buy_packages_keyboard(lang))


async def smeta_command(update, context):
    user_id = update.effective_user.id
    register_user(user_id)
    lang = get_lang(user_id)
    if lang != "ru":
        await update.message.reply_text(
            T[lang].get('smeta_only_ru', '⚠️ Estimates are only in Russian.'),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(T[lang].get('back_to_menu', '« Back'), callback_data="main_menu")]
            ]))
        return
    await update.message.reply_text(
        "📊 <b>Составление смет</b>\n\n"
        "Пришли мне <b>PDF спецификации</b> (ЭОМ, ЭМ).\n\n"
        "• Первая <b>треть сметы — бесплатно</b>\n"
        "• Полная смета (все позиции + работы + НДС) — за <b>5 ⭐</b>\n\n"
        "📎 Пришли PDF-файл.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("« Назад в меню", callback_data="main_menu")]
        ]))


# ========== SMETA PIPELINE ==========
def _format_money(value):
    try:
        return f"{value:,.2f}".replace(",", " ")
    except Exception:
        return str(value)


def _safe_float(val):
    if val is None:
        return 0.0
    try:
        if isinstance(val, str):
            val = val.replace(" ", "").replace("\xa0", "").replace(",", ".")
        return float(val)
    except (ValueError, TypeError):
        return 0.0


def _run_smeta_pipeline_sync(pdf_path, out_dir):
    import pandas as pd
    import parse_spec as ps
    import make_smeta_eom as mse
    import make_smeta_works as msw
    from pathlib import Path

    spec_xlsx = os.path.join(out_dir, "spec_materials.xlsx")
    smeta_materials = os.path.join(out_dir, "smeta_eom_materials.xlsx")
    smeta_full = os.path.join(out_dir, "smeta_eom_full.xlsx")

    ps.PDF_PATH = Path(pdf_path)
    ps.OUT_XLSX = Path(spec_xlsx)
    mse.IN_XLSX = Path(spec_xlsx)
    mse.OUT_XLSX = Path(smeta_materials)
    msw.IN_XLSX = Path(smeta_materials)
    msw.OUT_XLSX = Path(smeta_full)

    items = ps.extract_spec(ps.PDF_PATH)
    if not items:
        raise ValueError("Не удалось распарсить спецификацию")

    df = pd.DataFrame(items)
    df["Позиция"] = df["Позиция"].astype(str)
    df.to_excel(spec_xlsx, index=False)

    old_argv = sys.argv
    sys.argv = ["make_smeta_eom.py", "--fast"]
    try:
        mse.main()
    finally:
        sys.argv = old_argv

    msw.main()

    df_full = pd.read_excel(smeta_full, sheet_name="Сводка")

    def _get_val(pat):
        exact = df_full[df_full["Статья"].astype(str).str.strip() == pat]
        if len(exact) > 0:
            return _safe_float(exact["Сумма, руб"].iloc[0])
        row = df_full[df_full["Статья"].astype(str).str.contains(pat, na=False)]
        if len(row) == 0:
            return 0.0
        val = row["Сумма, руб"].iloc[0]
        return _safe_float(val)

    return {
        "smeta_materials": smeta_materials,
        "smeta_full": smeta_full,
        "materials_total": _get_val("Итого материалы"),
        "works_total": _get_val("Итого работы"),
        "vat_total": _get_val("НДС"),
        "grand_total": _get_val("ВСЕГО") or _get_val("подытог") + _get_val("НДС"),
    }


def _get_free_part_text(smeta_materials_path, lang):
    import pandas as pd
    try:
        df = pd.read_excel(smeta_materials_path, dtype={"Позиция": str, "Код": str})
    except Exception as e:
        return f"Ошибка чтения: {e}"

    df_items = df[df["Сумма, руб"].notna()].copy()
    total_items = len(df_items)
    if total_items == 0:
        return "Не удалось найти цены."

    free_count = max(1, int(total_items * 0.33))
    _key = hashlib.md5("|".join(sorted(df_items["Наименование"].astype(str))).encode("utf-8")).hexdigest()
    _rng = random.Random(int(_key[:8], 16))
    _idx = sorted(_rng.sample(range(total_items), free_count))
    free_df = df_items.iloc[_idx]

    lines = []
    for i, (_, r) in enumerate(free_df.iterrows(), 1):
        name = str(r["Наименование"])[:60]
        qty = r["Кол-во"]
        unit = r["Ед."]
        price = r["Цена ед., руб"]
        total = r["Сумма, руб"]
        lines.append(
            f"{i}. {name}\n"
            f"   💰 {_format_money(price)} ₽/{unit} × {qty} = <b>{_format_money(total)} ₽</b>\n"
        )

    text = "📊 <b>Бесплатная часть сметы</b> (1/3 позиций)\n\n"
    text += "\n".join(lines)
    text += (
        f"\n\n🔒 <b>Полная смета</b> содержит:\n"
        f"• Все <b>{total_items}</b> позиций материалов\n"
        f"• Работы (прокладка, монтаж лотков, муфт, щитов)\n"
        f"• Коэффициенты (высота, ночь, действующий объект)\n"
        f"• Наценки и НДС\n\n"
        f"💰 Цена: <b>5 ⭐</b>\n"
        f"📎 Excel-файл с 3 листами (Материалы / Работы / Сводка)"
    )
    return text


async def handle_smeta_pdf(update, context):
    user_id = update.effective_user.id
    register_user(user_id)
    lang = get_lang(user_id)

    if lang != "ru":
        await update.message.reply_text(
            T[lang].get('smeta_only_ru', '⚠️ Estimates are only in Russian.'))
        return

    doc = update.message.document
    if not doc or not doc.file_name.lower().endswith(".pdf"):
        return

    if doc.file_size and doc.file_size > 20 * 1024 * 1024:
        await update.message.reply_text("❌ Файл больше 20 МБ. Пришли PDF поменьше.")
        return

    base_dir = "/data/smeta_temp" if os.path.exists("/data") else "smeta_temp"
    user_dir = os.path.join(base_dir, str(user_id))
    os.makedirs(user_dir, exist_ok=True)
    pdf_path = os.path.join(user_dir, "spec.pdf")
    project_name = doc.file_name.rsplit(".", 1)[0][:60] if doc.file_name else "Проект"
    with open(os.path.join(user_dir, "project_name.txt"), "w", encoding="utf-8") as _pn:
        _pn.write(project_name)

    await update.message.reply_text(
        "⏳ <b>Принял PDF.</b> Обрабатываю...\n\n"
        "1. Парсинг спецификации\n"
        "2. Поиск цен на ЭТМ (~5-10 минут)\n"
        "3. Расчёт работ и НДС\n\n"
        "<b>Пришлю результат, когда будет готово.</b>",
        parse_mode="HTML")

    try:
        file = await doc.get_file()
        await file.download_to_drive(pdf_path)
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка скачивания: {e}")
        return

    asyncio.create_task(_run_smeta_task(update, context, user_id, lang, pdf_path, user_dir))


def _project_name(user_dir):
    try:
        with open(os.path.join(user_dir, "project_name.txt"), encoding="utf-8") as f:
            return f.read().strip() or "Проект"
    except Exception:
        return "Проект"


async def _run_smeta_task(update, context, user_id, lang, pdf_path, user_dir):
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, _run_smeta_pipeline_sync, pdf_path, user_dir)
    except Exception as e:
        print(f"[SMETA] Pipeline error: {e}")
        import traceback
        traceback.print_exc()
        await update.message.reply_text(f"❌ Ошибка обработки: {e}")
        return

    free, paid = get_balance(user_id)
    total_checks = free + paid
    free_text = _get_free_part_text(result["smeta_materials"], lang)

    if total_checks >= SMETA_PRICE_CHECKS:
        use_check(user_id, SMETA_PRICE_CHECKS)

        summary = (
            f"✅ <b>Смета готова!</b>\n\n"
            f"📁 <b>Проект:</b> {_project_name(user_dir)}\n\n"
            f"📊 <b>Итого:</b>\n"
            f"• Материалы: <b>{_format_money(result['materials_total'])} ₽</b>\n"
            f"• Работы: <b>{_format_money(result['works_total'])} ₽</b>\n"
            f"• НДС 20%: <b>{_format_money(result['vat_total'])} ₽</b>\n"
            f"• <b>ВСЕГО: {_format_money(result['grand_total'])} ₽</b>\n\n"
            f"📎 Excel-файл ниже (3 листа)."
        )
        await update.message.reply_text(summary, parse_mode="HTML")

        try:
            with open(result["smeta_full"], "rb") as f:
                await update.message.reply_document(
                    document=f,
                    filename=f"{_project_name(user_dir)[:40]}_{dt.datetime.now().strftime('%Y%m%d')}.xlsx",
                    caption="✅ Смета готова. Спасибо за использование!")
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка отправки файла: {e}")

        try:
            shutil.rmtree(user_dir, ignore_errors=True)
        except:
            pass
    else:
        not_enough = (
            f"⚠️ Недостаточно звёзд для полной сметы.\n\n"
            f"Нужно: <b>5 ⭐</b>\n"
            f"У вас: <b>{total_checks} ⭐</b>"
        )
        buy_text = T[lang].get('buy_button', '💳 Купить звёзды')
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(buy_text, callback_data="buy_checks")],
            [InlineKeyboardButton(T[lang].get('back_to_menu', '« Назад'), callback_data="main_menu")]
        ])
        await update.message.reply_text(
            free_text + "\n\n" + not_enough,
            parse_mode="HTML",
            reply_markup=keyboard)


async def handle_pre_checkout(update, context):
    query = update.pre_checkout_query
    try:
        await query.answer(ok=True)
    except Exception as e:
        print(f"Pre-checkout error: {e}")


async def handle_successful_payment(update, context):
    user_id = update.effective_user.id
    payment = update.message.successful_payment
    payload = payment.invoice_payload
    try:
        stars = int(payload.split("_")[1])
    except (IndexError, ValueError):
        stars = 0
    if stars > 0:
        add_paid_checks(user_id, stars)
        lang = get_lang(user_id)
        await update.message.reply_text(
            T[lang].get('stars_success', '✅ Paid! +{stars} ⭐').format(stars=stars),
            parse_mode="HTML")


if __name__ == "__main__":
    init_db()
    print("[START] DB initialized. Bot starting...")

    app = Application.builder().token(TOKEN).read_timeout(60).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("menu", start_command))
    app.add_handler(CommandHandler("balance", balance_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("review", review_command))
    app.add_handler(CommandHandler("addchecks", addchecks_command))
    app.add_handler(CommandHandler("resetchecks", resetchecks_command))
    app.add_handler(CommandHandler("resetall", resetall_command))
    app.add_handler(CommandHandler("buy", buy_command))
    app.add_handler(CommandHandler("smeta", smeta_command))

    app.add_handler(PreCheckoutQueryHandler(handle_pre_checkout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, handle_successful_payment))

    app.add_handler(MessageHandler(filters.Document.PDF, handle_smeta_pdf))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_txid))
    app.add_handler(CallbackQueryHandler(button_callback))

    print("🚀 Bot started (FINAL + SMETA + STARS) — lazy-load mode.")
    app.run_polling()