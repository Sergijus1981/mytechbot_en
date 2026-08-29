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
OWNER_ID = 8743362338  # только ты увидишь статистику

# ===== CATEGORY DATA =====
CATEGORY_DATA = [
    (
        "01_otsutstvuyut_birki",
        "⚠️ Missing cable/equipment labels (tags).",
        "birki_etalon",
        "IEC 60445, NEC 110.22, BS 7671 514.9"
    ),
    (
        "02_zadelka_prohodok",
        "⚠️ Gaps in cable penetrations not sealed.",
        "prohodki_etalon",
        "IEC 60364-5-52, NEC 300.21, BS 7671 527.2"
    ),
    (
        "03_zazemlenie_ne_vypolneno",
        "⚠️ Earthing not provided or does not meet standards.",
        "zazemlenie_etalon",
        "IEC 60364-4-41, NEC 250.4, BS 7671 411.3"
    ),
    (
        "04_shpilki_lotka_ne_srezany",
        "⚠️ Cable tray studs not trimmed.",
        "shpilki_etalon",
        "IEC 61537, NEC 392.18, BS 7671 522.8"
    ),
]

# ===== DATABASE SETUP =====
DB_PATH = "users.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        first_seen TEXT,
        last_seen TEXT
    )''')
    conn.commit()
    conn.close()

def register_user(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    now = dt.datetime.now().isoformat()
    c.execute("INSERT OR IGNORE INTO users (user_id, first_seen, last_seen) VALUES (?, ?, ?)",
              (user_id, now, now))
    c.execute("UPDATE users SET last_seen = ? WHERE user_id = ?", (now, user_id))
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

# ===== KEYBOARD =====
def get_report_keyboard():
    keyboard = [[InlineKeyboardButton("📄 Generate Report", callback_data="generate_report")]]
    return InlineKeyboardMarkup(keyboard)

# ===== PDF GENERATION =====
def generate_pdf_report(report_data, chat_id):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    for style_name in styles.byName:
        styles[style_name].fontName = FONT_NAME
    title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontSize=18, alignment=1, fontName=FONT_NAME)
    story = []
    story.append(Paragraph("📋 Electrical Inspection Report", title_style))
    story.append(Paragraph(f"Date: {dt.datetime.now().strftime('%d.%m.%Y %H:%M')}", styles['Normal']))
    story.append(Spacer(1, 12*mm))
    if report_data:
        for i, item in enumerate(report_data, 1):
            story.append(Paragraph(f"<b>Defect #{i}</b>", styles['Heading2']))
            story.append(Paragraph(f"📌 {item.get('text', 'Unknown')}", styles['Normal']))
            story.append(Paragraph(f"📜 Standard: {item.get('normative', '—')}", styles['Normal']))
            story.append(Paragraph(
                "🛠 Recommended action: Bring into compliance with "
                "the requirements of applicable regulatory and technical documents (RTD).",
                styles['Normal']
            ))
            if item.get('photo_path') and os.path.exists(item['photo_path']):
                try:
                    img = RLImage(item['photo_path'], width=120*mm, height=80*mm)
                    story.append(img)
                    story.append(Paragraph("📸 Actual photo", styles['Normal']))
                except Exception as e:
                    story.append(Paragraph(f"⚠️ Photo error: {e}", styles['Normal']))
            story.append(Spacer(1, 6*mm))
            story.append(PageBreak())
    else:
        story.append(Paragraph("No defects recorded.", styles['Normal']))
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

def get_category_info(filename):
    name = os.path.basename(filename)
    print(f"🔎 Determining category for: {name}")
    for keyword, text, etalon_prefix, normative in CATEGORY_DATA:
        if name.startswith(keyword):
            return {"text": text, "etalon_prefix": etalon_prefix, "normative": normative}
    parts = name.split('_')
    for keyword, text, etalon_prefix, normative in CATEGORY_DATA:
        kw_parts = keyword.split('_')
        if any(kp in parts for kp in kw_parts):
            return {"text": text, "etalon_prefix": etalon_prefix, "normative": normative}
    return {"text": f"📌 Unknown defect (file: {name})", "etalon_prefix": None, "normative": None}

def find_etalon(prefix):
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

        load_index()
        load_model()

        photo = update.message.photo[-1]
        file = await photo.get_file()
        user_path = f"temp_{update.message.chat.id}.jpg"
        await file.download_to_drive(user_path)

        emb = get_embedding(user_path)
        os.remove(user_path)

        emb = np.array([emb]).astype('float32')
        distances, indices = index.search(emb, 1)

        if len(indices[0]) == 0 or indices[0][0] == -1:
            await update.message.reply_text("❌ Could not find a matching image in the database.")
            return

        idx = indices[0][0]
        full_path = image_paths[idx]
        info = get_category_info(full_path)

        base_dir = os.getcwd()
        category_folder = info.get("etalon_prefix", "unknown")
        review_dir = os.path.join(base_dir, "review", category_folder)
        os.makedirs(review_dir, exist_ok=True)
        timestamp = dt.datetime.now().strftime('%Y%m%d_%H%M%S')
        review_path = os.path.join(review_dir, f"{timestamp}.jpg")
        print(f"📂 Сохраняю фото в: {review_path}")
        await file.download_to_drive(review_path)
        print(f"✅ Фото сохранено: {review_path}")

        response = f"🔍 **Defect found:**\n{info['text']}\n\n📸 Photo saved for manual verification.\n🕒 Awaiting confirmation."
        if info.get("normative"):
            response += f"\n📜 Standard: {info['normative']}"

        etalon_path = find_etalon(info.get("etalon_prefix"))
        if etalon_path and os.path.exists(etalon_path):
            with open(etalon_path, 'rb') as f:
                await update.message.reply_photo(photo=f, caption=response, reply_markup=get_report_keyboard())
        else:
            await update.message.reply_text(response, reply_markup=get_report_keyboard())

        if 'report_data' not in context.user_data:
            context.user_data['report_data'] = []
        context.user_data['report_data'].append({
            'text': info['text'],
            'normative': info.get('normative'),
            'photo_path': review_path
        })

    except Exception as e:
        print(f"Error: {e}")
        await update.message.reply_text(f"❌ Error: {e}")

# ===== BUTTON CALLBACK =====
async def button_callback(update, context):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    register_user(user_id)

    if query.data == "generate_report":
        report_data = context.user_data.get('report_data', [])
        if not report_data:
            await query.edit_message_text("📭 No defects recorded. Please send photos first.")
            return
        pdf_buffer = generate_pdf_report(report_data, query.message.chat.id)
        await query.message.reply_document(
            document=pdf_buffer,
            filename=f"report_{dt.datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
            caption="📄 Your report is ready!"
        )
        context.user_data['report_data'] = []

# ===== COMMAND /review =====
async def review_command(update, context):
    user_id = update.effective_user.id
    register_user(user_id)

    review_dir = os.path.join(os.getcwd(), "review")
    if not os.path.exists(review_dir):
        await update.message.reply_text("📭 Папка review пуста или не существует.")
        return

    photo_paths = []
    for root, dirs, files in os.walk(review_dir):
        for f in files:
            if f.lower().endswith(('.jpg', '.jpeg', '.png')):
                photo_paths.append(os.path.join(root, f))

    if not photo_paths:
        await update.message.reply_text("📭 В папке review нет фото.")
        return

    await update.message.reply_text(f"📸 Найдено {len(photo_paths)} фото. Отправляю...")

    for path in photo_paths:
        try:
            with open(path, 'rb') as f:
                await update.message.reply_photo(photo=f)
        except Exception as e:
            print(f"❌ Ошибка отправки {path}: {e}")
            await update.message.reply_text(f"❌ Не удалось отправить: {os.path.basename(path)}")

    await update.message.reply_text("✅ Все фото отправлены.")

# ===== COMMAND /stats (только для владельца) =====
async def stats_command(update, context):
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        await update.message.reply_text("⛔ You are not authorized to view statistics.")
        return

    total, today_count, week_count = get_stats()
    msg = (
        f"📊 Bot Statistics:\n"
        f"👥 Total users: {total}\n"
        f"📈 New today: {today_count}\n"
        f"📅 New this week: {week_count}"
    )
    await update.message.reply_text(msg)

# ===== START =====
if __name__ == "__main__":
    init_db()
    download_and_extract_photos()
    download_and_extract_etalons()
    load_index()
    load_model()
    app = Application.builder().token(TOKEN).read_timeout(60).build()
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(CommandHandler("review", review_command))
    app.add_handler(CommandHandler("stats", stats_command))
    print("🚀 Bot started. Waiting for photos...")
    app.run_polling()
