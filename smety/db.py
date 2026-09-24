"""База данных смет: продукты, цены, сметы."""
import sqlite3
import datetime as dt
from pathlib import Path

DB_PATH = Path("/data/smety.db") if Path("/data").exists() else Path("smety.db")


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Продукты (оборудование и материалы)
    c.execute('''CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        brand TEXT,
        model TEXT,
        code TEXT,
        vendor TEXT,
        unit TEXT,
        category TEXT,
        created_at TEXT,
        updated_at TEXT
    )''')
    
    # Цены (история)
    c.execute('''CREATE TABLE IF NOT EXISTS prices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id INTEGER,
        price REAL,
        source TEXT,
        vendor TEXT,
        date TEXT,
        FOREIGN KEY (product_id) REFERENCES products(id)
    )''')
    
    # Сметы
    c.execute('''CREATE TABLE IF NOT EXISTS estimates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        total_materials REAL,
        total_works REAL,
        total_nds REAL,
        total_all REAL,
        created_at TEXT
    )''')
    
    # Позиции в смете
    c.execute('''CREATE TABLE IF NOT EXISTS estimate_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        estimate_id INTEGER,
        product_id INTEGER,
        position TEXT,
        section TEXT,
        name TEXT,
        qty REAL,
        price REAL,
        sum REAL,
        status TEXT,
        FOREIGN KEY (estimate_id) REFERENCES estimates(id),
        FOREIGN KEY (product_id) REFERENCES products(id)
    )''')
    
    # Дилеры
    c.execute('''CREATE TABLE IF NOT EXISTS dealers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        brand TEXT,
        name TEXT,
        contact TEXT,
        discount REAL,
        notes TEXT
    )''')
    
    conn.commit()
    conn.close()
    print("✅ База инициализирована:", DB_PATH)


if __name__ == "__main__":
    init_db()