"""
patch_special_notes.py
Добавляет SPECIAL_NOTES для УППВ, УО, БАО-300.
Обновляет цены в MANUAL_PRICES.
"""
import re
from pathlib import Path

FILE = Path("make_smeta_eom.py")
text = FILE.read_text(encoding="utf-8")

# 1. Обновить цены
text = text.replace('"уппв л01": 0.0,', '"уппв л01": 534360.0,')
text = text.replace('"уо л01": 0.0,', '"уо л01": 300000.0,')

# 2. Добавить SPECIAL_NOTES после MANUAL_PRICES
if 'SPECIAL_NOTES = {' not in text:
    marker = 'CUSTOM_ASSEMBLY_KEYWORDS = ['
    notes = '''SPECIAL_NOTES = {
    "уппв л01": "Аналог: ЦПИ УППВ 1918 М1 исп. У. Требует согласования с проектировщиком.",
    "уо л01": "Аналог: ЦПИ УО 1918. Требует согласования с проектировщиком.",
    "бао-300": "Уточнить у Ловител.",
    "узел подачи программ вещания": "Аналог: ЦПИ УППВ 1918 М1. Требует согласования.",
    "узел оповещения": "Аналог: ЦПИ УО 1918. Требует согласования.",
}

'''
    text = text.replace(marker, notes + marker, 1)

# 3. Использовать SPECIAL_NOTES в search_with_hubs
old = '''            "note": "проверенная цена",
            "manual_key": _mk,'''
new = '''            "note": SPECIAL_NOTES.get(_mk, "проверенная цена"),
            "manual_key": _mk,'''

if old in text:
    text = text.replace(old, new)
    print("[OK] SPECIAL_NOTES подключены в search_with_hubs")
else:
    print("[WARN] Не нашёл 'note': 'проверенная цена' — возможно, уже пропатчено")

FILE.write_text(text, encoding="utf-8")
print("[OK] Файл обновлён")
print("     УППВ = 534 360 руб")
print("     УО = 300 000 руб")