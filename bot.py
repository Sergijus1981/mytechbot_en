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

TOKEN = "8993796250:AAFWDsfKuc4Bvha2ED-fvUyONlQ_iiNpCCk"

PHOTO_DB_URL = "https://github.com/Sergijus1981/mytechbot/releases/download/v1.0.0/photo_db.zip"
ETALONS_URL = "https://github.com/Sergijus1981/mytechbot/releases/download/v1.0.0/etalons.zip"

INDEX_PATH = "faiss_index.bin"
PATHS_PATH = "image_paths.pkl"
MODEL_PATH = "best.pt"
OWNER_ID = 8743362338

T = {
    "en": {
        "welcome": "Hello! 👋\nI'm a technical inspection bot. Send me a photo of electrical installation, and I'll find possible violations.\n\nJust send a photo!",
        "language_set": "✅ Language set to English.",
        "defect_found": "🔍 **Defect found:**",
        "standard": "📜 Standard:",
        "no_match": "❌ No similar examples found.",
        "report_ready": "📄 Your order is ready!",
        "no_defects": "📭 No defects recorded.",
        "review_empty": "📭 Review folder is empty.",
        "review_photos_found": "📸 Found {count} photos.",
        "review_done": "✅ All photos sent.",
        "stats": "📊 Bot Statistics:\n👥 Total users: {total}\n📈 New today: {today}\n📅 New this week: {week}",
        "stats_unauthorized": "⛔ Not authorized.",
        "choose_language": "🌐 Choose your language:",
        "report_action": "🛠 Recommended action: bring into compliance with RTD.",
        "defects_list": "🔍 Found defects:",
        "generate_order": "📄 Generate order",
        "classify_prompt": "📸 Classify this photo:",
        "classify_success": "✅ Photo added to {category}",
        "classify_skipped": "⏭️ Skipped",
        "classify_rejected": "❌ Rejected and deleted",
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
        "violation_photo": "Violation photo"
    },
    "ru": {
        "welcome": "Привет! 👋\nЯ бот технической инспекции. Отправь мне фото электроустановки, и я найду возможные нарушения.\n\nПросто отправь фото!",
        "language_set": "✅ Язык установлен на русский.",
        "defect_found": "🔍 **Найдено замечание:**",
        "standard": "📜 Норматив:",
        "no_match": "❌ Похожих примеров не найдено.",
        "report_ready": "📄 Ваше предписание готово!",
        "no_defects": "📭 Нет замечаний.",
        "review_empty": "📭 Папка review пуста.",
        "review_photos_found": "📸 Найдено {count} фото.",
        "review_done": "✅ Все фото отправлены.",
        "stats": "📊 Статистика бота:\n👥 Всего пользователей: {total}\n📈 Новых сегодня: {today}\n📅 За неделю: {week}",
        "stats_unauthorized": "⛔ Вы не авторизованы.",
        "choose_language": "🌐 Выберите язык:",
        "report_action": "🛠 Привести в соответствие с НТД.",
        "defects_list": "🔍 Найдены замечания:",
        "generate_order": "📄 Сформировать предписание",
        "classify_prompt": "📸 Классифицируйте это фото:",
        "classify_success": "✅ Фото добавлено в {category}",
        "classify_skipped": "⏭️ Пропущено",
        "classify_rejected": "❌ Отклонено",
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
        "violation_photo": "Фото нарушения"
    },
    "es": {
        "welcome": "¡Hola! 👋\nSoy un bot de inspección técnica. Envíame una foto de una instalación eléctrica y encontraré posibles infracciones.\n\n¡Solo envía una foto!",
        "language_set": "✅ Idioma configurado al español.",
        "defect_found": "🔍 **Defecto encontrado:**",
        "standard": "📜 Normativa:",
        "no_match": "❌ No se encontraron ejemplos similares.",
        "report_ready": "📄 ¡Su orden está lista!",
        "no_defects": "📭 No hay defectos.",
        "review_empty": "📭 La carpeta de revisión está vacía.",
        "review_photos_found": "📸 Encontradas {count} fotos.",
        "review_done": "✅ Todas las fotos enviadas.",
        "stats": "📊 Estadísticas:\n👥 Usuarios: {total}\n📈 Nuevos hoy: {today}\n📅 Semana: {week}",
        "stats_unauthorized": "⛔ No autorizado.",
        "choose_language": "🌐 Elige tu idioma:",
        "report_action": "🛠 Acción recomendada: cumplir con NTD.",
        "defects_list": "🔍 Defectos encontrados:",
        "generate_order": "📄 Generar orden",
        "classify_prompt": "📸 Clasifica esta foto:",
        "classify_success": "✅ Foto añadida a {category}",
        "classify_skipped": "⏭️ Omitida",
        "classify_rejected": "❌ Rechazada",
        "order_title": "ORDEN",
        "issue_date": "Fecha de emisión:",
        "defect": "Defecto",
        "standard_label": "Normativa:",
        "deadline": "Plazo de corrección: _______________",
        "issued_by": "EMITIDO POR:",
        "company": "Compañía: ___________________",
        "position": "Cargo: _________________",
        "full_name": "Nombre completo: _______________________",
        "signature": "Firma: ___________________",
        "received_by": "RECIBIDO POR:",
        "violation_photo": "Foto de la infracción"
    },
    "sw": {
        "welcome": "Habari! 👋\nMimi ni bot ya ukaguzi wa kiufundi. Nitume picha ya usakinishaji wa umeme, nami nitapata kasoro zinazowezekana.\n\nTuma picha tu!",
        "language_set": "✅ Lugha imewekwa Kiswahili.",
        "defect_found": "🔍 **Kasoro imepatikana:**",
        "standard": "📜 Kiwango:",
        "no_match": "❌ Hakuna mifano sawa iliyopatikana.",
        "report_ready": "📄 Agizo lako liko tayari!",
        "no_defects": "📭 Hakuna kasoro zilizorekodiwa.",
        "review_empty": "📭 Folda ya ukaguzi haina picha.",
        "review_photos_found": "📸 Picha {count} zimepatikana.",
        "review_done": "✅ Picha zote zimetumwa.",
        "stats": "📊 Takwimu:\n👥 Jumla ya watumiaji: {total}\n📈 Wapya leo: {today}\n📅 Wiki hii: {week}",
        "stats_unauthorized": "⛔ Hauruhusiwi.",
        "choose_language": "🌐 Chagua lugha yako:",
        "report_action": "🛠 Hatua inayopendekezwa: leta katika kiwango.",
        "defects_list": "🔍 Kasoro zilizopatikana:",
        "generate_order": "📄 Tengeneza agizo",
        "classify_prompt": "📸 Ainisha picha hii:",
        "classify_success": "✅ Picha imeongezwa kwenye {category}",
        "classify_skipped": "⏭️ Imerukwa",
        "classify_rejected": "❌ Imekataliwa",
        "order_title": "AGIZO",
        "issue_date": "Tarehe ya kutolewa:",
        "defect": "Kasoro",
        "standard_label": "Kiwango:",
        "deadline": "Tarehe ya mwisho wa kurekebisha: _______________",
        "issued_by": "ILITOA AGIZO:",
        "company": "Kampuni: ___________________",
        "position": "Nafasi: _________________",
        "full_name": "Jina kamili: _______________________",
        "signature": "Sahihi: ___________________",
        "received_by": "ALIPOKEA:",
        "violation_photo": "Picha ya ukiukaji"
    }
}

CATEGORIES = [
    {"keyword":"01_otsutstvuyut_birki", "etalon_prefix":"birki_etalon", "label_ru":"Бирки", "label_en":"Labels", "label_es":"Etiquetas", "label_sw":"Lebsi",
     "text":{"en":"⚠️ Missing cable/equipment labels.", "ru":"⚠️ Отсутствуют бирки на оборудовании.", "es":"⚠️ Faltan etiquetas en cables/equipos.", "sw":"⚠️ Lebsi za nyaya/vifaa hazipo."},
     "normative":{"en":"IEC 60445, NEC 110.22, BS 7671 514.9", "ru":"ПУЭ п. 2.3.23, СП 76.13330.2016 п. 6.4.8", "es":"IEC 60445, NEC 110.22, BS 7671 514.9", "sw":"IEC 60445, NEC 110.22, BS 7671 514.9"}},
    {"keyword":"02_zadelka_prohodok", "etalon_prefix":"prohodki_etalon", "label_ru":"Проходки", "label_en":"Penetrations", "label_es":"Penetraciones", "label_sw":"Mipenyo",
     "text":{"en":"⚠️ Gaps in penetrations not sealed.", "ru":"⚠️ Не выполнена заделка проходок.", "es":"⚠️ Brechas en penetraciones sin sellar.", "sw":"⚠️ Mipenyo haijafungwa vizuri."},
     "normative":{"en":"IEC 60364-5-52, NEC 300.21, BS 7671 527.2", "ru":"СП 76.13330.2016 п. 6.4.1.25", "es":"IEC 60364-5-52, NEC 300.21, BS 7671 527.2", "sw":"IEC 60364-5-52, NEC 300.21, BS 7671 527.2"}},
    {"keyword":"03_zazemlenie_ne_vypolneno", "etalon_prefix":"zazemlenie_etalon", "label_ru":"Заземление", "label_en":"Earthing", "label_es":"Puesta a tierra", "label_sw":"Kutuliza",
     "text":{"en":"⚠️ Earthing not provided.", "ru":"⚠️ Не выполнено заземление.", "es":"⚠️ No se proporciona puesta a tierra.", "sw":"⚠️ Kutuliza haijafanywa."},
     "normative":{"en":"IEC 60364-4-41, NEC 250.4, BS 7671 411.3", "ru":"ПУЭ п. 1.7.76", "es":"IEC 60364-4-41, NEC 250.4, BS 7671 411.3", "sw":"IEC 60364-4-41, NEC 250.4, BS 7671 411.3"}},
    {"keyword":"04_shpilki_lotka_ne_srezany", "etalon_prefix":"shpilki_etalon", "label_ru":"Шпильки", "label_en":"Studs", "label_es":"Espárragos", "label_sw":"Boliti",
     "text":{"en":"⚠️ Cable tray studs not trimmed.", "ru":"⚠️ Шпильки лотка не срезаны.", "es":"⚠️ Espárragos de bandeja no recortados.", "sw":"⚠️ Boliti za trei za nyaya hazijakatwa."},
     "normative":{"en":"IEC 61537, NEC 392.18, BS 7671 522.8", "ru":"ГОСТ Р 50571.5.52-2011", "es":"IEC 61537, NEC 392.18, BS 7671 522.8", "sw":"IEC 61537, NEC 392.18, BS 7671 522.8"}},
    {"keyword":"05_oksidy_rzhavchina", "etalon_prefix":"oksidy_etalon", "label_ru":"Окислы", "label_en":"Oxidation", "label_es":"Oxidación", "label_sw":"Oksidi/kutu",
     "text":{"en":"⚠️ Oxidation/rust on contacts.", "ru":"⚠️ Окислы y ржавчина на контактах.", "es":"⚠️ Oxidación/óxido en contactos.", "sw":"⚠️ Oksidi/kutu kwenye viungo."},
     "normative":{"en":"IEC 60204-1, NEC 110.12", "ru":"ПУЭ п. 1.8.4, ГОСТ 10434-82", "es":"IEC 60204-1, NEC 110.12", "sw":"IEC 60204-1, NEC 110.12"}},
    {"keyword":"06_otsutstvie_shemy", "etalon_prefix":"shema_etalon", "label_ru":"Схема", "label_en":"Diagram", "label_es":"Diagrama", "label_sw":"Mchoro",
     "text":{"en":"⚠️ Single-line diagram missing.", "ru":"⚠️ Отсутствует однолинейная схема.", "es":"⚠️ Falta el diagrama unifilar.", "sw":"⚠️ Mchoro wa mstari mmoja haupo."},
     "normative":{"en":"IEC 61082-1, NEC 110.22", "ru":"ПУЭ п. 1.8.4, СП 76.13330.2016 п. 6.4.8", "es":"IEC 61082-1, NEC 110.22", "sw":"IEC 61082-1, NEC 110.22"}}
]

def init_db():
    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        first_seen TEXT,
        last_seen TEXT,
        language TEXT DEFAULT "en"
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS sessions (
        user_id INTEGER,
        report_data TEXT,
        created_at TEXT,
        PRIMARY KEY (user_id)
    )''')
    conn.commit()
    conn.close()

def register_user(user_id):
    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    now = dt.datetime.now().isoformat()
    c.execute("INSERT OR IGNORE INTO users (user_id, first_seen, last_seen, language) VALUES (?, ?, ?, 'en')", (user_id, now, now))
    c.execute("UPDATE users SET last_seen = ? WHERE user_id = ?", (now, user_id))
    conn.commit()
    conn.close()

def get_lang(user_id):
    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    r = c.execute("SELECT language FROM users WHERE user_id = ?", (user_id,)).fetchone()
    conn.close()
    if r and r[0]:
        return r[0]
    return "en"

def set_lang(user_id, lang):
    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    c.execute("UPDATE users SET language = ? WHERE user_id = ?", (lang, user_id))
    conn.commit()
    conn.close()

def get_stats():
    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    total = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    today = dt.datetime.now().date().isoformat()
    today_count = c.execute("SELECT COUNT(*) FROM users WHERE date(first_seen) = ?", (today,)).fetchone()[0]
    week_ago = (dt.datetime.now() - timedelta(days=7)).date().isoformat()
    week_count = c.execute("SELECT COUNT(*) FROM users WHERE date(first_seen) >= ?", (week_ago,)).fetchone()[0]
    conn.close()
    return total, today_count, week_count

def save_session(user_id, report_data):
    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    data_json = json.dumps(report_data)
    c.execute("INSERT OR REPLACE INTO sessions (user_id, report_data, created_at) VALUES (?, ?, ?)", (user_id, data_json, dt.datetime.now().isoformat()))
    conn.commit()
    conn.close()

def load_session(user_id):
    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    r = c.execute("SELECT report_data FROM sessions WHERE user_id = ?", (user_id,)).fetchone()
    conn.close()
    if r:
        return json.loads(r[0])
    return None

def delete_session(user_id):
    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    c.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
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
        print("📁 photo_db already exists, skipping download.")
        return
    print("📥 Downloading photo_db.zip...")
    gdown.download(PHOTO_DB_URL, "photo_db.zip", quiet=False)
    with zipfile.ZipFile("photo_db.zip", "r") as zf:
        zf.extractall(".")
    os.remove("photo_db.zip")
    if not os.path.exists("photo_db"):
        for item in os.listdir("."):
            if os.path.isdir(item) and item.startswith("photo_db"):
                os.rename(item, "photo_db")
                break
    print(f"✅ photo_db ready, files: {len(os.listdir('photo_db'))}")

def download_and_extract_etalons():
    if os.path.exists("etalons") and len(os.listdir("etalons")) > 0:
        print("📁 etalons already exists, skipping download.")
        return
    print("📥 Downloading etalons.zip...")
    response = requests.get(ETALONS_URL, stream=True)
    with open("etalons.zip", "wb") as f:
        for chunk in response.iter_content(8192):
            f.write(chunk)
    with zipfile.ZipFile("etalons.zip", "r") as zf:
        zf.extractall(".")
    os.remove("etalons.zip")
    if not os.path.exists("etalons"):
        for item in os.listdir("."):
            if os.path.isdir(item) and item.startswith("etalons"):
                os.rename(item, "etalons")
                break
    print(f"✅ etalons ready, files: {len(os.listdir('etalons'))}")

def rebuild_index():
    print("🔄 Rebuilding index...")
    subprocess.run(["python", "index_builder.py"], check=True)
    load_index()

def load_index():
    global index, image_paths
    if index is None:
        index = faiss.read_index(INDEX_PATH)
        with open(PATHS_PATH, "rb") as f:
            raw = pickle.load(f)
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
        return np.random.rand(128).astype('float32')
    img = Image.open(image_path).convert('RGB')
    img_tensor = transform(img).unsqueeze(0)
    with torch.no_grad():
        return embedder(img_tensor).flatten().cpu().numpy()

def get_category_info(filename, lang):
    name = os.path.basename(filename)
    for cat in CATEGORIES:
        if name.startswith(cat["keyword"]):
            return {
                "text": cat["text"].get(lang, cat["text"]["en"]),
                "etalon_prefix": cat["etalon_prefix"],
                "normative": cat["normative"].get(lang, cat["normative"]["en"])
            }
    parts = name.split('_')
    for cat in CATEGORIES:
        if any(kp in parts for kp in cat["keyword"].split('_')):
            return {
                "text": cat["text"].get(lang, cat["text"]["en"]),
                "etalon_prefix": cat["etalon_prefix"],
                "normative": cat["normative"].get(lang, cat["normative"]["en"])
            }
    return {
        "text": f"Unknown defect (file: {name})" if lang=="en" else f"Desconocido (archivo: {name})" if lang=="es" else f"Неизвестное замечание (файл: {name})" if lang=="ru" else f"Kasoro isiyojulikana (faili: {name})",
        "etalon_prefix": None,
        "normative": None
    }

def find_etalon(prefix):
    if not prefix:
        return None
    etalon_dir = "etalons"
    if not os.path.exists(etalon_dir):
        return None
    for f in os.listdir(etalon_dir):
        if f.startswith(prefix) and f.lower().endswith(('.jpg', '.jpeg', '.png')):
            return os.path.join(etalon_dir, f)
    return None

def get_report_keyboard(lang):
    return InlineKeyboardMarkup([[InlineKeyboardButton(T[lang]['generate_order'], callback_data="generate_report")]])

def get_language_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")],
        [InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru")],
        [InlineKeyboardButton("🇪🇸 Español", callback_data="lang_es")],
        [InlineKeyboardButton("🇰🇪 Kiswahili", callback_data="lang_sw")]
    ])

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
        photo_path = report_data[0].get('photo_path') if report_data else None
        for i, item in enumerate(report_data, 1):
            story.append(Paragraph(f"<b>{t['defect']} #{i}</b>", styles['Heading2']))
            story.append(Paragraph(f"📌 {item.get('text', '')}", styles['Normal']))
            story.append(Paragraph(f"{t['standard_label']} {item.get('normative', '—')}", styles['Normal']))
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
    load_index()
    load_model()

    photo = update.message.photo[-1]
    file = await photo.get_file()
    user_path = f"temp_{user_id}.jpg"
    await file.download_to_drive(user_path)
    emb = get_embedding(user_path)
    os.remove(user_path)
    emb = np.array([emb]).astype('float32')
    distances, indices = index.search(emb, 3)

    if len(indices[0]) == 0 or indices[0][0] == -1:
        await update.message.reply_text(t['no_match'])
        return

    review_dir = "review"
    os.makedirs(review_dir, exist_ok=True)
    timestamp = dt.datetime.now().strftime('%Y%m%d_%H%M%S')
    review_path = os.path.join(review_dir, f"{timestamp}.jpg")
    await file.download_to_drive(review_path)
    print(f"Saved review: {review_path}")

    unique = []
    seen = set()
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

    report_data = [{
        'text': d['text'],
        'normative': d.get('normative'),
        'photo_path': review_path
    } for d in unique]
    save_session(user_id, report_data)
    context.user_data['report_data'] = report_data

    etalon_path = find_etalon(unique[0].get("etalon_prefix"))
    if etalon_path and os.path.exists(etalon_path):
        with open(etalon_path, 'rb') as f:
            await update.message.reply_photo(photo=f, caption=response, reply_markup=get_report_keyboard(lang))
    else:
        await update.message.reply_text(response, reply_markup=get_report_keyboard(lang))

async def button_callback(update, context):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    register_user(user_id)
    lang = get_lang(user_id)
    t = T[lang]
    data = query.data

    if data == "generate_report":
        report_data = load_session(user_id) or context.user_data.get('report_data')
        if not report_data:
            await query.edit_message_text(t['no_defects'])
            return
        pdf_buffer = generate_pdf_report(report_data, lang)
        await query.message.reply_document(
            document=pdf_buffer,
            filename=f"Предписание_{dt.datetime.now().strftime('%d.%m.%Y')}.pdf" if lang=="ru" else f"Order_{dt.datetime.now().strftime('%d.%m.%Y')}.pdf" if lang=="en" else f"Orden_{dt.datetime.now().strftime('%d.%m.%Y')}.pdf" if lang=="es" else f"Agizo_{dt.datetime.now().strftime('%d.%m.%Y')}.pdf",
            caption=t['report_ready']
        )
        delete_session(user_id)
        context.user_data.pop('report_data', None)
        await query.delete_message()
        return

    if data.startswith("lang_"):
        new_lang = data.split("_")[1]
        set_lang(user_id, new_lang)
        await query.edit_message_text(T[new_lang]['welcome'])
        return

    if data.startswith("classify_"):
        action = data.split("_", 1)[1]
        if 'review_photos' not in context.user_data or not context.user_data['review_photos']:
            await query.edit_message_text("❌ No photos left.")
            return
        photo_path = context.user_data['review_photos'].pop(0)
        if action == "skip":
            await query.edit_message_text(t['classify_skipped'])
        elif action == "reject":
            if os.path.exists(photo_path):
                os.remove(photo_path)
            await query.edit_message_text(t['classify_rejected'])
        else:
            cat = next((c for c in CATEGORIES if c["keyword"] == action), None)
            if not cat:
                await query.edit_message_text("❌ Unknown category.")
                return
            target = os.path.join("photo_db", cat["keyword"])
            os.makedirs(target, exist_ok=True)
            new_name = f"{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
            new_path = os.path.join(target, new_name)
            shutil.copy2(photo_path, new_path)
            if os.path.exists(photo_path):
                os.remove(photo_path)
            rebuild_index()
            await query.edit_message_text(t['classify_success'].format(
                category=cat["label_ru"] if lang=="ru" else cat["label_en"] if lang=="en" else cat["label_es"] if lang=="es" else cat["label_sw"]
            ))
        if context.user_data['review_photos']:
            next_photo = context.user_data['review_photos'][0]
            with open(next_photo, 'rb') as f:
                await query.message.reply_photo(photo=f, caption=t['classify_prompt'], reply_markup=get_language_keyboard())
        else:
            await query.message.reply_text(t['review_done'])
        return

async def start_command(update, context):
    user_id = update.effective_user.id
    register_user(user_id)
    lang = get_lang(user_id)
    await update.message.reply_text(T[lang]['choose_language'], reply_markup=get_language_keyboard())

async def review_command(update, context):
    user_id = update.effective_user.id
    register_user(user_id)
    lang = get_lang(user_id)
    t = T[lang]
    review_dir = "review"
    if not os.path.exists(review_dir):
        os.makedirs(review_dir, exist_ok=True)
        await update.message.reply_text(t['review_empty'])
        return
    photos = []
    for root, _, files in os.walk(review_dir):
        for f in files:
            if f.lower().endswith(('.jpg', '.jpeg', '.png')):
                photos.append(os.path.join(root, f))
    if not photos:
        await update.message.reply_text(t['review_empty'])
        return
    await update.message.reply_text(t['review_photos_found'].format(count=len(photos)))
    for path in photos:
        try:
            with open(path, 'rb') as f:
                await update.message.reply_photo(photo=f)
        except Exception as e:
            print(f"❌ Error sending {path}: {e}")
            await update.message.reply_text(f"❌ Could not send: {os.path.basename(path)}")
    await update.message.reply_text(t['review_done'])

async def stats_command(update, context):
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        lang = get_lang(user_id)
        await update.message.reply_text(T[lang]['stats_unauthorized'])
        return
    total, today, week = get_stats()
    lang = get_lang(user_id)
    await update.message.reply_text(T[lang]['stats'].format(total=total, today=today, week=week))

if __name__ == "__main__":
    init_db()
    download_and_extract_photos()
    download_and_extract_etalons()
    rebuild_index()
    load_index()
    load_model()
    app = Application.builder().token(TOKEN).read_timeout(60).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("review", review_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(CallbackQueryHandler(button_callback))
    print("🚀 Bot started (GitHub + Swahili ready).")
    app.run_polling()
