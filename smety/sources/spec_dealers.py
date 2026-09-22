"""
sources/spec_dealers.py
Парсер специализированного оборудования (пожарка, охрана)
через дилерские сайты: techbuy, ter-bez, e-kc, planetasveta и др.

Не блокируются (в отличие от ChipDip).
Приоритет запроса: артикул (Rbz-XXXXXX) → название.
"""
import re
import time
import logging
from urllib.parse import quote_plus, urljoin

import requests
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ru-RU,ru;q=0.9",
}

DEALERS = [
    {
        "name": "TechBuy",
        "search": "https://techbuy.ru/search/?q={q}",
        "price_pattern": r"(\d[\d\s]{2,10}[,.]\d{2})\s*₽",
    },
    {
        "name": "Территория безопасности",
        "search": "https://ter-bez.ru/search/?q={q}",
        "price_pattern": r"(\d[\d\s]{2,10})\s*₽",
    },
    {
        "name": "E-KC",
        "search": "https://e-kc.ru/search/?q={q}",
        "price_pattern": r"(\d[\d\s]{2,10}[,.]\d{2})\s*₽",
    },
    {
        "name": "Планета Света",
        "search": "https://planetasveta.pro/search/?q={q}",
        "price_pattern": r"(\d[\d\s]{2,10}[,.]\d{2})\s*руб",
    },
    {
        "name": "RESanteh",
        "search": "https://resanteh.ru/search/?q={q}",
        "price_pattern": r"(\d[\d\s]{2,10})[\s,.]*(?:₽|руб)",
    },
    {
        "name": "Teploluxe",
        "search": "https://teploluxe.ru/search/?q={q}",
        "price_pattern": r"(\d[\d\s]{2,10})[\s,.]*(?:₽|руб)",
    },
    {
        "name": "ELAB",
        "search": "https://elab.com.ru/search/?q={q}",
        "price_pattern": r"(\d[\d\s]{2,10})[\s,.]*(?:₽|руб)",
    },
    {
        "name": "ChipDip",
        "search": "https://www.chipdip.ru/search?searchtext={q}",
        "price_pattern": r"(\d[\d\s]{2,10})[\s,.]*(?:₽|руб)",
    },
    {
        "name": "Rusklimat B2B",
        "search": "https://b2b.rusklimat.com/search/?q={q}",
        "price_pattern": r"(\d[\d\s]{2,10})[\s,.]*(?:₽|руб)",
    },
]

HOMOGLYPHS_LAT2CYR = str.maketrans({
    "A": "А", "B": "В", "E": "Е", "K": "К", "M": "М",
    "H": "Н", "O": "О", "P": "Р", "C": "С", "T": "Т",
    "X": "Х", "Y": "У",
})

HOMOGLYPHS_CYR2LAT = str.maketrans({
    "А": "A", "В": "B", "Е": "E", "К": "K", "М": "M",
    "Н": "H", "О": "O", "Р": "P", "С": "C", "Т": "T",
    "Х": "X", "У": "Y",
})

# Названия-мусор, которые берутся из ссылок-кнопок и табов, а не из карточек товара
BAD_NAMES = {
    # кнопки действий
    "быстрый просмотр", "в корзину", "купить", "сравнить",
    "подробнее", "в избранное", "заказать", "в корзине",
    # табы на карточке товара
    "описание товара", "описание", "характеристики", "отзывы",
    "документы", "доставка", "оплата", "гарантия",
}


def _to_cyrillic(s):
    return s.translate(HOMOGLYPHS_LAT2CYR)


def _to_latin(s):
    return s.translate(HOMOGLYPHS_CYR2LAT)


def _norm(s):
    if not s:
        return ""
    s = s.lower()
    s = s.translate(HOMOGLYPHS_CYR2LAT)
    s = re.sub(r"[\s\-_/\\.,()\"']+", "", s)
    return s


def _clean_price(raw):
    if not raw:
        return None
    s = raw.replace("\xa0", " ").replace(" ", "").replace(",", ".")
    m = re.search(r"\d+(?:\.\d+)?", s)
    return float(m.group()) if m else None


def _get(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=15, allow_redirects=True)
        return r if r.status_code == 200 else None
    except Exception as e:
        log.debug("HTTP error %s: %s", url, e)
        return None


def _is_service(href):
    """True — если ссылка служебная (не карточка товара)."""
    if not href:
        return True
    h = href.lower()
    for s in ["/auth", "compare", "favorite", "basket",
              "login", "register", "javascript:", "mailto:"]:
        if s in h:
            return True
    return False


def _name_from_url(href):
    """Достаёт читаемое имя из URL карточки как fallback."""
    tail = href.rstrip("/").split("/")[-1]
    tail = tail.replace("_product", "").replace("_", " ").strip()
    return tail[:120]


def _is_bad_name(name):
    if not name:
        return True
    n = name.lower().strip()
    if n in BAD_NAMES:
        return True
    if len(n) < 10:
        return True
    return False


def search_dealer(dealer, query):
    """Ищет товар у одного дилера (универсально, через блоки цены)."""
    url = dealer["search"].format(q=quote_plus(query))
    r = _get(url)
    if not r:
        return []

    final_url = r.url  # после редиректов (Планета Света редиректит на карточку)

    soup = BeautifulSoup(r.text, "html.parser")
    results = []

    price_blocks = soup.find_all(class_=re.compile(r"price", re.IGNORECASE))
    for pb in price_blocks:
        raw_price = pb.get_text(" ", strip=True)
        m = re.search(dealer["price_pattern"], raw_price)
        if not m:
            continue
        price = _clean_price(m.group(1))
        if not price or price < 100:
            continue

        container = pb
        for _ in range(6):
            if container is None:
                break
            link = container.find("a", href=re.compile(r"/product/"))
            if link and not _is_service(link.get("href", "")):
                href = link["href"]
                name = link.get_text(strip=True)

                # если имя — мусорная кнопка/таб, пробуем h1/h2/h3 рядом
                if _is_bad_name(name):
                    h = container.find(["h3", "h2", "h1"])
                    if h:
                        name = h.get_text(strip=True)

                # если всё ещё мусор — берём из URL
                if _is_bad_name(name):
                    name = _name_from_url(href)

                results.append({
                    "name": name[:120],
                    "price": price,
                    "url": urljoin(final_url.split("/search")[0], href),
                    "dealer": dealer["name"],
                })
                break
            container = container.parent

    seen = set()
    out = []
    for r in results:
        if r["url"] in seen:
            continue
        seen.add(r["url"])
        out.append(r)

    return out[:3]


def find_prices(query, keywords=None):
    """Ищет цену у всех дилеров. Приоритет: артикул → название."""
    all_results = []

    article_queries = []
    if keywords:
        for k in keywords:
            # артикул — есть и цифры, и дефис/подчёркивание (Rbz-377219, R3-MC-E)
            if re.search(r"\d", k) and re.search(r"[-_]", k):
                article_queries.append(k)

    queries = article_queries + [query]

    for dealer in DEALERS:
        dealer_results = []
        for q in queries:
            try:
                res = search_dealer(dealer, q)
                if keywords and res:
                    # ключ ищем в названии ИЛИ в URL
                    res = [
                        r for r in res
                        if any(
                            _norm(k) in _norm(r["name"]) or _norm(k) in _norm(r["url"])
                            for k in keywords
                        )
                    ]
                dealer_results.extend(res)
                if dealer_results:
                    break
            except Exception as e:
                log.debug("%s / %s: %s", dealer["name"], q, e)
            time.sleep(0.3)

        if dealer_results:
            log.info("%s: %d предложений", dealer["name"], len(dealer_results))
            all_results.extend(dealer_results[:2])
        time.sleep(0.3)

    if not all_results:
        return []

    prices = sorted([r["price"] for r in all_results])
    if len(prices) >= 3:
        cutoff = prices[1]
    else:
        cutoff = prices[0]

    out = [r for r in all_results if abs(r["price"] - cutoff) / cutoff < 0.05]
    return out[:3]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("--- Тест: R3-MC-E ---")
    for r in find_prices("R3-MC-E", keywords=["R3-MC-E", "Rbz-377219"]):
        print(r)
    print("\n--- Тест: ИП 212-64 ---")
    for r in find_prices("ИП 212-64", keywords=["ИП 212"]):
        print(r)
    print("\n--- Тест: R3-Рубеж-2ОП ---")
    for r in find_prices("R3-Рубеж-2ОП", keywords=["R3-Рубеж-2ОП"]):
        print(r)