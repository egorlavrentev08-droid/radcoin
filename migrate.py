# migrate.py - Ручная миграция базы данных
# Версия: 4.0.0 (ALPHA)

import sqlite3
import os
from datetime import datetime

DB_PATH = 'radcoin_bot.db'


def run_migration():
    """Запуск миграции базы данных"""
    
    if not os.path.exists(DB_PATH):
        print(f"❌ База данных не найдена по пути: {DB_PATH}")
        print("Сначала запустите бота, чтобы база создалась")
        return False
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Получаем список существующих колонок в таблице users
    cursor.execute("PRAGMA table_info(users)")
    existing_columns = [col[1] for col in cursor.fetchall()]
    
    print("=" * 50)
    print("🔄 Миграция базы данных RadCoin Bot")
    print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)
    
    # ==================== НОВЫЕ КОЛОНКИ ДЛЯ ТАБЛИЦЫ USERS ====================
    
    # Колонки для лаборатории, эффектов, металлоискателя и рюкзаков (ALPHA 4.0)
    new_columns = {
        'last_lab': 'DATETIME',
        'energy_drink_level': 'TEXT DEFAULT "strike"',
        'reducer_level': 'TEXT DEFAULT "basic"',
        'last_metal_detector': 'DATETIME',
        'last_metal_detector_duration': 'INTEGER DEFAULT 3',
        'energy_drink_stacks': 'INTEGER DEFAULT 0',
        'reducer_stacks': 'INTEGER DEFAULT 0',
        'shop_purchases': 'TEXT DEFAULT \'{}\'',
        'last_shop_reset': 'DATETIME',
    }
    
    print("\n📋 Проверка колонок в таблице users...")
    
    for col_name, col_type in new_columns.items():
        if col_name not in existing_columns:
            try:
                cursor.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_type}")
                print(f"  ✅ Добавлена колонка: {col_name} ({col_type})")
            except sqlite3.Error as e:
                print(f"  ❌ Ошибка при добавлении {col_name}: {e}")
        else:
            print(f"  ⏭️ Колонка уже существует: {col_name}")
    
    # ==================== НОВЫЕ КОЛОНКИ ДЛЯ ТАБЛИЦЫ CLANS ====================
    
    # Проверяем таблицу clans
    cursor.execute("PRAGMA table_info(clans)")
    existing_clans_columns = [col[1] for col in cursor.fetchall()]
    
    # Колонки для кланов (ALPHA 4.0)
    clans_new_columns = {
        'max_members': 'INTEGER DEFAULT 50',
    }
    
    print("\n📋 Проверка колонок в таблице clans...")
    
    for col_name, col_type in clans_new_columns.items():
        if col_name not in existing_clans_columns:
            try:
                cursor.execute(f"ALTER TABLE clans ADD COLUMN {col_name} {col_type}")
                print(f"  ✅ Добавлена колонка: {col_name} ({col_type})")
            except sqlite3.Error as e:
                print(f"  ❌ Ошибка при добавлении {col_name}: {e}")
        else:
            print(f"  ⏭️ Колонка уже существует: {col_name}")
    
    # ==================== ПРОВЕРКА СУЩЕСТВОВАНИЯ ТАБЛИЦ ====================
    
    # Проверяем таблицу radio_groups
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='radio_groups'")
    if not cursor.fetchone():
        cursor.execute("""
            CREATE TABLE radio_groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER UNIQUE,
                chat_title TEXT,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        print("  ✅ Создана таблица: radio_groups")
    else:
        print("  ⏭️ Таблица уже существует: radio_groups")
    
    # Проверяем таблицу user_logs
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='user_logs'")
    if not cursor.fetchone():
        cursor.execute("""
            CREATE TABLE user_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT,
                action TEXT,
                amount_rc REAL DEFAULT 0,
                amount_rf INTEGER DEFAULT 0,
                amount_crystals INTEGER DEFAULT 0,
                item TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        """)
        print("  ✅ Создана таблица: user_logs")
    else:
        print("  ⏭️ Таблица уже существует: user_logs")
    
    # ==================== ПРОВЕРКА ЗНАЧЕНИЙ ПО УМОЛЧАНИЮ ====================
    
    print("\n📋 Проверка значений по умолчанию...")
    
    # Устанавливаем уровень энергетика по умолчанию для старых пользователей
    cursor.execute("UPDATE users SET energy_drink_level = 'strike' WHERE energy_drink_level IS NULL")
    print("  ✅ energy_drink_level установлен в 'strike' для старых записей")
    
    # Устанавливаем уровень редуктора по умолчанию для старых пользователей
    cursor.execute("UPDATE users SET reducer_level = 'basic' WHERE reducer_level IS NULL")
    print("  ✅ reducer_level установлен в 'basic' для старых записей")
    
    # Устанавливаем стеки энергетика по умолчанию
    cursor.execute("UPDATE users SET energy_drink_stacks = 0 WHERE energy_drink_stacks IS NULL")
    print("  ✅ energy_drink_stacks установлен в 0 для старых записей")
    
    # Устанавливаем стеки редуктора по умолчанию
    cursor.execute("UPDATE users SET reducer_stacks = 0 WHERE reducer_stacks IS NULL")
    print("  ✅ reducer_stacks установлен в 0 для старых записей")
    
    # Устанавливаем длительность кулдауна металлоискателя
    cursor.execute("UPDATE users SET last_metal_detector_duration = 3 WHERE last_metal_detector_duration IS NULL")
    print("  ✅ last_metal_detector_duration установлен в 3 для старых записей")
    
    # Устанавливаем пустой инвентарь для старых записей, если NULL
    cursor.execute("UPDATE users SET inventory = '[]' WHERE inventory IS NULL")
    print("  ✅ inventory установлен в '[]' для старых записей")
    
    # Устанавливаем пустую экипировку для старых записей, если NULL
    cursor.execute("UPDATE users SET equipped = '{}' WHERE equipped IS NULL")
    print("  ✅ equipped установлен в '{}' для старых записей")
    
    # Устанавливаем пустые достижения для старых записей, если NULL
    cursor.execute("UPDATE users SET achievements = '[]' WHERE achievements IS NULL")
    print("  ✅ achievements установлен в '[]' для старых записей")
    
    # Устанавливаем пустые покупки магазина
    cursor.execute("UPDATE users SET shop_purchases = '{}' WHERE shop_purchases IS NULL")
    print("  ✅ shop_purchases установлен в '{}' для старых записей")
    
    # Устанавливаем max_members для старых кланов
    cursor.execute("UPDATE clans SET max_members = 50 WHERE max_members IS NULL")
    print("  ✅ max_members установлен в 50 для старых кланов")
    
    # ==================== ПРОВЕРКА НАЛИЧИЯ НОВЫХ ПРЕДМЕТОВ В ИНВЕНТАРЕ ====================
    
    # Эта проверка не нужна — инвентарь хранится как JSON, старые предметы остаются
    
    # ==================== ЗАВЕРШЕНИЕ ====================
    
    conn.commit()
    conn.close()
    
    print("\n" + "=" * 50)
    print("✅ Миграция базы данных завершена успешно!")
    print("=" * 50)
    print("\n📌 Новые поля добавлены:")
    print("  • last_lab — время последней лаборатории")
    print("  • energy_drink_level — тип активного энергетика")
    print("  • reducer_level — тип активного редуктора")
    print("  • last_metal_detector — время последнего использования металлоискателя")
    print("  • last_metal_detector_duration — кулдаун металлоискателя")
    print("  • energy_drink_stacks — количество стеков энергетика")
    print("  • reducer_stacks — количество стеков редуктора")
    print("  • shop_purchases — лимиты покупок в магазине")
    print("  • last_shop_reset — время сброса магазина")
    print("  • max_members (clans) — лимит участников клана")
    
    return True


if __name__ == '__main__':
    run_migration()
