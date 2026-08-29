import requests
import zipfile
import os
import time

def download_and_extract_etalons():
    if os.path.exists("etalons") and len(os.listdir("etalons")) > 0:
        print("📁 etalons already exists, skipping download.")
        return

    print("📥 Downloading etalons archive using gdown (fallback to requests)...")
    
    # Пробуем через gdown (как работает для photo_db)
    try:
        import gdown
        gdown.download(ETALONS_URL, "etalons.zip", quiet=False)
    except Exception as e:
        print(f"⚠️ gdown failed: {e}, falling back to requests with headers...")
        # Пробуем через requests с заголовками (чтобы имитировать браузер)
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        response = requests.get(ETALONS_URL, stream=True, headers=headers)
        with open("etalons.zip", "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

    # Проверяем, что скачался именно zip-файл
    if not os.path.exists("etalons.zip"):
        print("❌ etalons.zip not downloaded!")
        return

    # Проверяем первые байты (сигнатура zip)
    with open("etalons.zip", "rb") as f:
        header = f.read(4)
        if header != b'PK\x03\x04' and header != b'PK\x05\x06' and header != b'PK\x07\x08':
            print(f"⚠️ Downloaded file is not a zip (header: {header})")
            # Если это не zip, удаляем и выходим
            os.remove("etalons.zip")
            return

    print("📦 Extracting...")
    try:
        with zipfile.ZipFile("etalons.zip", "r") as zip_ref:
            zip_ref.extractall(".")
        os.remove("etalons.zip")
        print("✅ Etalons ready.")
    except zipfile.BadZipFile as e:
        print(f"❌ BadZipFile: {e}")
        # Покажем, что внутри файла (первые 500 символов)
        with open("etalons.zip", "rb") as f:
            content = f.read(500)
            print(f"First 500 bytes: {content}")
        os.remove("etalons.zip")
        raise
