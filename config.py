# config.py - Централизованные настройки и константы
# Версия: 4.0.0 (ALPHA)

import logging
import os
from datetime import datetime, timedelta

# ==================== НАСТРОЙКИ БОТА ====================
TOKEN = ''
ADMIN_CODE = '1252836169043217'
SUPER_ADMIN_IDS = [6595788533]

# ==================== ИГРОВЫЕ КОНСТАНТЫ ====================
MAX_LEVEL = 1000
MAX_CLAN_BONUS = 25
MAX_MEDKITS = 10

# ==================== НОВАЯ ЛИНЕЙКА ЭНЕРГЕТИКОВ ====================
ENERGY_DRINKS = {
    'strike': {
        'name': '⚡ Strike',
        'price': 100,
        'level_required': 1,
        'rc_bonus': 1.03,      # +3% RC
        'rf_bonus': 1.05,      # +5% RF
        'crystal_bonus': 1.10,  # +10% кристаллы
        'survive_bonus': 0,     # 0% выживание
        'duration_hours': 6
    },
    'tornado': {
        'name': '🌀 Tornado',
        'price': 500,
        'level_required': 5,
        'rc_bonus': 1.07,      # +7% RC
        'rf_bonus': 1.12,      # +12% RF
        'crystal_bonus': 1.15,  # +15% кристаллы
        'survive_bonus': 5,     # +5% выживание
        'duration_hours': 6
    },
    'adrenaline': {
        'name': '💉 Adrenaline',
        'price': 2500,
        'level_required': 10,
        'rc_bonus': 1.15,      # +15% RC
        'rf_bonus': 1.25,      # +25% RF
        'crystal_bonus': 1.35,  # +35% кристаллы
        'survive_bonus': 10,    # +10% выживание
        'duration_hours': 6
    },
    'redbull': {
        'name': '🔴 RedBull',
        'price': 5000,
        'level_required': 25,
        'rc_bonus': 1.40,      # +40% RC
        'rf_bonus': 1.50,      # +50% RF
        'crystal_bonus': 1.80,  # +80% кристаллы
        'survive_bonus': 25,    # +25% выживание
        'duration_hours': 6
    }
}

# ==================== НОВАЯ ЛИНЕЙКА РЕДУКТОРОВ ====================
REDUCERS = {
    'basic': {
        'name': '⏱️ Базовый редуктор',
        'price': 1000,
        'level_required': 1,
        'cooldown_reduction': 0.70,  # ускорение 30%
        'duration_days': 3
    },
    'advanced': {
        'name': '⚙️ Продвинутый редуктор',
        'price': 3500,
        'level_required': 10,
        'cooldown_reduction': 0.55,  # ускорение 45%
        'duration_days': 3
    },
    'quantum': {
        'name': '🌀 Квантовый редуктор',
        'price': 7500,
        'level_required': 25,
        'cooldown_reduction': 0.50,  # ускорение 50%
        'duration_days': 3
    }
}

# ==================== НОВЫЕ РЮКЗАКИ (ALPHA 4.0) ====================
BACKPACKS = {
    'backpack1': {
        'name': '🎒 Маленький рюкзак',
        'price': 5000,
        'level_required': 10,
        'rc_bonus': 20,      # +20% RC
        'rf_bonus': 10,      # +10% RF
        'medkit_slots': 1    # вмещает 1 аптечку
    },
    'backpack2': {
        'name': '🎒 Тактический рюкзак',
        'price': 15000,
        'level_required': 25,
        'rc_bonus': 30,      # +30% RC
        'rf_bonus': 15,      # +15% RF
        'medkit_slots': 2    # вмещает 2 аптечки
    },
    'backpack3': {
        'name': '🎒 Профессиональный рюкзак',
        'price': 40000,
        'level_required': 50,
        'rc_bonus': 45,      # +45% RC
        'rf_bonus': 18,      # +18% RF
        'medkit_slots': 3    # вмещает 3 аптечки
    }
}

# ==================== МЕТАЛЛОИСКАТЕЛЬ (ALPHA 4.0) ====================
METAL_DETECTOR = {
    'name': '🔍 Металлоискатель',
    'price': 10000,
    'level_required': 5,
    'cooldown_min': 3,      # минимальный кулдаун в часах
    'cooldown_max': 18,     # максимальный кулдаун
    'chest_chance': 10,     # 10% шанс найти сундук
    'chest_types': ['common', 'rare', 'epic', 'mythic', 'legendary']  # равные шансы 20% каждый
}

# ==================== СТАРЫЕ ЛИМИТЫ ТОВАРОВ (для магазина) ====================
# Лимиты только для старых товаров. Новые товары (энергетики, редукторы, рюкзаки, металлоискатель) без лимитов!
SHOP_LIMITS = {
    'броня3': 10,      # Тактическая броня
    'броня4': 7,       # Тяжёлая броня
    'броня5': 5,       # Силовая броня
    'винтовка': 7,     # Винтовка
    'гаусс': 5,        # Винтовка Гаусса
    'аптечка': 75,     # Аптечка
}
SHOP_RESET_HOURS = 6

# ==================== НАСТРОЙКИ КАЗИНО ====================
CASINO_PUBLIC_CHANCE = 12
CASINO_PUBLIC_CASH_MULT = 5
CASINO_MIN_BET = 100
CASINO_MAX_BET = 1000000

# ==================== БЭКАПЫ ====================
BACKUP_DIR = '/app/shared/backups'
BACKUP_RETENTION_DAYS = 3
BACKUP_INTERVAL_MINUTES = 15

# Создаём папку для бэкапов, если её нет
if not os.path.exists(BACKUP_DIR):
    os.makedirs(BACKUP_DIR, exist_ok=True)

# ==================== ФАБРИКИ (ТОЧКИ) ====================
FACTORIES = {
    'свалка': {
        'name': '🗑️ Свалка',
        'slots': 50,
        'price': 1500,
        'income': 1,
        'income_type': 'RF',
        'level': 1,
        'duration': 72,
    },
    'мастерская': {
        'name': '🔧 Мастерская',
        'slots': 30,
        'price': 5000,
        'income': 5,
        'income_type': 'RF',
        'level': 5,
        'duration': 72,
    },
    'станция': {
        'name': '⚡ Станция',
        'slots': 25,
        'price': 10000,
        'income': 12,
        'income_type': 'RF',
        'level': 7,
        'duration': 72,
    },
    'дамба': {
        'name': '🌊 Дамба',
        'slots': 10,
        'price': 15000,
        'income': 25,
        'income_type': 'RF',
        'level': 10,
        'duration': 72,
    },
    'химка': {
        'name': '🧪 Химка',
        'slots': 7,
        'price': 25000,
        'income': 40,
        'income_type': 'RF',
        'level': 15,
        'duration': 72,
    },
    'комплекс': {
        'name': '🏭 Комплекс',
        'slots': 5,
        'price': 100000,
        'income': 100,
        'income_type': 'RF',
        'level': 25,
        'duration': 72,
    },
    'реактор': {
        'name': '☢️ Реактор',
        'slots': 3,
        'price': 500000,
        'income': 1000,
        'income_type': 'RF',
        'level': 50,
        'duration': 72,
    },
}

# ==================== ЛОГГЕР ====================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)
logger = logging.getLogger(__name__)


# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

def get_exp_for_level(level):
    """Опыт для повышения уровня"""
    if level <= 1:
        return 0
    if level > MAX_LEVEL:
        level = MAX_LEVEL
    total = 0
    for i in range(2, level + 1):
        total += 100 + (i - 2) * 50
    return total


def calculate_reward(level):
    """Базовая награда RC"""
    import random
    level = min(level, MAX_LEVEL)
    base = random.randint(51, 150)
    bonus = 1 + (level - 1) * 0.05
    if bonus > 1 + (MAX_LEVEL - 1) * 0.05:
        bonus = 1 + (MAX_LEVEL - 1) * 0.05
    return int(base * bonus)


def calculate_experience():
    """Базовая награда опыта"""
    import random
    return random.randint(10, 50)


def get_random_interval(user=None):
    """Интервал между сборами с учётом редуктора и кайота"""
    import random
    from datetime import datetime
    
    base = random.randint(30, 120)
    if user and hasattr(user, 'cooldown_reducer_until') and user.cooldown_reducer_until and user.cooldown_reducer_until > datetime.now():
        base = base // 2
    if user and hasattr(user, 'pet') and user.pet == 'кайот':
        base = base // 2
    return max(base, 5)


def get_energy_bonus(energy_level):
    """Получить бонусы энергетика по его уровню"""
    return ENERGY_DRINKS.get(energy_level, ENERGY_DRINKS['strike'])


def get_reducer_bonus(reducer_level):
    """Получить параметры редуктора по его уровню"""
    return REDUCERS.get(reducer_level, REDUCERS['basic'])


def get_backpack_bonus(backpack_type):
    """Получить бонусы рюкзака по его типу"""
    return BACKPACKS.get(backpack_type, None)
