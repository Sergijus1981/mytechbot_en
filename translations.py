# translations.py

TRANSLATIONS = {
    'ru': {
        'start': "Привет! 👋\nЯ бот для технического надзора. Отправь мне фото электромонтажа, и я найду возможные нарушения.\n\nПросто отправь фото!",
        'language_selected': "Отлично! Теперь я буду отвечать на русском языке. Отправь мне фото электромонтажа, и я проверю его.",
        'defect_found': "🔍 **Найдено замечание:**\n{}",
        'photo_saved': "📸 Фото сохранено для ручной проверки инспектором.\n🕒 Ожидайте подтверждения.",
        'standard': "📜 Норматив: {}",
        'generate_report': "📄 Сформировать отчёт",
        'no_defects': "📭 Нет замечаний для отчёта. Сначала отправьте фотографии.",
        'report_ready': "📄 Ваш отчёт готов!",
        'unknown_defect': "📌 Неизвестное замечание (файл: {})",
        'choose_language': "🌍 Пожалуйста, выберите язык:",
        'error': "❌ Ошибка: {}",
        'no_photo_found': "❌ Не удалось найти похожее изображение в базе."
    },
    'en': {
        'start': "Hello! 👋\nI'm a technical inspection bot. Send me a photo of electrical installation, and I'll find possible violations.\n\nJust send a photo!",
        'language_selected': "Great! Now I'll respond in English. Send me a photo of electrical installation, and I'll check it.",
        'defect_found': "🔍 **Defect found:**\n{}",
        'photo_saved': "📸 Photo saved for manual verification.\n🕒 Awaiting confirmation.",
        'standard': "📜 Standard: {}",
        'generate_report': "📄 Generate Report",
        'no_defects': "📭 No defects recorded. Please send photos first.",
        'report_ready': "📄 Your report is ready!",
        'unknown_defect': "📌 Unknown defect (file: {})",
        'choose_language': "🌍 Please choose your language:",
        'error': "❌ Error: {}",
        'no_photo_found': "❌ Could not find a matching image in the database."
    }
}

def get_text(lang, key, **kwargs):
    """Возвращает перевод по ключу с подстановкой параметров."""
    text = TRANSLATIONS.get(lang, TRANSLATIONS['en']).get(key, key)
    if kwargs:
        text = text.format(**kwargs)
    return text