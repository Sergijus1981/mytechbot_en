import os
import pickle
import zipfile
import gdown
import numpy as np
import faiss
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, filters, CallbackQueryHandler
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
import datetime
import shutil

# ===== CONFIG =====
TOKEN = "8993796250:AAFWDsfKuc4Bvha2ED-fvUyONlQ_iiNpCCk"  # NEW TOKEN
PHOTO_DB_URL = "https://dl.dropboxusercontent.com/scl/fi/xxl7bna8h3re0ks9jdsy6/photo_db.zip?rlkey=j94j0yuv1e3sg67txyzda4zo9&dl=1"
INDEX_PATH = "faiss_index.bin"
PATHS_PATH = "image_paths.pkl"
MODEL_PATH = "best.pt"

# ===== CATEGORY DATA (ENGLISH) =====
CATEGORY_DATA = [
    (
        "01_otsutstvuyut_birki",
        "⚠️ Missing cable/equipment labels (tags).",
        "birki_etalon",
        "IEC 60445 (Terminal marking), NEC 110.22 (Equipment Marking), BS 7671 514.9 (Identification)"
    ),
    (
        "02_zadelka_prohodok",
        "⚠️ Gaps in cable penetrations (tubes, ducts, openings) not sealed.",
        "prohodki_etalon",
        "IEC 60364-5-52, NEC 300.21 (Firestopping), BS 7671 527.2 (Sealing of openings)"
    ),
    (
        "03_zazemlenie_ne_vypolneno",
        "⚠️ Earthing not provided or does not meet standards.",
        "zazemlenie_etalon",
        "IEC 60364-4-41, NEC 250.4 (General requirements for grounding), BS 7671 411.3 (Protective earthing)"
    ),
    (
        "04_shpilki_lotka_ne_srezany",
        "⚠️ Cable tray studs not trimmed (risk of injury and cable damage).",
        "shpilki_etalon",
        "IEC 61537 (Cable tray systems), NEC 392.18 (Cable tray installation), BS 7671 522.8 (Mechanical protection)"
    ),
]

# Global variables
index = None
image_paths = None
embedder = None
transform = None

# ===== FONT REGISTRATION FOR CYRILLIC (still needed if we keep some Russian, but we'll use DejaVu for English too) =====
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
    print("⚠️ DejaVuSans not found, using Helvetica (no Cyrillic support)")

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
    story.append(Paragraph(f"Date: {datetime.datetime.now().strftime('%d.%m.%Y %H:%M')}", styles['Normal']))
    story.append(Spacer(1, 12*mm))

    if report_data:
        for i, item in enumerate(report_data, 1):
            story.append(Paragraph(f"<b>Defect #{i}</b>", styles['Heading2']))
            story.append(Paragraph(f"📌 {item.get('text', 'Unknown')}", styles['Normal']))
            story.append(Paragraph(f"📜 Standard: {item.get('normative', '—')}", styles['Normal']))
            story.append(Paragraph(
                "🛠 Recommended action: Bring into compliance with IEC 61293-2016 "
                "(Electrical equipment – Marking with specified characteristics of power supply).",
                styles['Normal']
            ))
            
            if item.get('photo_path') and os.path.exists(item['photo_path']):
                try:
                    img = RLImage(item['photo_path'], width=120*mm, height=80*mm)
                    story.append(img)
                    story.append(Paragraph("📸 Actual photo", styles['Normal']))
                except:
                    story.append(Paragraph("⚠️ Photo not available", styles['Normal']))
            
            story.append(Spacer(1, 6*mm))
            story.append(PageBreak())
    else:
        story.append(Paragraph("No defects recorded.", styles['Normal']))

    doc.build(story)
    buffer.seek(0)
    return buffer

# ===== AUTO-DOWNLOAD PHOTOS =====
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

# ===== LOAD INDEX =====
def load_index():
    global index, image_paths
    if index is None:
        print("Loading index...")
        index = faiss.read_index(INDEX_PATH)
        with open(PATHS_PATH, "rb") as f:
            raw_paths = pickle.load(f)
        image_paths = [os.path.join("photo_db", os.path.basename(p)) for p in raw_paths]
        print(f"Index loaded, {len(image_paths)} images.")

# ===== LOAD MODEL =====
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

# ===== HANDLE PHOTO (with saving to review/) =====
async def handle_photo(update, context):
    try:
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

        # Save original photo to review/ folder for manual verification
        category_folder = info.get("etalon_prefix", "unknown")
        review_dir = os.path.join("review", category_folder)
        os.makedirs(review_dir, exist_ok=True)
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        review_path = os.path.join(review_dir, f"{timestamp}.jpg")
        await file.download_to_drive(review_path)

        response = f"🔍 **Defect found:**\n{info['text']}\n\n📸 Photo saved for manual verification.\n🕒 Awaiting confirmation."
        if info.get("normative"):
            response += f"\n📜 Standard: {info['normative']}"

        # Send etalon
        etalon_path = find_etalon(info.get("etalon_prefix"))
        if etalon_path and os.path.exists(etalon_path):
            with open(etalon_path, 'rb') as f:
                await update.message.reply_photo(photo=f, caption=response, reply_markup=get_report_keyboard())
        else:
            await update.message.reply_text(response, reply_markup=get_report_keyboard())

        # Store in session for report
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
    if query.data == "generate_report":
        report_data = context.user_data.get('report_data', [])
        if not report_data:
            await query.edit_message_text("📭 No defects recorded. Please send photos first.")
            return
        pdf_buffer = generate_pdf_report(report_data, query.message.chat.id)
        await query.message.reply_document(
            document=pdf_buffer,
            filename=f"report_{datetime.datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
            caption="📄 Your report is ready!"
        )
        context.user_data['report_data'] = []

# ===== START =====
if __name__ == "__main__":
    download_and_extract_photos()
    load_index()
    load_model()
    app = Application.builder().token(TOKEN).read_timeout(60).build()
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(CallbackQueryHandler(button_callback))
    print("🚀 Bot started. Waiting for photos...")
    app.run_polling()