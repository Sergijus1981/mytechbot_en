# translations.py

TRANSLATIONS = {
    'ru': {
        'start': "Привет! 👋\nЯ бот технического надзора. Отправь мне фото электромонтажа, и я найду возможные нарушения.\n\nПросто отправь фото!",
        'language_selected': "Отлично! Теперь я буду отвечать на русском языке.",
        'defect_found': "🔍 **Найдено замечание:**\n{}",
        'photo_saved': "📸 Фото сохранено.",
        'standard': "📜 Норматив: {}",
        'generate_report': "📄 Сформировать отчёт",
        'no_defects': "📭 Нет замечаний для отчёта.",
        'report_ready': "📄 Ваш отчёт готов!",
        'unknown_defect': "❓ Неизвестное замечание (файл: {})",
        'choose_language': "🌍 Пожалуйста, выберите язык:",
        'error': "❌ Ошибка: {}",
        'no_photo_found': "❌ Не удалось найти похожее изображение.",

        # SMETA
        'smeta_welcome': "📊 **Составление смет**\n\nПришли мне **PDF спецификации** (ЭОМ, ЭМ).\n\n• Первая **треть сметы — бесплатно**\n• Полная смета (все позиции + работы + НДС) — за **5 проверок**\n\n📎 Пришли PDF-файл.",
        'smeta_processing': "⏳ **Принял PDF.** Обрабатываю...\n\n1. Парсинг спецификации\n2. Поиск цен на ЭТМ (~5-10 минут)\n3. Расчёт работ и НДС\n\n**Пришлю результат, когда будет готово.**",
        'smeta_free_part': "📊 **Бесплатная часть сметы** (1/3 позиций)\n\n",
        'smeta_free_item': "{i}. {name}\n   💰 {price} ₽/{unit} × {qty} = **{total} ₽**\n",
        'smeta_free_footer': "\n\n🔒 **Полная смета:** {total_count} позиций + работы + наценки + НДС.\n💰 Цена: **5 проверок**",
        'smeta_summary': "✅ **Смета готова!**\n\n📊 **Итого:**\n• Материалы: **{materials} ₽**\n• Работы: **{works} ₽**\n• НДС 20%: **{vat} ₽**\n• **ВСЕГО: {total} ₽**\n\n📎 Excel-файл ниже.",
        'smeta_error': "❌ Ошибка при обработке сметы:\n`{error}`",
        'smeta_not_enough_checks': "⚠️ Недостаточно проверок.\n\nНужно: **5 проверок**\nУ вас: **{balance}**",
        'smeta_buy': "💳 Купить проверки",
    },
    'en': {
        'start': "Hello! 👋\nI'm a technical inspection bot. Send me a photo.",
        'language_selected': "Great! Now I'll respond in English.",
        'defect_found': "🔍 **Defect found:**\n{}",
        'photo_saved': "📸 Photo saved.",
        'standard': "📜 Standard: {}",
        'generate_report': "📄 Generate Report",
        'no_defects': "📭 No defects recorded.",
        'report_ready': "📄 Your report is ready!",
        'unknown_defect': "❓ Unknown defect (file: {})",
        'choose_language': "🌍 Please choose your language:",
        'error': "❌ Error: {}",
        'no_photo_found': "❌ Could not find a matching image.",

        # SMETA
        'smeta_welcome': "📊 **Estimates (smeta)**\n\nSend me a **PDF specification**.\n\n• First **third of the estimate free**\n• Full estimate (items + works + VAT) — for **5 checks**\n\n📎 Send a PDF file.",
        'smeta_processing': "⏳ **PDF received.** Processing...\n\n1. Parsing\n2. Searching prices on ETM (~5-10 min)\n3. Calculating works and VAT\n\n**I'll send the result when ready.**",
        'smeta_free_part': "📊 **Free part of estimate** (1/3 of items)\n\n",
        'smeta_free_item': "{i}. {name}\n   💰 {price} ₽/{unit} × {qty} = **{total} ₽**\n",
        'smeta_free_footer': "\n\n🔒 **Full estimate:** {total_count} items + works + markups + VAT.\n💰 Price: **5 checks**",
        'smeta_summary': "✅ **Estimate ready!**\n\n📊 **Total:**\n• Materials: **{materials} ₽**\n• Works: **{works} ₽**\n• VAT 20%: **{vat} ₽**\n• **GRAND TOTAL: {total} ₽**\n\n📎 Excel file below.",
        'smeta_error': "❌ Estimate processing error:\n`{error}`",
        'smeta_not_enough_checks': "⚠️ Not enough checks.\n\nNeed: **5 checks**\nYou have: **{balance}**",
        'smeta_buy': "💳 Buy checks",
    }
}


def get_text(lang, key, **kwargs):
    """Возвращает перевод по ключу с подстановкой параметров."""
    text = TRANSLATIONS.get(lang, TRANSLATIONS['en']).get(key, key)
    if kwargs:
        text = text.format(**kwargs)
    return text
