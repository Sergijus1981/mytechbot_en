import os
import requests
import zipfile
import subprocess

# ===== КОНФИГУРАЦИЯ =====
# file_id архивов (получить, отправив файлы боту и взяв из логов или через команду /get_id)
PHOTO_DB_FILE_ID = "ВАШ_FILE_ID_ДЛЯ_PHOTO_DB_ZIP"
ETALONS_FILE_ID = "ВАШ_FILE_ID_ДЛЯ_ETALONS_ZIP"

# ===== ФУНКЦИЯ СКАЧИВАНИЯ ПО FILE_ID =====
def download_file_by_id(file_id, destination):
    """Скачивает файл из Telegram по его file_id"""
    try:
        # Получаем объект файла
        file_info = bot.get_file(file_id)  # Нужно иметь доступ к экземпляру бота
        # Скачиваем
        file_info.download(destination)
        print(f"✅ Файл сохранён: {destination}")
        return True
    except Exception as e:
        print(f"❌ Ошибка скачивания: {e}")
        return False

# ===== ЗАГРУЗКА АРХИВОВ (ЕСЛИ НЕТ ЛОКАЛЬНЫХ ПАПОК) =====
def download_and_extract_photos():
    if os.path.exists("photo_db") and len(os.listdir("photo_db")) > 0:
        print("📁 photo_db уже существует, пропускаю.")
        return

    print("📥 Скачиваю photo_db.zip из Telegram...")
    if not download_file_by_id(PHOTO_DB_FILE_ID, "photo_db.zip"):
        print("❌ Не удалось скачать photo_db.zip")
        return

    print("📦 Распаковываю...")
    with zipfile.ZipFile("photo_db.zip", "r") as zf:
        zf.extractall(".")
    os.remove("photo_db.zip")

    # Если папка photo_db не создалась — исправляем
    if not os.path.exists("photo_db"):
        # Поищем папку, которая могла распаковаться с другим именем
        for item in os.listdir("."):
            if os.path.isdir(item) and item.startswith("photo_db"):
                os.rename(item, "photo_db")
                break
    print(f"✅ photo_db готова, файлов: {len(os.listdir('photo_db'))}")

def download_and_extract_etalons():
    if os.path.exists("etalons") and len(os.listdir("etalons")) > 0:
        print("📁 etalons уже существует, пропускаю.")
        return

    print("📥 Скачиваю etalons.zip из Telegram...")
    if not download_file_by_id(ETALONS_FILE_ID, "etalons.zip"):
        print("❌ Не удалось скачать etalons.zip")
        return

    print("📦 Распаковываю...")
    with zipfile.ZipFile("etalons.zip", "r") as zf:
        zf.extractall(".")
    os.remove("etalons.zip")

    if not os.path.exists("etalons"):
        for item in os.listdir("."):
            if os.path.isdir(item) and item.startswith("etalons"):
                os.rename(item, "etalons")
                break
    print(f"✅ etalons готова, файлов: {len(os.listdir('etalons'))}")
