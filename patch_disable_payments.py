"""
patch_disable_payments.py
Отключает кнопки оплаты (Stars, USDT) в bot.py — заглушка.
"""
from pathlib import Path

FILE = Path("bot.py")
text = FILE.read_text(encoding="utf-8")

# 1. Убираем кнопку "Купить звёзды" из главного меню
old_buy = """    buttons.append([InlineKeyboardButton(T[lang].get('buy_menu', '💳 Buy stars'), callback_data="buy_checks")])\n"""
new_buy = """    # ВРЕМЕННО ОТКЛЮЧЕНО: покупка звёзд\n"""
if old_buy in text:
    text = text.replace(old_buy, new_buy)
    print("[OK] Убрана кнопка 'Купить звёзды' из главного меню")
else:
    print("[WARN] Кнопка 'Купить звёзды' не найдена (возможно, уже убрана)")

# 2. Заглушка на buy_checks
old_block = """        if data == "buy_checks":
            free, paid = get_balance(user_id)
            balance_line = f"\\n\\n💰 {t['balance_text'].format(free=free, paid=paid)}"
            await safe_edit(query,
                f"{t.get('buy_welcome', '💳 Top up balance')}{balance_line}\\n\\n"
                f"⭐ Telegram Stars — мгновенно\\n💎 USDT TRC20 — для крупных сумм",
                reply_markup=get_buy_packages_keyboard(lang))
            return"""

new_block = """        if data == "buy_checks":
            await safe_edit(query,
                "⏸ Пополнение баланса временно недоступно.\\n\\n"
                "📊 Составление смет — работает.\\n"
                "📷 Проверка фото — работает.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(t.get('back_to_menu', '« Назад'), callback_data="main_menu")]
                ]))
            return"""

if old_block in text:
    text = text.replace(old_block, new_block)
    print("[OK] Заглушка на 'buy_checks' установлена")
else:
    print("[WARN] Блок 'buy_checks' не найден — возможно, уже заглушён")

# 3. Убираем кнопку "Купить" из buy_keyboard (если есть)
old_buy_kb = """def get_buy_keyboard(lang):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(T[lang]['buy_button'], callback_data="buy_checks")],
        [InlineKeyboardButton(T[lang].get('back_to_menu', '« Back to menu'), callback_data="main_menu")]
    ])"""
new_buy_kb = """def get_buy_keyboard(lang):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(T[lang].get('back_to_menu', '« Back to menu'), callback_data="main_menu")]
    ])"""
if old_buy_kb in text:
    text = text.replace(old_buy_kb, new_buy_kb)
    print("[OK] Убрана кнопка 'Купить' из buy_keyboard")
else:
    print("[WARN] buy_keyboard не найден")

FILE.write_text(text, encoding="utf-8")
print("[OK] bot.py обновлён")
print("     - Кнопка 'Купить звёзды' убрана из меню")
print("     - Кнопка 'Купить' убрана из balance")
print("     - Заглушка на buy_checks установлена")