# database.py - База данных (полностью независимый модуль)
# Версия: 4.0.0 (ALPHA)

from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, scoped_session

# ==================== СОЗДАНИЕ БАЗЫ ====================
Base = declarative_base()
engine = create_engine('sqlite:///radcoin_bot.db', pool_size=10, max_overflow=20)

# expire_on_commit=False — объекты не отваливаются после коммита
Session = scoped_session(sessionmaker(bind=engine, expire_on_commit=False))

# ==================== КОНСТАНТЫ ====================
SUPER_ADMIN_IDS = [6595788533]


# ==================== МОДЕЛЬ ПОЛЬЗОВАТЕЛЯ ====================

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, unique=True)
    username = Column(String)
    
    # Ресурсы
    radcoins = Column(Float, default=0)
    radfragments = Column(Integer, default=0)
    radcrystals = Column(Integer, default=0)
    
    # Прогресс
    level = Column(Integer, default=1)
    experience = Column(Integer, default=0)
    
    # Таймеры
    last_collection = Column(DateTime, nullable=True)
    next_collection_time = Column(DateTime, nullable=True)
    last_hunt = Column(DateTime, nullable=True)
    last_lab = Column(DateTime, nullable=True)  # для лаборатории учёных (ALPHA 4.0)
    cooldown_reducer_until = Column(DateTime, nullable=True)
    energy_drink_until = Column(DateTime, nullable=True)
    
    # Экипировка
    armor_type = Column(String, default=None)
    weapon = Column(String, default=None)
    medkits = Column(Integer, default=0)
    
    # Статистика
    total_collects = Column(Integer, default=0)
    total_rc_earned = Column(Float, default=0)
    best_collect = Column(Float, default=0)
    mutants_killed = Column(Integer, default=0)
    mutants_lvl3 = Column(Integer, default=0)
    bosses_killed = Column(Integer, default=0)
    deaths = Column(Integer, default=0)
    crit_collects = Column(Integer, default=0)
    daily_streak = Column(Integer, default=0)
    last_collect_date = Column(DateTime, nullable=True)
    achievements = Column(String, default='[]')
    
    # Питомцы
    pet = Column(String, nullable=True)
    
    # Кланы
    clan_id = Column(Integer, ForeignKey('clans.id'), nullable=True)
    clan_role = Column(String, default='member')
    total_purchases = Column(Integer, default=0)
    last_seen = Column(DateTime, default=datetime.now)
    notifications_enabled = Column(Boolean, default=False)
    
    # Сундуки
    chest_common = Column(Integer, default=0)
    chest_rare = Column(Integer, default=0)
    chest_epic = Column(Integer, default=0)
    chest_mythic = Column(Integer, default=0)
    chest_legendary = Column(Integer, default=0)
    
    # Локации
    location = Column(String, default='normal')
    
    # Классы
    user_class = Column(String, default='stalker')
    last_free_class_change = Column(DateTime, nullable=True)
    
    # Радио
    radio_active = Column(Boolean, default=False)
    radio_code = Column(String, nullable=True)
    radio_banned = Column(Boolean, default=False)
    
    # Админ
    is_admin = Column(Boolean, default=False)
    is_blocked = Column(Boolean, default=False)
    is_admin_visible = Column(Boolean, default=True)
    
    # Фабрики
    factories = Column(String, default='[]')
    factory_bans = Column(String, default='[]')
    
    # Инвентарь и экипировка
    inventory = Column(String, default='[]')
    equipped = Column(String, default='{}')
    
    # Казино
    casino_chance = Column(Integer, nullable=True)
    casino_cash_mult = Column(Integer, nullable=True)
    
    # Эффекты (для /use)
    energy_drink_stacks = Column(Integer, default=0)
    reducer_stacks = Column(Integer, default=0)
    
    # Лимиты магазина
    shop_purchases = Column(String, default='{}')
    last_shop_reset = Column(DateTime, nullable=True)
    
    # ==================== НОВЫЕ ПОЛЯ ДЛЯ ALPHA 4.0 ====================
    # Уровень активного энергетика (strike, tornado, adrenaline, redbull)
    energy_drink_level = Column(String, default='strike')
    
    # Уровень активного редуктора (basic, advanced, quantum)
    reducer_level = Column(String, default='basic')
    
    # Металлоискатель
    last_metal_detector = Column(DateTime, nullable=True)
    last_metal_detector_duration = Column(Integer, default=3)  # часы кулдауна
    
    # Рюкзак (хранится в equipped, но добавим поле для быстрого доступа?)
    # На самом деле рюкзак будет в equipped['backpack'], отдельное поле не нужно


# ==================== МОДЕЛЬ КЛАНА ====================

class Clan(Base):
    __tablename__ = 'clans'
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True)
    leader_id = Column(Integer)
    created_at = Column(DateTime, default=datetime.now)
    treasury_coins = Column(Float, default=0)
    treasury_crystals = Column(Integer, default=0)
    collect_bonus = Column(Integer, default=0)
    exp_bonus = Column(Integer, default=0)
    double_bonus = Column(Integer, default=0)
    # НОВОЕ ПОЛЕ ДЛЯ ALPHA 4.0
    max_members = Column(Integer, default=50)  # лимит участников клана


# ==================== МОДЕЛЬ ЛОГОВ ====================

class UserLog(Base):
    __tablename__ = 'user_logs'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.user_id'))
    username = Column(String)
    action = Column(String)
    amount_rc = Column(Float, default=0)
    amount_rf = Column(Integer, default=0)
    amount_crystals = Column(Integer, default=0)
    item = Column(String, nullable=True)
    timestamp = Column(DateTime, default=datetime.now)


# ==================== МОДЕЛЬ РАДИО-ГРУПП ====================

class RadioGroup(Base):
    __tablename__ = 'radio_groups'
    id = Column(Integer, primary_key=True)
    chat_id = Column(Integer, unique=True)
    chat_title = Column(String, nullable=True)
    added_at = Column(DateTime, default=datetime.now)


# ==================== МИГРАЦИИ ====================

def migrate_db():
    """Автоматическое добавление новых колонок для ALPHA 4.0"""
    from sqlalchemy import inspect, text
    
    inspector = inspect(engine)
    
    # Проверяем существование таблицы users
    if not inspector.has_table('users'):
        print("⚠️ Таблица users не найдена, будет создана позже")
        return
    
    # Колонки для users (новые для ALPHA 4.0)
    columns_to_add_users = {
        'energy_drink_stacks': 'INTEGER DEFAULT 0',
        'reducer_stacks': 'INTEGER DEFAULT 0',
        'shop_purchases': 'TEXT DEFAULT \'{}\'',
        'last_shop_reset': 'DATETIME',
        'last_lab': 'DATETIME',
        'energy_drink_level': 'TEXT DEFAULT \'strike\'',
        'reducer_level': 'TEXT DEFAULT \'basic\'',
        'last_metal_detector': 'DATETIME',
        'last_metal_detector_duration': 'INTEGER DEFAULT 3',
    }
    
    existing_columns_users = [col['name'] for col in inspector.get_columns('users')]
    with engine.connect() as conn:
        for col_name, col_type in columns_to_add_users.items():
            if col_name not in existing_columns_users:
                try:
                    conn.execute(text(f"ALTER TABLE users ADD COLUMN {col_name} {col_type}"))
                    conn.commit()
                    print(f"✅ Добавлена колонка в users: {col_name}")
                except Exception as e:
                    print(f"⚠️ Ошибка при добавлении {col_name}: {e}")
    
    # Колонки для clans
    if inspector.has_table('clans'):
        columns_to_add_clans = {
            'max_members': 'INTEGER DEFAULT 50',
        }
        
        existing_columns_clans = [col['name'] for col in inspector.get_columns('clans')]
        with engine.connect() as conn:
            for col_name, col_type in columns_to_add_clans.items():
                if col_name not in existing_columns_clans:
                    try:
                        conn.execute(text(f"ALTER TABLE clans ADD COLUMN {col_name} {col_type}"))
                        conn.commit()
                        print(f"✅ Добавлена колонка в clans: {col_name}")
                    except Exception as e:
                        print(f"⚠️ Ошибка при добавлении {col_name}: {e}")
    
    # Создаём таблицу логов, если её нет
    if not inspector.has_table('user_logs'):
        Base.metadata.create_all(engine, tables=[UserLog.__table__])
        print("✅ Создана таблица user_logs")
    
    # Создаём таблицу радио-групп, если её нет
    if not inspector.has_table('radio_groups'):
        Base.metadata.create_all(engine, tables=[RadioGroup.__table__])
        print("✅ Создана таблица radio_groups")
    
    # Устанавливаем значения по умолчанию для существующих записей
    with engine.connect() as conn:
        # Устанавливаем уровень энергетика по умолчанию
        conn.execute(text("UPDATE users SET energy_drink_level = 'strike' WHERE energy_drink_level IS NULL"))
        # Устанавливаем уровень редуктора по умолчанию
        conn.execute(text("UPDATE users SET reducer_level = 'basic' WHERE reducer_level IS NULL"))
        # Устанавливаем длительность кулдауна металлоискателя
        conn.execute(text("UPDATE users SET last_metal_detector_duration = 3 WHERE last_metal_detector_duration IS NULL"))
        conn.commit()
        print("✅ Установлены значения по умолчанию для новых колонок")


# ==================== ИНИЦИАЛИЗАЦИЯ ====================

def init_db():
    """Создание таблиц и миграция"""
    Base.metadata.create_all(engine)
    migrate_db()
    print("✅ База данных инициализирована")


def init_super_admin():
    """Добавление главных администраторов"""
    session = Session()
    try:
        for admin_id in SUPER_ADMIN_IDS:
            user = session.query(User).filter_by(user_id=admin_id).first()
            if not user:
                user = User(user_id=admin_id, username=f"admin_{admin_id}")
                session.add(user)
            user.is_admin = True
            user.is_blocked = False
            session.commit()
            print(f"✅ Главный администратор {admin_id} добавлен")
    except Exception as e:
        print(f"⚠️ Ошибка: {e}")
    finally:
        Session.remove()


def get_user(user_id, username=None):
    """Получить или создать пользователя"""
    session = Session()
    try:
        user = session.query(User).filter_by(user_id=user_id).first()
        if not user:
            user = User(user_id=user_id, username=username)
            session.add(user)
            session.commit()
        elif username and user.username != username:
            user.username = username
            session.commit()
        user.last_seen = datetime.now()
        session.commit()
        return user
    except Exception as e:
        print(f"Database error: {e}")
        session.rollback()
        return None
    finally:
        Session.remove()


# Запускаем инициализацию
init_db()
init_super_admin()
