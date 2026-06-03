# utils.py - Утилиты и механики
# Версия: 4.0.0 (ALPHA)

import json
import random
from datetime import datetime, timedelta

from config import logger, MAX_MEDKITS, MAX_LEVEL
from database import Session, User, UserLog


# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

def escape_markdown(text: str) -> str:
    """Экранирует спецсимволы для Markdown"""
    if not text:
        return ""
    chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for ch in chars:
        text = text.replace(ch, f'\\{ch}')
    return text


def safe_log_user_action(user_id, username, action, amount_rc=0, amount_rf=0, amount_crystals=0, item=None):
    """Безопасное логирование — не ломает основную команду"""
    try:
        session = Session()
        log = UserLog(
            user_id=user_id, username=username, action=action,
            amount_rc=amount_rc, amount_rf=amount_rf,
            amount_crystals=amount_crystals, item=item,
            timestamp=datetime.now()
        )
        session.add(log)
        session.commit()
        session.close()
    except Exception as e:
        logger.error(f"⚠️ Ошибка логирования: {e}")


log_user_action = safe_log_user_action


# ==================== ИНВЕНТАРЬ ====================

def get_inventory(user):
    return json.loads(user.inventory) if user.inventory else []


def save_inventory(user, inventory):
    user.inventory = json.dumps(inventory)


def get_equipped(user):
    return json.loads(user.equipped) if user.equipped else {}


def save_equipped(user, equipped):
    user.equipped = json.dumps(equipped)


def add_item_to_inventory(user, item_name, count=1, expires=None):
    inventory = get_inventory(user)
    for i in inventory:
        if i['item'] == item_name:
            i['count'] += count
            if expires and 'expires' not in i:
                i['expires'] = expires.isoformat() if expires else None
            save_inventory(user, inventory)
            return
    new_item = {'item': item_name, 'count': count}
    if expires:
        new_item['expires'] = expires.isoformat()
    inventory.append(new_item)
    save_inventory(user, inventory)


def remove_item_from_inventory(user, item_name, count=1):
    inventory = get_inventory(user)
    for i in inventory:
        if i['item'] == item_name:
            i['count'] -= count
            if i['count'] <= 0:
                inventory.remove(i)
            save_inventory(user, inventory)
            return True
    return False


def get_item_count(user, item_name):
    inventory = get_inventory(user)
    for i in inventory:
        if i['item'] == item_name:
            return i['count']
    return 0


# ==================== РЮКЗАКИ И АПТЕЧКИ В НИХ (НОВОЕ ДЛЯ ALPHA 4.0) ====================

def get_backpack(user):
    """Получить тип экипированного рюкзака"""
    equipped = get_equipped(user)
    return equipped.get('backpack')


def get_medkits_in_backpack(user):
    """Получить количество аптечек в экипированном рюкзаке"""
    # Аптечки в рюкзаке хранятся в отдельном поле в equipped
    equipped = get_equipped(user)
    return equipped.get('medkits_in_backpack', 0)


def add_medkits_to_backpack(user, count):
    """Добавить аптечки в рюкзак"""
    equipped = get_equipped(user)
    current = equipped.get('medkits_in_backpack', 0)
    equipped['medkits_in_backpack'] = current + count
    save_equipped(user, equipped)


def remove_medkits_from_backpack(user, count):
    """Удалить аптечки из рюкзака"""
    equipped = get_equipped(user)
    current = equipped.get('medkits_in_backpack', 0)
    new_count = max(0, current - count)
    equipped['medkits_in_backpack'] = new_count
    save_equipped(user, equipped)


def get_backpack_max_medkits(backpack_type):
    """Получить максимальное количество аптечек в рюкзаке по его типу"""
    from config import BACKPACKS
    backpack_data = BACKPACKS.get(backpack_type, {})
    return backpack_data.get('medkit_slots', 0)


# ==================== БОНУСЫ КЛАССОВ ====================

def apply_class_bonus(user, rc_gain, fragment_gain, exp_gain):
    class_name = getattr(user, 'user_class', 'stalker')
    if class_name == 'military':
        return int(rc_gain * 1.2), int(fragment_gain * 0.7), int(exp_gain * 1.3)
    elif class_name == 'bandit':
        return int(rc_gain * 1.15), int(fragment_gain * 1.4), int(exp_gain * 0.75)
    elif class_name == 'scientist':
        return int(rc_gain * 0.8), int(fragment_gain * 1.25), int(exp_gain * 1.5)
    return rc_gain, fragment_gain, exp_gain


# ==================== ВЫЖИВАЕМОСТЬ ====================

def calculate_survive_chance(user, target_level):
    """Расчёт шанса выживания на охоте с учётом брони и оружия"""
    armor_bonus = {
        'броня1': 20,
        'броня2': 30,
        'броня3': 40,
        'броня4': 50,
        'броня5': 60
    }
    weapon_bonus = {
        'ружье': 10,
        'гарпун': 15,
        'винтовка': 20,
        'гаусс': 30
    }
    
    base = 10  # базовый шанс без брони и оружия
    equipped = get_equipped(user)
    
    armor = equipped.get('armor')
    if armor and armor in armor_bonus:
        base += armor_bonus[armor]
    
    weapon = equipped.get('weapon')
    if weapon and weapon in weapon_bonus:
        base += weapon_bonus[weapon]
    
    # Бонус за уровень цели
    if target_level == 3:
        base = min(100, base + 25)
    
    # Аптечка в инвентаре (не в рюкзаке) даёт +25%
    if get_item_count(user, 'аптечка') > 0:
        base = min(100, base + 25)
    
    # Питомец волк даёт +10% к выживанию
    if user.pet == 'волк':
        base = min(100, base + 10)
    
    return base


# ==================== ДОСТИЖЕНИЯ ====================

def check_achievements(user):
    """Проверяет достижения и возвращает список новых. НИЧЕГО НЕ СОХРАНЯЕТ."""
    achievements = json.loads(user.achievements) if user.achievements else []
    new_achievements = []

    if user.total_collects >= 10 and 'добытчик' not in achievements:
        new_achievements.append('добытчик')
    if user.level >= 10 and 'кандидат' not in achievements:
        new_achievements.append('кандидат')
    if user.level >= 50 and 'мастер' not in achievements:
        new_achievements.append('мастер')
    if user.level >= MAX_LEVEL and 'легенда' not in achievements:
        new_achievements.append('легенда')
    if user.daily_streak >= 7 and 'терпила' not in achievements:
        new_achievements.append('терпила')
    if user.daily_streak >= 30 and 'старатель' not in achievements:
        new_achievements.append('старатель')
    if user.total_purchases >= 10 and 'постоянный_клиент' not in achievements:
        new_achievements.append('постоянный_клиент')
    if user.radcoins >= 100000 and 'миллионер' not in achievements:
        new_achievements.append('миллионер')

    return new_achievements


# ==================== ОПЫТ ДЛЯ УРОВНЯ ====================

def get_exp_for_level(level):
    if level <= 1:
        return 0
    level = min(level, MAX_LEVEL)
    return sum(100 + (i - 2) * 50 for i in range(2, level + 1))


def get_user_by_username(session, username):
    """Найти пользователя по username (без учёта регистра)"""
    from sqlalchemy import func
    return session.query(User).filter(func.lower(User.username) == username.lower()).first()
