import requests
from bs4 import BeautifulSoup
import re

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "ru-RU,ru;q=0.9",
}

def search_petrovich(query):
    """Ищет товар на petrovich.ru"""
    print(f"🔍 Ищу: {query}")
    
    url = "https://petrovich.ru/search/"
    params = {"q": query}
    
    try:
        r = requests.get(url, params=params, headers=HEADERS, timeout=15)
        print(f"📡 Статус: {r.status_code}")
        print(f"📏 Длина ответа: {len(r.text)}")
        
        if r.status_code != 200:
            print("❌ Не 200. Блокировка?")
            return None
        
        soup = BeautifulSoup(r.text, "html.parser")
        
        # Ищем блоки с ценой
        # Ищем все элементы, где есть "₽" или "руб"
        price_elements = soup.find_all(string=re.compile(r'[\d\s]+[₽руб]'))
        
        print(f"💰 Найдено элементов с ценой: {len(price_elements)}")
        
        for i, elem in enumerate(price_elements[:10], 1):
            parent = elem.parent
            text = parent.get_text(strip=True)[:100]
            print(f"   {i}. {text}")
        
        return price_elements
    
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return None

if __name__ == "__main__":
    # Тест на одной позиции
    search_petrovich("Светильник светодиодный")
