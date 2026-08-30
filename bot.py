import os, pickle, zipfile, gdown, requests, numpy as np, faiss, sqlite3, shutil, subprocess, io, datetime as dt
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
PHOTO_DB_URL = "https://dl.dropboxusercontent.com/scl/fi/xxl7bna8h3re0ks9jdsy6/photo_db.zip?rlkey=j94j0yuv1e3sg67txyzda4zo9&dl=1"
ETALONS_URL = "https://dl.dropboxusercontent.com/scl/fi/c7xk15hjnjx1eyzwmwrds/etalons.zip?rlkey=xos4ax8t621r6w8r16ji0tsk1&dl=1"
INDEX_PATH, PATHS_PATH, MODEL_PATH = "faiss_index.bin", "image_paths.pkl", "best.pt"
OWNER_ID = 8743362338

# ===== TRANSLATIONS =====
T = {
    "en": {
        "welcome": "Hello! 👋\nI'm a technical inspection bot. Send me a photo of electrical installation, and I'll find possible violations.\n\nJust send a photo!",
        "language_set": "✅ Language set to English. Send a photo of electrical installation.",
        "defect_found": "🔍 **Defect found:**",
        "standard": "📜 Standard:",
        "no_match": "❌ Could not find a matching image in the database.",
        "report_ready": "📄 Your order is ready!",
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
        "classify_skipped": "⏭️ Пропущено",
        "classify_rejected": "❌ Отклонено и удалено",
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
    }
}

# ===== CATEGORIES =====
CATEGORIES = [
    {"keyword":"01_otsutstvuyut_birki", "etalon_prefix":"birki_etalon", "label_ru":"Бирки", "label_en":"Labels",
     "text":{"en":"⚠️ Missing cable/equipment labels.", "ru":"⚠️ Отсутствуют бирки на оборудовании."},
     "normative":{"en":"IEC 60445, NEC 110.22, BS 7671 514.9", "ru":"ПУЭ п. 2.3.23, СП 76.13330.2016 п. 6.4.8"}},
    {"keyword":"02_zadelka_prohodok", "etalon_prefix":"prohodki_etalon", "label_ru":"Проходки", "label_en":"Penetrations",
     "text":{"en":"⚠️ Gaps in penetrations not sealed.", "ru":"⚠️ Не выполнена заделка проходок."},
     "normative":{"en":"IEC 60364-5-52, NEC 300.21, BS 7671 527.2", "ru":"СП 76.13330.2016 п. 6.4.1.25"}},
    {"keyword":"03_zazemlenie_ne_vypolneno", "etalon_prefix":"zazemlenie_etalon", "label_ru":"Заземление", "label_en":"Earthing",
     "text":{"en":"⚠️ Earthing not provided.", "ru":"⚠️ Не выполнено заземление."},
     "normative":{"en":"IEC 60364-4-41, NEC 250.4, BS 7671 411.3", "ru":"ПУЭ п. 1.7.76"}},
    {"keyword":"04_shpilki_lotka_ne_srezany", "etalon_prefix":"shpilki_etalon", "label_ru":"Шпильки", "label_en":"Studs",
     "text":{"en":"⚠️ Cable tray studs not trimmed.", "ru":"⚠️ Шпильки лотка не срезаны."},
     "normative":{"en":"IEC 61537, NEC 392.18, BS 7671 522.8", "ru":"ГОСТ Р 50571.5.52-2011"}},
    {"keyword":"05_oksidy_rzhavchina", "etalon_prefix":"oksidy_etalon", "label_ru":"Окислы", "label_en":"Oxidation",
     "text":{"en":"⚠️ Oxidation/rust on contacts.", "ru":"⚠️ Окислы и ржавчина на контактах."},
     "normative":{"en":"IEC 60204-1, NEC 110.12", "ru":"ПУЭ п. 1.8.4, ГОСТ 10434-82"}},
    {"keyword":"06_otsutstvie_shemy", "etalon_prefix":"shema_etalon", "label_ru":"Схема", "label_en":"Diagram",
     "text":{"en":"⚠️ Single-line diagram missing.", "ru":"⚠️ Отсутствует однолинейная схема."},
     "normative":{"en":"IEC 61082-1, NEC 110.22", "ru":"ПУЭ п. 1.8.4, СП 76.13330.2016 п. 6.4.8"}}
]

# ===== DB =====
def init_db():
    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, first_seen TEXT, last_seen TEXT, language TEXT DEFAULT "en")')
    conn.commit(); conn.close()

def register_user(user_id):
    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    now = dt.datetime.now().isoformat()
    c.execute("INSERT OR IGNORE INTO users (user_id, first_seen, last_seen, language) VALUES (?, ?, ?, 'en')", (user_id, now, now))
    c.execute("UPDATE users SET last_seen = ? WHERE user_id = ?", (now, user_id))
    conn.commit(); conn.close()

def get_lang(user_id):
    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    r = c.execute("SELECT language FROM users WHERE user_id = ?", (user_id,)).fetchone()
    conn.close()
    return r[0] if r else "en"

def set_lang(user_id, lang):
    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    c.execute("UPDATE users SET language = ? WHERE user_id = ?", (lang, user_id))
    conn.commit(); conn.close()

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

# ===== FONT =====
try:
    pdfmetrics.registerFont(ttfonts.TTFont('DejaVuSans', 'DejaVuSans.ttf'))
    addMapping('DejaVuSans', 0, 0, 'DejaVuSans')
    FONT = 'DejaVuSans'
except:
    FONT = 'Helvetica'

# ===== GLOBALS =====
index = None
image_paths = None
embedder = None
transform = None

# ===== DOWNLOADS =====
def download_and_extract_photos():
    if os.path.exists("photo_db") and len(os.listdir("photo_db")) > 0:
        print("photo_db exists")
        return
    print("Downloading photo_db...")
    gdown.download(PHOTO_DB_URL, "photo_db.zip", quiet=False)
    with zipfile.ZipFile("photo_db.zip", "r") as z: z.extractall(".")
    os.remove("photo_db.zip")
    if not os.path.exists("photo_db"):
        os.mkdir("photo_db")
        for f in os.listdir("."):
            if f.lower().endswith(('.jpg','.jpeg','.png')): os.rename(f, os.path.join("photo_db", f))
    print(f"photo_db ready, {len(os.listdir('photo_db'))} files")

def download_and_extract_etalons():
    if os.path.exists("etalons") and len(os.listdir("etalons")) > 0:
        print("etalons exists")
        return
    print("Downloading etalons...")
    r = requests.get(ETALONS_URL, stream=True)
    with open("etalons.zip", "wb") as f:
        for chunk in r.iter_content(8192): f.write(chunk)
    with zipfile.ZipFile("etalons.zip", "r") as z: z.extractall(".")
    os.remove("etalons.zip")
    print("etalons ready")

def rebuild_index():
    print("Rebuilding index...")
    subprocess.run(["python", "index_builder.py"], check=True)
    load_index()

# ===== INDEX, MODEL =====
def load_index():
    global index, image_paths
    if index is None:
        index = faiss.read_index(INDEX_PATH)
        with open(PATHS_PATH, "rb") as f:
            raw = pickle.load(f)
        image_paths = [os.path.join("photo_db", os.path.basename(p)) for p in raw]
        print(f"Index loaded, {len(image_paths)} images")

def load_model():
    global embedder, transform
    if embedder is None:
        try:
            model = YOLO(MODEL_PATH)
            torch_model = model.model.model
            embedder = torch.nn.Sequential(*list(torch_model.children())[:-1]).eval()
            transform = transforms.Compose([
                transforms.Resize((224,224)),
                transforms.ToTensor(),
                transforms.Normalize(mean=[0.485,0.456,0.406], std=[0.229,0.224,0.225])
            ])
            print("Model loaded")
        except Exception as e:
            print(f"Model load failed: {e}")
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
        "text": f"Unknown defect (file: {name})" if lang=="en" else f"Неизвестное замечание (файл: {name})",
        "etalon_prefix": None,
        "normative": None
    }

def find_etalon(prefix):
    if not prefix: return None
    etalon_dir = "etalons"
    if not os.path.exists(etalon_dir): return None
    for f in os.listdir(etalon_dir):
        if f.startswith(prefix) and f.lower().endswith(('.jpg','.jpeg','.png')):
            return os.path.join(etalon_dir, f)
    return None

# ===== KEYBOARDS =====
def get_report_keyboard(lang):
    return InlineKeyboardMarkup([[InlineKeyboardButton(T[lang]['generate_order'], callback_data="generate_report")]])

def get_language_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")],
        [InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru")]
    ])

# ===== PDF =====
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
        for i, item in enumerate(report_data, 1):
            story.append(Paragraph(f"<b>{t['defect']} #{i}</b>", styles['Heading2']))
            story.append(Paragraph(f"📌 {item.get('text', '')}", styles['Normal']))
            story.append(Paragraph(f"{t['standard_label']} {item.get('normative', '—')}", styles['Normal']))
            story.append(Paragraph(t['report_action'], styles['Normal']))
            if item.get('photo_path') and os.path.exists(item['photo_path']):
                try:
                    img = RLImage(item['photo_path'], width=120*mm, height=80*mm)
                    story.append(img)
                    story.append(Paragraph(t['violation_photo'], styles['Normal']))
                except: pass
            story.append(Spacer(1, 4*mm))
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

# ===== HANDLERS =====
async def handle_photo(update, context):
    user_id = update.effective_user.id
    register_user(user_id)
    lang = get_lang(user_id)
    t = T[lang]
    load_index(); load_model()

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
            if len(unique) >= 3: break
    if not unique:
        await update.message.reply_text(t['no_match'])
        return

    response = t['defects_list'] + "\n"
    for i, d in enumerate(unique, 1):
        response += f"{i}. {d['text']}\n"
        if d.get('normative'): response += f"   {t['standard']} {d['normative']}\n"

    if 'report_data' not in context.user_data: context.user_data['report_data'] = []
    for d in unique:
        context.user_data['report_data'].append({
            'text': d['text'],
            'normative': d.get('normative'),
            'photo_path': review_path
        })

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

    print(f"Button clicked: {data}")

    if data == "generate_report":
        report_data = context.user_data.get('report_data', [])
        if not report_data:
            await query.edit_message_text(t['no_defects'])
            return
        pdf_buffer = generate_pdf_report(report_data, lang)
        await query.message.reply_document(
            document=pdf_buffer,
            filename=f"Предписание_{dt.datetime.now().strftime('%d.%m.%Y')}.pdf" if lang=="ru" else f"Order_{dt.datetime.now().strftime('%d.%m.%Y')}.pdf",
            caption=t['report_ready']
        )
        context.user_data['report_data'] = []
        await query.delete_message()
        return

    if data.startswith("lang_"):
        new_lang = data.split("_")[1]
        set_lang(user_id, new_lang)
        await query.edit_message_text(T[new_lang]['language_set'])
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
            if os.path.exists(photo_path): os.remove(photo_path)
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
            if os.path.exists(photo_path): os.remove(photo_path)
            rebuild_index()
            await query.edit_message_text(t['classify_success'].format(
                category=cat["label_ru"] if lang=="ru" else cat["label_en"]
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
    await update.message.reply_text(T[lang]['welcome'], reply_markup=get_language_keyboard())

async def language_command(update, context):
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
    print("🚀 Bot started.")
    app.run_polling()
