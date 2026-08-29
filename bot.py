import os
import pickle
import zipfile
import gdown
import requests
import numpy as np
import faiss
import sqlite3
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import Application, MessageHandler, filters, CallbackQueryHandler, CommandHandler
from PIL import Image
import torch
from torchvision import transforms
from ultralytics import YOLO
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image as RLImage, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.fonts import addMapping
import io
import datetime as dt

# ===== CONFIG =====
TOKEN = "8993796250:AAFWDsfKuc4Bvha2ED-fvUyONlQ_iiNpCCk"
PHOTO_DB_URL = "https://dl.dropboxusercontent.com/scl/fi/xxl7bna8h3re0ks9jdsy6/photo_db.zip?rlkey=j94j0yuv1e3sg67txyzda4zo9&dl=1"
ETALONS_URL = "https://dl.dropboxusercontent.com/scl/fi/c7xk15hjnjx1eyzwmwrds/etalons.zip?rlkey=xos4ax8t621r6w8r16ji0tsk1&dl=1"
INDEX_PATH = "faiss_index.bin"
PATHS_PATH = "image_paths.pkl"
MODEL_PATH = "best.pt"
OWNER_ID = 8743362338

# ===== TRANSLATIONS =====
TRANSLATIONS = {
    "en": {
        "welcome": "Hello! 👋\nI'm a technical inspection bot. Send me a photo of electrical installation, and I'll find possible violations.\n\nJust send a photo!",
        "language_set": "✅ Language set to English. Send a photo of electrical installation.",
        "defect_found": "🔍 **Defect found:**",
        "standard": "📜 Standard:",
        "no_match": "❌ Could not find a matching image in the database.",
        "report_ready": "📄 Your report is ready!",
        "no_defects": "📭 No defects recorded. Please send photos first.",
        "review_empty": "📭 Review folder is empty or does not exist.",
        "review_photos_found": "📸 Found {count} photos. Sending...",
        "review_done": "✅ All photos sent.",
        "stats": "📊 Bot Statistics:\n👥 Total users: {total}\n📈 New today: {today}\n📅 New this week: {week}",
        "stats_unauthorized": "⛔ You are not authorized to view statistics.",
        "choose_language": "🌐 Choose your language:",
        "report_action": "🛠 Recommended action: Bring into compliance with the requirements of applicable regulatory and technical documents (RTD).",
        "defects_found": "🔍 **Defects found:**",
        "no_photo": "❌ Could not find a matching image in the database.",
        "prescription_ready": "📄 Your prescription is ready!",
        "defect_label": "Defect #{i}",
        "standard_label": "Standard:",
        "empty_report": "No defects recorded. Please send photos first.",
        "prescription_title": "📋 Prescription for Elimination of Violations",
        "issue_date": "Issue date: {date}",
        "deadline": "Deadline for elimination: _______________",
        "issued_by": "ISSUED THE PRESCRIPTION:",
        "received_by": "TOOK THE PRESCRIPTION FOR WORK:",
        "company": "Company: ___________________",
        "position": "Position: _________________",
        "full_name": "Full name: _______________________",
        "signature": "Signature: ___________________",
        "violation": "Violation #{i}",
        "photo": "📸 Photo of the violation:",
        "no_photo_available": "No photo available",
        "generate_prescription": "📄 Generate Prescription"
    },
    "ru": {
        "welcome": "Привет! 👋\nЯ бот технической инспекции. Отправь мне фото электроустановки, и я найду возможные нарушения.\n\nПросто отправь фото!",
        "language_set": "✅ Язык установлен на русский. Отправьте фото электроустановки.",
        "defect_found": "🔍 **Найдено замечание:**",
        "standard": "📜 Норматив:",
        "no_match": "❌ Не удалось найти похожее изображение в базе.",
        "report_ready": "📄 Ваше предписание готово!",
        "no_defects": "📭 Нет замечаний для предписания. Сначала отправьте фотографии.",
        "review_empty": "📭 Папка review пуста или не существует.",
        "review_photos_found": "📸 Найдено {count} фото. Отправляю...",
        "review_done": "✅ Все фото отправлены.",
        "stats": "📊 Статистика бота:\n👥 Всего пользователей: {total}\n📈 Новых сегодня: {today}\n📅 За неделю: {week}",
        "stats_unauthorized": "⛔ Вы не авторизованы для просмотра статистики.",
        "choose_language": "🌐 Выберите язык:",
        "report_action": "🛠 Необходимо привести в соответствие с требованиями действующих нормативно-технических документов (НТД).",
        "defects_found": "🔍 **Найдены замечания:**",
        "no_photo": "❌ Не удалось найти похожее изображение в базе.",
        "prescription_ready": "📄 Ваше предписание готово!",
        "defect_label": "Замечание №{i}",
        "standard_label": "Норматив:",
        "empty_report": "Нет замечаний для предписания. Сначала отправьте фотографии.",
        "prescription_title": "📋 Предписание по устранению нарушений",
        "issue_date": "Дата выдачи: {date}",
        "deadline": "Срок устранения: _______________",
        "issued_by": "ВЫДАЛ ПРЕДПИСАНИЕ:",
        "received_by": "ВЗЯЛ В РАБОТУ:",
        "company": "Компания: ___________________",
        "position": "Должность: _________________",
        "full_name": "ФИО: _______________________",
        "signature": "Подпись: ___________________",
        "violation": "Замечание №{i}",
        "photo": "📸 Фото нарушения:",
        "no_photo_available": "Фото не загружено",
        "generate_prescription": "📄 Сформировать предписание"
    }
}

# ===== CATEGORY DATA =====
CATEGORY_DATA = [
    {
        "keyword": "01_otsutstvuyut_birki",
        "etalon_prefix": "birki_etalon",
        "text": {
            "en": "⚠️ Missing cable/equipment labels (tags).",
            "ru": "⚠️ Отсутствуют бирки на оборудовании (кабелях, муфтах, аппаратах)."
        },
        "normative": {
            "en": "IEC 60445, NEC 110.22, BS 7671 514.9",
            "ru": "ПУЭ п. 2.3.23, СП 76.13330.2016 п. 6.4.8"
        }
    },
    {
        "keyword": "02_zadelka_prohodok",
        "etalon_prefix": "prohodki_etalon",
        "text": {
            "en": "⚠️ Gaps in cable penetrations not sealed.",
            "ru": "⚠️ Не выполнена заделка проходок (зазоры в трубах, коробах, проёмах)."
        },
        "normative": {
            "en": "IEC 60364-5-52, NEC 300.21, BS 7671 527.2",
            "ru": "СП 76.13330.2016 п. 6.4.1.25"
        }
    },
    {
        "keyword": "03_zazemlenie_ne_vypolneno",
        "etalon_prefix": "zazemlenie_etalon",
        "text": {
            "en": "⚠️ Earthing not provided or does not meet standards.",
            "ru": "⚠️ Не выполнено заземление (или не соответствует нормам)."
        },
        "normative": {
            "en": "IEC 60364-4-41, NEC 250.4, BS 7671 411.3",
            "ru": "ПУЭ п. 1.7.76"
        }
    },
    {
        "keyword": "04_shpilki_lotka_ne_srezany",
        "etalon_prefix": "shpilki_etalon",
        "text": {
            "en": "⚠️ Cable tray studs not trimmed.",
            "ru": "⚠️ Шпильки лотка не срезаны (опасность травматизма и повреждения кабелей)."
        },
        "normative": {
            "en": "IEC 61537, NEC 392.18, BS 7671 522.8",
            "ru": "ГОСТ Р 50571.5.52-2011"
        }
    }
]

# ===== DATABASE =====
DB_PATH = "users.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        first_seen TEXT,
        last_seen TEXT,
        language TEXT DEFAULT 'en'
    )''')
    conn.commit()
    conn.close()

def register_user(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    now = dt.datetime.now().isoformat()
    c.execute("INSERT OR IGNORE INTO users (user_id, first_seen, last_seen, language) VALUES (?, ?, ?, 'en')",
              (user_id, now, now))
    c.execute("UPDATE users SET last_seen = ? WHERE user_id = ?", (now, user_id))
    conn.commit()
    conn.close()

def get_user_language(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    lang = c.execute("SELECT language FROM users WHERE user_id = ?", (user_id,)).fetchone()
    conn.close()
    return lang[0] if lang else "en"

def set_user_language(user_id, lang):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE users SET language = ? WHERE user_id = ?", (lang, user_id))
    conn.commit()
    conn.close()

def get_stats():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    total = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    today = dt.datetime.now().date().isoformat()
    today_count = c.execute(
        "SELECT COUNT(*) FROM users WHERE date(first_seen) = ?", (today,)
    ).fetchone()[0]
    week_ago = (dt.datetime.now() - timedelta(days=7)).date().isoformat()
    week_count = c.execute(
        "SELECT COUNT(*) FROM users WHERE date(first_seen) >= ?", (week_ago,)
    ).fetchone()[0]
    conn.close()
    return total, today_count, week_count

# ===== GLOBALS =====
index = None
image_paths = None
embedder = None
transform = None

# ===== FONT =====
try:
    pdfmetrics.registerFont(TTFont('DejaVuSans', 'DejaVuSans.ttf'))
    addMapping('DejaVuSans', 0, 0, 'DejaVuSans')
    addMapping('DejaVuSans', 0, 1, 'DejaVuSans')
    addMapping('DejaVuSans', 1, 0, 'DejaVuSans')
    addMapping('DejaVuSans', 1, 1, 'DejaVuSans')
    FONT_NAME = 'DejaVuSans'
    print("✅ DejaVuSans font loaded")
except:
    FONT_NAME = 'Helvetica'
    print("⚠️ DejaVuSans not found, using Helvetica")

# ===== KEYBOARDS =====
def get_report_keyboard(lang):
    text = TRANSLATIONS[lang]["generate_prescription"]
    return InlineKeyboardMarkup([[InlineKeyboardButton(text, callback_data="generate_report")]])

def get_language_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")],
        [InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru")]
    ])

# ===== PDF GENERATION =====
def generate_pdf_report(report_data, chat_id, lang):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    for style_name in styles.byName:
        styles[style_name].fontName = FONT_NAME
    title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontSize=18, alignment=1, fontName=FONT_NAME)

    story = []
    # Заголовок
    story.append(Paragraph(TRANSLATIONS[lang]['prescription_title'], title_style))
    story.append(Paragraph(TRANSLATIONS[lang]['issue_date'].format(date=dt.datetime.now().strftime('%d.%m.%Y')), styles['Normal']))
    story.append(Spacer(1, 12*mm))

    if report_data:
        for i, item in enumerate(report_data, 1):
            story.append(Paragraph(TRANSLATIONS[lang]['violation'].format(i=i), styles['Heading2']))
            story.append(Paragraph(f"{item.get('text', 'Unknown')}", styles['Normal']))
            story.append(Paragraph(f"{TRANSLATIONS[lang]['standard_label']} {item.get('normative', '—')}", styles['Normal']))
            # Добавляем фото нарушения
            if item.get('photo_path') and os.path.exists(item['photo_path']):
                try:
                    img = RLImage(item['photo_path'], width=120*mm, height=80*mm)
                    story.append(img)
                    story.append(Paragraph(TRANSLATIONS[lang]['photo'], styles['Normal']))
                except:
                    story.append(Paragraph(TRANSLATIONS[lang]['no_photo_available'], styles['Normal']))
            else:
                story.append(Paragraph(TRANSLATIONS[lang]['no_photo_available'], styles['Normal']))
            story.append(Spacer(1, 6*mm))

    # Блок для подписей и срока
    story.append(Paragraph(TRANSLATIONS[lang]['deadline'], styles['Normal']))
    story.append(Spacer(1, 6*mm))
    story.append(Paragraph(TRANSLATIONS[lang]['issued_by'], styles['Heading2']))
    story.append(Paragraph(TRANSLATIONS[lang]['company'], styles['Normal']))
    story.append(Paragraph(TRANSLATIONS[lang]['position'], styles['Normal']))
    story.append(Paragraph(TRANSLATIONS[lang]['full_name'], styles['Normal']))
    story.append(Paragraph(TRANSLATIONS[lang]['signature'], styles['Normal']))
    story.append(Spacer(1, 6*mm))
    story.append(Paragraph(TRANSLATIONS[lang]['received_by'], styles['Heading2']))
    story.append(Paragraph(TRANSLATIONS[lang]['company'], styles['Normal']))
    story.append(Paragraph(TRANSLATIONS[lang]['position'], styles['Normal']))
    story.append(Paragraph(TRANSLATIONS[lang]['full_name'], styles['Normal']))
    story.append(Paragraph(TRANSLATIONS[lang]['signature'], styles['Normal']))

    doc.build(story)
    buffer.seek(0)
    return buffer

# ===== DOWNLOADS =====
def download_and_extract_photos():
    if os.path.exists("photo_db") and len(os.listdir("photo_db")) > 0:
        print("📁 photo_db already exists, skipping download.")
        return
    print("📥 Downloading photo archive via gdown...")
    gdown.download(PHOTO_DB_URL, "photo_db.zip", quiet=False)
    print("📦 Extracting...")
    with zipfile.ZipFile("photo_db.zip", "r") as zip_ref:
        zip_ref.extractall(".")
    os.remove("photo_db.zip")
    if not os.path.exists("photo_db"):
        for item in os.listdir("."):
            if os.path.isdir(item) and item.startswith("photo_db"):
                os.rename(item, "photo_db")
                break
        else:
            os.mkdir("photo_db")
            for f in os.listdir("."):
                if f.lower().endswith(('.jpg', '.jpeg', '.png')):
                    os.rename(f, os.path.join("photo_db", f))
    print(f"✅ photo_db ready, {len(os.listdir('photo_db'))} files.")

def download_and_extract_etalons():
    if os.path.exists("etalons") and len(os.listdir("etalons")) > 0:
        print("📁 etalons already exists, skipping download.")
        return
    print("📥 Downloading etalons archive via requests...")
    response = requests.get(ETALONS_URL, stream=True)
    with open("etalons.zip", "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)
    print("📦 Extracting...")
    with zipfile.ZipFile("etalons.zip", "r") as zip_ref:
        zip_ref.extractall(".")
    os.remove("etalons.zip")
    print("✅ Etalons ready.")

# ===== INDEX, MODEL =====
def load_index():
    global index, image_paths
    if index is None:
        print("Loading index...")
        index = faiss.read_index(INDEX_PATH)
        with open(PATHS_PATH, "rb") as f:
            raw_paths = pickle.load(f)
        image_paths = [os.path.join("photo_db", os.path.basename(p)) for p in raw_paths]
        print(f"Index loaded, {len(image_paths)} images.")

def load_model():
    global embedder, transform
    if embedder is None:
        print("Loading model...")
        try:
            model = YOLO(MODEL_PATH)
            torch_model = model.model.model
            embedder = torch.nn.Sequential(*list(torch_model.children())[:-1])
            embedder.eval()
            transform = transforms.Compose([
                transforms.Resize((224, 224)),
                transforms.ToTensor(),
                transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
            ])
            print("Model loaded.")
        except Exception as e:
            print(f"⚠️ Model not loaded: {e}. Falling back to filename matching.")
            embedder = None

def get_embedding(image_path):
    if embedder is None:
        return np.random.rand(128).astype('float32')
    img = Image.open(image_path).convert('RGB')
    img_tensor = transform(img).unsqueeze(0)
    with torch.no_grad():
        emb = embedder(img_tensor).flatten().cpu().numpy()
    return emb

def get_category_info(filename, lang):
    name = os.path.basename(filename)
    print(f"🔎 Determining category for: {name}")
    for category in CATEGORY_DATA:
        if name.startswith(category["keyword"]):
            return {
                "text": category["text"].get(lang, category["text"]["en"]),
                "etalon_prefix": category["etalon_prefix"],
                "normative": category["normative"].get(lang, category["normative"]["en"])
            }
    # Если точное совпадение не найдено, пробуем по частям
    parts = name.split('_')
    for category in CATEGORY_DATA:
        kw_parts = category["keyword"].split('_')
        if any(kp in parts for kp in kw_parts):
            return {
                "text": category["text"].get(lang, category["text"]["en"]),
                "etalon_prefix": category["etalon_prefix"],
                "normative": category["normative"].get(lang, category["normative"]["en"])
            }
    # Если ничего не найдено
    return {
        "text": f"📌 Unknown defect (file: {name})" if lang == "en" else f"📌 Неизвестное замечание (файл: {name})",
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

# ===== HANDLE PHOTO =====
async def handle_photo(update, context):
    try:
        user_id = update.effective_user.id
        register_user(user_id)
        lang = get_user_language(user_id)
        t = TRANSLATIONS[lang]

        load_index()
        load_model()

        photo = update.message.photo[-1]
        file = await photo.get_file()
        user_path = f"temp_{update.message.chat.id}.jpg"
        await file.download_to_drive(user_path)

        emb = get_embedding(user_path)
        os.remove(user_path)

        emb = np.array([emb]).astype('float32')
        # Ищем 3 самых похожих изображения
        k = 3
        distances, indices = index.search(emb, k)

        if len(indices[0]) == 0 or indices[0][0] == -1:
            await update.message.reply_text(t['no_photo'])
            return

        # Собираем уникальные замечания
        unique_defects = []
        seen = set()
        for idx in indices[0]:
            if idx == -1:
                continue
            full_path = image_paths[idx]
            info = get_category_info(full_path, lang)
            cat_key = info.get("etalon_prefix")
            if cat_key and cat_key not in seen:
                seen.add(cat_key)
                unique_defects.append(info)
            if len(unique_defects) >= 3:  # максимум 3 замечания
                break

        # Сохраняем оригинальное фото в review (для истории)
        base_dir = os.getcwd()
        timestamp = dt.datetime.now().strftime('%Y%m%d_%H%M%S')
        review_path = os.path.join(base_dir, "review", "all", f"{timestamp}.jpg")
        os.makedirs(os.path.dirname(review_path), exist_ok=True)
        await file.download_to_drive(review_path)

        # Формируем ответ
        if len(unique_defects) == 0:
            await update.message.reply_text(t['no_photo'])
            return

        response = t['defects_found'] + "\n\n"
        for i, defect in enumerate(unique_defects, 1):
            response += f"{i}. {defect['text']}\n"
            if defect.get("normative"):
                response += f"   {t['standard']} {defect['normative']}\n\n"

        # Сохраняем замечания в сессию для предписания
        if 'report_data' not in context.user_data:
            context.user_data['report_data'] = []
        context.user_data['report_data'] = unique_defects

        # Добавляем кнопку для формирования предписания
        await update.message.reply_text(
            response,
            reply_markup=get_report_keyboard(lang)
        )

    except Exception as e:
        print(f"Error: {e}")
        await update.message.reply_text(f"❌ Error: {e}")

# ===== BUTTON CALLBACK =====
async def button_callback(update, context):
    query = update.callback_query
    user_id = update.effective_user.id
    register_user(user_id)
    lang = get_user_language(user_id)
    t = TRANSLATIONS[lang]

    await query.answer()

    if query.data == "generate_report":
        report_data = context.user_data.get('report_data', [])
        if not report_data:
            await query.edit_message_text(t['empty_report'])
            return
        pdf_buffer = generate_pdf_report(report_data, query.message.chat.id, lang)
        await query.message.reply_document(
            document=pdf_buffer,
            filename=f"prescription_{dt.datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
            caption=t['prescription_ready']
        )
        context.user_data['report_data'] = []

    elif query.data.startswith("lang_"):
        new_lang = query.data.split("_")[1]
        set_user_language(user_id, new_lang)
        t_new = TRANSLATIONS[new_lang]
        await query.edit_message_text(t_new['language_set'])

# ===== COMMANDS =====
async def start_command(update, context):
    user_id = update.effective_user.id
    register_user(user_id)
    lang = get_user_language(user_id)
    await update.message.reply_text(TRANSLATIONS[lang]['welcome'], reply_markup=get_language_keyboard())

async def language_command(update, context):
    user_id = update.effective_user.id
    register_user(user_id)
    lang = get_user_language(user_id)
    await update.message.reply_text(TRANSLATIONS[lang]['choose_language'], reply_markup=get_language_keyboard())

async def review_command(update, context):
    user_id = update.effective_user.id
    register_user(user_id)
    lang = get_user_language(user_id)
    t = TRANSLATIONS[lang]

    review_dir = os.path.join(os.getcwd(), "review")
    if not os.path.exists(review_dir):
        await update.message.reply_text(t['review_empty'])
        return

    photo_paths = []
    for root, dirs, files in os.walk(review_dir):
        for f in files:
            if f.lower().endswith(('.jpg', '.jpeg', '.png')):
                photo_paths.append(os.path.join(root, f))

    if not photo_paths:
        await update.message.reply_text(t['review_empty'])
        return

    await update.message.reply_text(t['review_photos_found'].format(count=len(photo_paths)))
    for path in photo_paths:
        try:
            with open(path, 'rb') as f:
                await update.message.reply_photo(photo=f)
        except:
            await update.message.reply_text(f"❌ Не удалось отправить: {os.path.basename(path)}")
    await update.message.reply_text(t['review_done'])

async def stats_command(update, context):
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        lang = get_user_language(user_id)
        await update.message.reply_text(TRANSLATIONS[lang]['stats_unauthorized'])
        return
    total, today_count, week_count = get_stats()
    lang = get_user_language(user_id)
    await update.message.reply_text(TRANSLATIONS[lang]['stats'].format(total=total, today=today_count, week=week_count))

# ===== START =====
if __name__ == "__main__":
    init_db()
    download_and_extract_photos()
    download_and_extract_etalons()
    load_index()
    load_model()
    app = Application.builder().token(TOKEN).read_timeout(60).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("language", language_command))
    app.add_handler(CommandHandler("review", review_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(CallbackQueryHandler(button_callback))
    print("🚀 Bot started. Waiting for photos...")
    app.run_polling()
