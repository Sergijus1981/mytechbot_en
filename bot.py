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
import shutil
import subprocess

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
        "defects_list": "🔍 Found defects:",
        "generate_order": "📄 Generate order",
        "classify_prompt": "📸 Classify this photo:",
        "classify_success": "✅ Photo added to {category}",
        "classify_skipped": "⏭️ Photo skipped",
        "classify_rejected": "❌ Photo rejected and deleted",
        "no_photos_left": "✅ All photos classified."
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
        "defects_list": "🔍 Найдены замечания:",
        "generate_order": "📄 Сформировать предписание",
        "classify_prompt": "📸 Классифицируйте это фото:",
        "classify_success": "✅ Фото добавлено в категорию {category}",
        "classify_skipped": "⏭️ Фото пропущено",
        "classify_rejected": "❌ Фото отклонено и удалено",
        "no_photos_left": "✅ Все фото классифицированы."
    }
}

# ===== CATEGORY DATA =====
CATEGORY_DATA = [
    {
        "keyword": "01_otsutstvuyut_birki",
        "etalon_prefix": "birki_etalon",
        "label_ru": "Бирки",
        "label_en": "Labels",
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
        "label_ru": "Проходки",
        "label_en": "Penetrations",
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
        "label_ru": "Заземление",
        "label_en": "Earthing",
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
        "label_ru": "Шпильки",
        "label_en": "Studs",
        "text": {
            "en": "⚠️ Cable tray studs not trimmed.",
            "ru": "⚠️ Шпильки лотка не срезаны (опасность травматизма и повреждения кабелей)."
        },
        "normative": {
            "en": "IEC 61537, NEC 392.18, BS 7671 522.8",
            "ru": "ГОСТ Р 50571.5.52-2011"
        }
    },
    {
        "keyword": "05_oksidy_rzhavchina",
        "etalon_prefix": "oksidy_etalon",
        "label_ru": "Окислы",
        "label_en": "Oxidation",
        "text": {
            "en": "⚠️ Oxidation and rust on equipment contacts.",
            "ru": "⚠️ Окислы и ржавчина на контактах оборудования."
        },
        "normative": {
            "en": "IEC 60204-1, NEC 110.12",
            "ru": "ПУЭ п. 1.8.4, ГОСТ 10434-82"
        }
    },
    {
        "keyword": "06_otsutstvie_shemy",
        "etalon_prefix": "shema_etalon",
        "label_ru": "Схема",
        "label_en": "Diagram",
        "text": {
            "en": "⚠️ Single-line diagram missing inside the cabinet.",
            "ru": "⚠️ Отсутствует однолинейная схема внутри шкафа."
        },
        "normative": {
            "en": "IEC 61082-1, NEC 110.22",
            "ru": "ПУЭ п. 1.8.4, СП 76.13330.2016 п. 6.4.8"
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
    text = TRANSLATIONS[lang]['generate_order']
    return InlineKeyboardMarkup([[InlineKeyboardButton(text, callback_data="generate_report")]])

def get_language_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")],
        [InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru")]
    ])

def get_classify_keyboard(lang):
    keyboard = []
    for cat in CATEGORY_DATA:
        label = cat["label_ru"] if lang == "ru" else cat["label_en"]
        callback = f"classify_{cat['keyword']}"
        keyboard.append([InlineKeyboardButton(label, callback_data=callback)])
    keyboard.append([InlineKeyboardButton("⏭️ Пропустить", callback_data="classify_skip")])
    keyboard.append([InlineKeyboardButton("❌ Отклонить", callback_data="classify_reject")])
    return InlineKeyboardMarkup(keyboard)

def get_category_by_keyword(keyword):
    for cat in CATEGORY_DATA:
        if cat["keyword"] == keyword:
            return cat
    return None

# ===== PDF GENERATION =====
def generate_pdf_report(report_data, chat_id, lang):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    for style_name in styles.byName:
        styles[style_name].fontName = FONT_NAME
    title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontSize=18, alignment=1, fontName=FONT_NAME)
    story = []
    title = "ПРЕДПИСАНИЕ" if lang == "ru" else "ORDER"
    story.append(Paragraph(title, title_style))
    story.append(Paragraph(f"Дата выдачи: {dt.datetime.now().strftime('%d.%m.%Y')}" if lang == "ru" else f"Issue date: {dt.datetime.now().strftime('%d.%m.%Y')}", styles['Normal']))
    story.append(Spacer(1, 6*mm))

    if report_data:
        for i, item in enumerate(report_data, 1):
            story.append(Paragraph(f"<b>{'Замечание' if lang == 'ru' else 'Defect'} #{i}</b>", styles['Heading2']))
            story.append(Paragraph(f"📌 {item.get('text', 'Unknown')}", styles['Normal']))
            story.append(Paragraph(f"{'Норматив:' if lang == 'ru' else 'Standard:'} {item.get('normative', '—')}", styles['Normal']))
            story.append(Paragraph(TRANSLATIONS[lang]['report_action'], styles['Normal']))
            if item.get('photo_path') and os.path.exists(item['photo_path']):
                try:
                    img = RLImage(item['photo_path'], width=120*mm, height=80*mm)
                    story.append(img)
                    story.append(Paragraph("📸 Фото нарушения" if lang == 'ru' else "📸 Violation photo", styles['Normal']))
                except:
                    story.append(Paragraph("⚠️ Фото не загружено" if lang == 'ru' else "⚠️ Photo not available", styles['Normal']))
            story.append(Spacer(1, 4*mm))
        story.append(Spacer(1, 6*mm))
        story.append(Paragraph("Срок устранения: _______________", styles['Normal']))
        story.append(Spacer(1, 4*mm))
        story.append(Paragraph("ВЫДАЛ ПРЕДПИСАНИЕ:" if lang == 'ru' else "ISSUED BY:", styles['Normal']))
        story.append(Paragraph("Компания: ___________________", styles['Normal']))
        story.append(Paragraph("Должность: _________________", styles['Normal']))
        story.append(Paragraph("ФИО: _______________________", styles['Normal']))
        story.append(Paragraph("Подпись: ___________________", styles['Normal']))
        story.append(Spacer(1, 4*mm))
        story.append(Paragraph("ВЗЯЛ В РАБОТУ:" if lang == 'ru' else "RECEIVED BY:", styles['Normal']))
        story.append(Paragraph("Компания: ___________________", styles['Normal']))
        story.append(Paragraph("Должность: _________________", styles['Normal']))
        story.append(Paragraph("ФИО: _______________________", styles['Normal']))
        story.append(Paragraph("Подпись: ___________________", styles['Normal']))
    else:
        story.append(Paragraph(TRANSLATIONS[lang]['no_defects'], styles['Normal']))

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

def rebuild_index():
    """Перестраивает индекс FAISS."""
    print("🔄 Перестраиваю индекс...")
    try:
        # Проверяем, что index_builder.py существует
        if not os.path.exists("index_builder.py"):
            print("❌ index_builder.py не найден")
            return False
        # Проверяем, что папка photo_db существует
        if not os.path.exists("photo_db"):
            print("❌ photo_db не найдена")
            return False
        subprocess.run(["python", "index_builder.py"], check=True)
        print("✅ Индекс перестроен.")
        return True
    except Exception as e:
        print(f"❌ Ошибка перестроения индекса: {e}")
        return False

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
    parts = name.split('_')
    for category in CATEGORY_DATA:
        kw_parts = category["keyword"].split('_')
        if any(kp in parts for kp in kw_parts):
            return {
                "text": category["text"].get(lang, category["text"]["en"]),
                "etalon_prefix": category["etalon_prefix"],
                "normative": category["normative"].get(lang, category["normative"]["en"])
            }
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
        distances, indices = index.search(emb, 3)  # ищем 3 самых похожих

        if len(indices[0]) == 0 or indices[0][0] == -1:
            await update.message.reply_text(t['no_match'])
            return

        # Сохраняем фото в review (для последующей классификации)
        base_dir = os.getcwd()
        review_dir = os.path.join(base_dir, "review")
        os.makedirs(review_dir, exist_ok=True)
        timestamp = dt.datetime.now().strftime('%Y%m%d_%H%M%S')
        review_path = os.path.join(review_dir, f"{timestamp}.jpg")
        print(f"📂 Сохраняю фото в: {review_path}")
        await file.download_to_drive(review_path)
        print(f"✅ Фото сохранено в review: {review_path}")

        # Собираем уникальные замечания (до 3)
        unique_defects = []
        seen = set()
        for idx in indices[0]:
            full_path = image_paths[idx]
            info = get_category_info(full_path, lang)
            cat_key = info.get("etalon_prefix")
            if cat_key and cat_key not in seen:
                seen.add(cat_key)
                unique_defects.append(info)
                if len(unique_defects) >= 3:
                    break

        if not unique_defects:
            await update.message.reply_text(t['no_match'])
            return

        # Формируем ответ
        response = t['defects_list'] + "\n"
        for i, defect in enumerate(unique_defects, 1):
            response += f"{i}. {defect['text']}\n"
            if defect.get('normative'):
                response += f"   {t['standard']} {defect['normative']}\n"

        # Сохраняем замечания в сессию для предписания
        if 'report_data' not in context.user_data:
            context.user_data['report_data'] = []
        for defect in unique_defects:
            context.user_data['report_data'].append({
                'text': defect['text'],
                'normative': defect.get('normative'),
                'photo_path': review_path
            })

        # Отправляем эталон (первое найденное)
        etalon_path = find_etalon(unique_defects[0].get("etalon_prefix"))
        if etalon_path and os.path.exists(etalon_path):
            with open(etalon_path, 'rb') as f:
                await update.message.reply_photo(photo=f, caption=response, reply_markup=get_report_keyboard(lang))
        else:
            await update.message.reply_text(response, reply_markup=get_report_keyboard(lang))

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
            await query.edit_message_text(t['no_defects'])
            return
        pdf_buffer = generate_pdf_report(report_data, query.message.chat.id, lang)
        await query.message.reply_document(
            document=pdf_buffer,
            filename=f"Предписание_{dt.datetime.now().strftime('%d.%m.%Y')}.pdf" if lang == 'ru' else f"Order_{dt.datetime.now().strftime('%d.%m.%Y')}.pdf",
            caption=t['report_ready']
        )
        context.user_data['report_data'] = []

    elif query.data.startswith("lang_"):
        new_lang = query.data.split("_")[1]
        set_user_language(user_id, new_lang)
        t_new = TRANSLATIONS[new_lang]
        await query.edit_message_text(t_new['language_set'])

    elif query.data.startswith("classify_"):
        # Обработка классификации из review
        action = query.data.split("_", 1)[1]
        # Получаем текущее фото из контекста (храним список фото для классификации)
        if 'review_photos' not in context.user_data or not context.user_data['review_photos']:
            await query.edit_message_text("❌ Нет фото для классификации.")
            return

        photo_path = context.user_data['review_photos'].pop(0)
        if action == "skip":
            # Пропускаем — оставляем в review
            await query.edit_message_text(t['classify_skipped'])
        elif action == "reject":
            # Удаляем фото
            if os.path.exists(photo_path):
                os.remove(photo_path)
            await query.edit_message_text(t['classify_rejected'])
        else:
            # Классифицируем — перемещаем в photo_db
            category = get_category_by_keyword(action)
            if not category:
                await query.edit_message_text("❌ Неизвестная категория.")
                return
            # Создаём папку, если её нет
            target_dir = os.path.join("photo_db", category["keyword"])
            os.makedirs(target_dir, exist_ok=True)
            # Копируем фото с новым именем (с временем)
            new_name = f"{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
            new_path = os.path.join(target_dir, new_name)
            shutil.copy2(photo_path, new_path)
            # Удаляем из review
            if os.path.exists(photo_path):
                os.remove(photo_path)
            # Перестраиваем индекс
            rebuild_index()
            # Обновляем глобальный индекс
            global index, image_paths
            load_index()
            await query.edit_message_text(t['classify_success'].format(category=category["label_ru"] if lang == "ru" else category["label_en"]))

        # Отправляем следующее фото, если есть
        if context.user_data['review_photos']:
            next_photo = context.user_data['review_photos'][0]
            with open(next_photo, 'rb') as f:
                await query.message.reply_photo(photo=f, caption=t['classify_prompt'], reply_markup=get_classify_keyboard(lang))
        else:
            await query.message.reply_text(t['no_photos_left'])

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

    base_dir = os.getcwd()
    review_dir = os.path.join(base_dir, "review")
    if not os.path.exists(review_dir):
        os.makedirs(review_dir, exist_ok=True)
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

    # Сохраняем список фото в контекст для пошаговой классификации
    context.user_data['review_photos'] = photo_paths

    # Показываем первое фото с кнопками
    first_photo = photo_paths[0]
    with open(first_photo, 'rb') as f:
        await update.message.reply_photo(photo=f, caption=t['classify_prompt'], reply_markup=get_classify_keyboard(lang))

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
