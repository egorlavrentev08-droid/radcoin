# chest.py - Сундуки
# Версия: 4.0.0 (ALPHA)

import random
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import ContextTypes
from config import logger, BACKPACKS
from core import send_to_private
from database import Session, User
from utils import add_item_to_inventory, log_user_action


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
        from database import UserLog
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


# ==================== СУНДУКИ ====================

async def chest_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Главная команда сундуков"""
    if not context.args:
        await update.message.reply_text(
            "🎁 *Сундуки Пустоши*\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "/chest list — список сундуков\n"
            "/chest chance — шансы выпадения\n"
            "/chest open common — открыть обычный\n"
            "/chest open rare — открыть редкий\n"
            "/chest open epic — открыть эпический\n"
            "/chest open mythic — открыть мифический\n"
            "/chest open legendary — открыть легендарный\n"
            "/chest open all — открыть все сундуки сразу",
            parse_mode='Markdown'
        )
        return
    
    action = context.args[0].lower()
    
    if action == 'list':
        await chest_list(update, context)
    elif action == 'chance':
        await chest_chance(update, context)
    elif action == 'open':
        if len(context.args) > 1:
            if context.args[1].lower() == 'all':
                await chest_open_all(update, context)
            else:
                await chest_open(update, context, context.args[1].lower())
        else:
            await update.message.reply_text("❌ /chest open [common/rare/epic/mythic/legendary/all]")
    else:
        await update.message.reply_text("❌ Используйте: list, chance, open")


async def chest_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Список сундуков пользователя"""
    session = Session()
    try:
        user = session.query(User).filter_by(user_id=update.effective_user.id).first()
        if not user:
            await update.message.reply_text("❌ /start")
            return
        text = (
            f"🎁 *Ваши сундуки*\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🟢 *Обычные:* {user.chest_common}\n"
            f"🔵 *Редкие:* {user.chest_rare}\n"
            f"🟣 *Эпические:* {user.chest_epic}\n"
            f"🟡 *Мифические:* {user.chest_mythic}\n"
            f"🟠 *Легендарные:* {user.chest_legendary}\n\n"
            "💡 /chest open [тип] — открыть"
        )
        await update.message.reply_text(text, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error in chest_list: {e}")
        await update.message.reply_text("❌ Ошибка")
    finally:
        session.close()


async def chest_chance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Шансы выпадения из сундуков"""
    text = (
        "🎲 *Шансы выпадения в сундуках*\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "*🟢 ОБЫЧНЫЙ* (2 предмета)\n"
        "☢️ RC 100-500\n☣️ RF 2-10\n💊 Аптечка\n\n"
        "*🔵 РЕДКИЙ* (3 предмета)\n"
        "☢️ RC 500-1500\n☣️ RF 10-50\n🎣 Гарпун\n🥉 Лёгкая броня\n💊 Аптечка\n⚡ Энергетик (Strike)\n\n"
        "*🟣 ЭПИЧЕСКИЙ* (4 предмета)\n"
        "☢️ RC 1000-3000\n☣️ RF 50-200\n🥈 Утяжеленная броня\n🎣 Гарпун\n💊 Аптечка\n⚡ Энергетик (Tornado)\n⏱️ Редуктор (Базовый)\n🟢 Обычный сундук\n\n"
        "*🟡 МИФИЧЕСКИЙ* (4 предмета)\n"
        "☢️ RC 2500-6000\n☣️ RF 150-500\n🥉 Тактическая броня\n🔫 Винтовка\n🎣 Гарпун\n💊 Аптечка\n⏱️ Редуктор (Продвинутый)\n⚡ Энергетик (Adrenaline)\n🐾 Питомец (0.5%)\n🟣 Эпический сундук\n🎒 Рюкзак (маленький)\n\n"
        "*🟠 ЛЕГЕНДАРНЫЙ* (5 предметов)\n"
        "☢️ RC 5000-15000\n☣️ RF 500-1500\n🥇 Силовая броня\n⚡ Винтовка Гаусса\n💊 Аптечка\n⏱️ Редуктор (Квантовый)\n⚡ Энергетик (RedBull)\n🐾 Питомец (2%)\n🎣 Гарпун\n🟡 Мифический сундук\n🎒 Рюкзак (тактический/профессиональный)\n🔍 Металлоискатель"
    )
    await update.message.reply_text(text, parse_mode='Markdown')


async def chest_open(update: Update, context: ContextTypes.DEFAULT_TYPE, chest_type: str):
    """Открыть сундук определённого типа"""
    session = Session()
    try:
        user = session.query(User).filter_by(user_id=update.effective_user.id).first()
        if not user:
            await update.message.reply_text("❌ /start")
            return
        
        rc_gain = 0
        rf_gain = 0
        log_user_id = user.user_id
        log_username = user.username
        
        # Словарь для подсчёта полученных предметов
        items_gained = {}
        
        def add_item(item_name, count=1):
            if item_name in items_gained:
                items_gained[item_name] += count
            else:
                items_gained[item_name] = count
        
        # ==================== ОБЫЧНЫЙ СУНДУК ====================
        if chest_type == 'common':
            if user.chest_common <= 0:
                await update.message.reply_text("❌ Нет обычных сундуков")
                return
            user.chest_common -= 1
            items = ['rc', 'rf', 'medkit']
            random.shuffle(items)
            selected = items[:2]
            for r in selected:
                if r == 'rc':
                    amt = random.randint(100, 500)
                    rc_gain += amt
                    user.radcoins += amt
                elif r == 'rf':
                    amt = random.randint(2, 10)
                    rf_gain += amt
                    user.radfragments += amt
                elif r == 'medkit':
                    add_item('💊 Аптечка')
                    add_item_to_inventory(user, 'аптечка', 1)
            name = "🟢 Обычный сундук"
        
        # ==================== РЕДКИЙ СУНДУК ====================
        elif chest_type == 'rare':
            if user.chest_rare <= 0:
                await update.message.reply_text("❌ Нет редких сундуков")
                return
            user.chest_rare -= 1
            items = ['rc', 'rf', 'harpoon', 'armor1', 'medkit', 'energy_strike']
            random.shuffle(items)
            selected = items[:3]
            for r in selected:
                if r == 'rc':
                    amt = random.randint(500, 1500)
                    rc_gain += amt
                    user.radcoins += amt
                elif r == 'rf':
                    amt = random.randint(10, 50)
                    rf_gain += amt
                    user.radfragments += amt
                elif r == 'harpoon':
                    add_item('🎣 Гарпун')
                    add_item_to_inventory(user, 'гарпун', 1)
                elif r == 'armor1':
                    add_item('🥉 Лёгкая броня')
                    add_item_to_inventory(user, 'броня1', 1)
                elif r == 'medkit':
                    amt = random.randint(1, 3)
                    add_item(f'💊 Аптечка x{amt}')
                    add_item_to_inventory(user, 'аптечка', amt)
                elif r == 'energy_strike':
                    add_item('⚡ Энергетик Strike')
                    add_item_to_inventory(user, 'энергетик_strike', 1)
            name = "🔵 Редкий сундук"
        
        # ==================== ЭПИЧЕСКИЙ СУНДУК ====================
        elif chest_type == 'epic':
            if user.chest_epic <= 0:
                await update.message.reply_text("❌ Нет эпических сундуков")
                return
            user.chest_epic -= 1
            items = ['rc', 'rf', 'armor2', 'harpoon', 'medkit', 'energy_tornado', 'reducer_basic', 'chest_common']
            random.shuffle(items)
            selected = items[:4]
            for r in selected:
                if r == 'rc':
                    amt = random.randint(1000, 3000)
                    rc_gain += amt
                    user.radcoins += amt
                elif r == 'rf':
                    amt = random.randint(50, 200)
                    rf_gain += amt
                    user.radfragments += amt
                elif r == 'armor2':
                    add_item('🥈 Утяжеленная броня')
                    add_item_to_inventory(user, 'броня2', 1)
                elif r == 'harpoon':
                    add_item('🎣 Гарпун')
                    add_item_to_inventory(user, 'гарпун', 1)
                elif r == 'medkit':
                    amt = random.randint(1, 3)
                    add_item(f'💊 Аптечка x{amt}')
                    add_item_to_inventory(user, 'аптечка', amt)
                elif r == 'energy_tornado':
                    add_item('🌀 Энергетик Tornado')
                    add_item_to_inventory(user, 'энергетик_tornado', 1)
                elif r == 'reducer_basic':
                    add_item('⏱️ Базовый редуктор')
                    add_item_to_inventory(user, 'редуктор_basic', 1)
                elif r == 'chest_common':
                    add_item('🟢 Обычный сундук')
                    user.chest_common += 1
            name = "🟣 Эпический сундук"
        
        # ==================== МИФИЧЕСКИЙ СУНДУК ====================
        elif chest_type == 'mythic':
            if user.chest_mythic <= 0:
                await update.message.reply_text("❌ Нет мифических сундуков")
                return
            user.chest_mythic -= 1
            items = ['rc', 'rf', 'armor3', 'rifle', 'harpoon', 'medkit', 'reducer_advanced', 'energy_adrenaline', 'pet', 'chest_epic', 'backpack1']
            random.shuffle(items)
            selected = items[:4]
            pet_added = False
            for r in selected:
                if r == 'rc':
                    amt = random.randint(2500, 6000)
                    rc_gain += amt
                    user.radcoins += amt
                elif r == 'rf':
                    amt = random.randint(150, 500)
                    rf_gain += amt
                    user.radfragments += amt
                elif r == 'armor3':
                    add_item('🥉 Тактическая броня')
                    add_item_to_inventory(user, 'броня3', 1)
                elif r == 'rifle':
                    add_item('🔫 Винтовка')
                    add_item_to_inventory(user, 'винтовка', 1)
                elif r == 'harpoon':
                    add_item('🎣 Гарпун')
                    add_item_to_inventory(user, 'гарпун', 1)
                elif r == 'medkit':
                    amt = random.randint(2, 5)
                    add_item(f'💊 Аптечка x{amt}')
                    add_item_to_inventory(user, 'аптечка', amt)
                elif r == 'reducer_advanced':
                    add_item('⚙️ Продвинутый редуктор')
                    add_item_to_inventory(user, 'редуктор_advanced', 1)
                elif r == 'energy_adrenaline':
                    add_item('💉 Энергетик Adrenaline')
                    add_item_to_inventory(user, 'энергетик_adrenaline', 1)
                elif r == 'pet':
                    if not pet_added and random.random() < 0.005:
                        pets = ['овчарка', 'волк', 'рысь', 'пума', 'попугай', 'кайот']
                        pet = random.choice(pets)
                        user.pet = pet
                        pet_names = {
                            'овчарка': '🐕 Овчарка', 'волк': '🐺 Волк',
                            'рысь': '🐈 Рысь', 'пума': '🐆 Пума',
                            'попугай': '🦜 Попугай', 'кайот': '🐕 Кайот'
                        }
                        add_item(f'🐾 {pet_names.get(pet, pet)}')
                        pet_added = True
                elif r == 'chest_epic':
                    add_item('🟣 Эпический сундук')
                    user.chest_epic += 1
                elif r == 'backpack1':
                    add_item('🎒 Маленький рюкзак')
                    add_item_to_inventory(user, 'backpack1', 1)
            name = "🟡 Мифический сундук"
        
        # ==================== ЛЕГЕНДАРНЫЙ СУНДУК ====================
        elif chest_type == 'legendary':
            if user.chest_legendary <= 0:
                await update.message.reply_text("❌ Нет легендарных сундуков")
                return
            user.chest_legendary -= 1
            items = ['rc', 'rf', 'armor5', 'gauss', 'medkit', 'reducer_quantum', 'energy_redbull', 'pet', 'harpoon', 'chest_mythic', 'backpack2', 'backpack3', 'metal_detector']
            random.shuffle(items)
            selected = items[:5]
            pet_added = False
            for r in selected:
                if r == 'rc':
                    amt = random.randint(5000, 15000)
                    rc_gain += amt
                    user.radcoins += amt
                elif r == 'rf':
                    amt = random.randint(500, 1500)
                    rf_gain += amt
                    user.radfragments += amt
                elif r == 'armor5':
                    add_item('🥇 Силовая броня')
                    add_item_to_inventory(user, 'броня5', 1)
                elif r == 'gauss':
                    add_item('⚡ Винтовка Гаусса')
                    add_item_to_inventory(user, 'гаусс', 1)
                elif r == 'medkit':
                    amt = random.randint(2, 5)
                    add_item(f'💊 Аптечка x{amt}')
                    add_item_to_inventory(user, 'аптечка', amt)
                elif r == 'reducer_quantum':
                    add_item('🌀 Квантовый редуктор')
                    add_item_to_inventory(user, 'редуктор_quantum', 1)
                elif r == 'energy_redbull':
                    add_item('🔴 Энергетик RedBull')
                    add_item_to_inventory(user, 'энергетик_redbull', 1)
                elif r == 'pet':
                    if not pet_added and random.random() < 0.02:
                        pets = ['овчарка', 'волк', 'рысь', 'пума', 'попугай', 'кайот']
                        pet = random.choice(pets)
                        user.pet = pet
                        pet_names = {
                            'овчарка': '🐕 Овчарка', 'волк': '🐺 Волк',
                            'рысь': '🐈 Рысь', 'пума': '🐆 Пума',
                            'попугай': '🦜 Попугай', 'кайот': '🐕 Кайот'
                        }
                        add_item(f'🐾 {pet_names.get(pet, pet)}')
                        pet_added = True
                elif r == 'harpoon':
                    add_item('🎣 Гарпун')
                    add_item_to_inventory(user, 'гарпун', 1)
                elif r == 'chest_mythic':
                    add_item('🟡 Мифический сундук')
                    user.chest_mythic += 1
                elif r == 'backpack2':
                    add_item('🎒 Тактический рюкзак')
                    add_item_to_inventory(user, 'backpack2', 1)
                elif r == 'backpack3':
                    add_item('🎒 Профессиональный рюкзак')
                    add_item_to_inventory(user, 'backpack3', 1)
                elif r == 'metal_detector':
                    add_item('🔍 Металлоискатель')
                    add_item_to_inventory(user, 'metal_detector', 1)
            name = "🟠 Легендарный сундук"
        else:
            await update.message.reply_text("❌ Тип: common, rare, epic, mythic, legendary")
            return
        
        session.commit()
        
        if rc_gain > 0 or rf_gain > 0:
            safe_log_user_action(
                log_user_id, log_username, 'chest_open',
                amount_rc=rc_gain, amount_rf=rf_gain, item=chest_type
            )
        
        # Формируем сообщение
        text = f"🎁 *{name} открыт!*\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        if rc_gain > 0:
            text += f"💰 ☢️ +{rc_gain} RC\n"
        if rf_gain > 0:
            text += f"💰 ☣️ +{rf_gain} RF\n"
        
        if items_gained:
            text += f"\n📦 *Находки:*\n"
            for item, count in items_gained.items():
                text += f"• {item} x{count}\n"
        
        await update.message.reply_text(text, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Error in chest_open: {e}")
        session.rollback()
        await update.message.reply_text("❌ Ошибка")
    finally:
        session.close()


async def chest_open_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Открыть все сундуки подряд, получая все предметы"""
    session = Session()
    try:
        user = session.query(User).filter_by(user_id=update.effective_user.id).first()
        if not user:
            await update.message.reply_text("❌ /start")
            return

        total_common = user.chest_common
        total_rare = user.chest_rare
        total_epic = user.chest_epic
        total_mythic = user.chest_mythic
        total_legendary = user.chest_legendary

        if total_common == 0 and total_rare == 0 and total_epic == 0 and total_mythic == 0 and total_legendary == 0:
            await update.message.reply_text("🎁 *У вас нет сундуков!*", parse_mode='Markdown')
            return

        await update.message.reply_text(
            f"🎁 *Начинаю открывать сундуки...*\n\n"
            f"🟢 Обычных: {total_common}\n"
            f"🔵 Редких: {total_rare}\n"
            f"🟣 Эпических: {total_epic}\n"
            f"🟡 Мифических: {total_mythic}\n"
            f"🟠 Легендарных: {total_legendary}\n\n"
            f"⏳ Подождите, идёт открытие...",
            parse_mode='Markdown'
        )

        total_rc = 0
        total_rf = 0
        items_gained = {}
        pet_gained = None
        log_user_id = user.user_id
        log_username = user.username

        def add_item(item_name, count=1):
            if item_name in items_gained:
                items_gained[item_name] += count
            else:
                items_gained[item_name] = count

        # ==================== 1. ОБЫЧНЫЕ СУНДУКИ ====================
        for _ in range(user.chest_common):
            items = ['rc', 'rf', 'medkit']
            random.shuffle(items)
            selected = items[:2]
            for r in selected:
                if r == 'rc':
                    amt = random.randint(100, 500)
                    total_rc += amt
                    user.radcoins += amt
                elif r == 'rf':
                    amt = random.randint(2, 10)
                    total_rf += amt
                    user.radfragments += amt
                elif r == 'medkit':
                    add_item('💊 Аптечка')
                    add_item_to_inventory(user, 'аптечка', 1)
            user.chest_common -= 1

        # ==================== 2. РЕДКИЕ СУНДУКИ ====================
        for _ in range(user.chest_rare):
            items = ['rc', 'rf', 'harpoon', 'armor1', 'medkit', 'energy_strike']
            random.shuffle(items)
            selected = items[:3]
            for r in selected:
                if r == 'rc':
                    amt = random.randint(500, 1500)
                    total_rc += amt
                    user.radcoins += amt
                elif r == 'rf':
                    amt = random.randint(10, 50)
                    total_rf += amt
                    user.radfragments += amt
                elif r == 'harpoon':
                    add_item('🎣 Гарпун')
                    add_item_to_inventory(user, 'гарпун', 1)
                elif r == 'armor1':
                    add_item('🥉 Лёгкая броня')
                    add_item_to_inventory(user, 'броня1', 1)
                elif r == 'medkit':
                    amt = random.randint(1, 3)
                    add_item(f'💊 Аптечка x{amt}')
                    add_item_to_inventory(user, 'аптечка', amt)
                elif r == 'energy_strike':
                    add_item('⚡ Энергетик Strike')
                    add_item_to_inventory(user, 'энергетик_strike', 1)
            user.chest_rare -= 1

        # ==================== 3. ЭПИЧЕСКИЕ СУНДУКИ ====================
        for _ in range(user.chest_epic):
            items = ['rc', 'rf', 'armor2', 'harpoon', 'medkit', 'energy_tornado', 'reducer_basic', 'chest_common']
            random.shuffle(items)
            selected = items[:4]
            for r in selected:
                if r == 'rc':
                    amt = random.randint(1000, 3000)
                    total_rc += amt
                    user.radcoins += amt
                elif r == 'rf':
                    amt = random.randint(50, 200)
                    total_rf += amt
                    user.radfragments += amt
                elif r == 'armor2':
                    add_item('🥈 Утяжеленная броня')
                    add_item_to_inventory(user, 'броня2', 1)
                elif r == 'harpoon':
                    add_item('🎣 Гарпун')
                    add_item_to_inventory(user, 'гарпун', 1)
                elif r == 'medkit':
                    amt = random.randint(1, 3)
                    add_item(f'💊 Аптечка x{amt}')
                    add_item_to_inventory(user, 'аптечка', amt)
                elif r == 'energy_tornado':
                    add_item('🌀 Энергетик Tornado')
                    add_item_to_inventory(user, 'энергетик_tornado', 1)
                elif r == 'reducer_basic':
                    add_item('⏱️ Базовый редуктор')
                    add_item_to_inventory(user, 'редуктор_basic', 1)
                elif r == 'chest_common':
                    add_item('🟢 Обычный сундук')
                    user.chest_common += 1
            user.chest_epic -= 1

        # ==================== 4. МИФИЧЕСКИЕ СУНДУКИ ====================
        for _ in range(user.chest_mythic):
            items = ['rc', 'rf', 'armor3', 'rifle', 'harpoon', 'medkit', 'reducer_advanced', 'energy_adrenaline', 'pet', 'chest_epic', 'backpack1']
            random.shuffle(items)
            selected = items[:4]
            pet_added_this = False
            for r in selected:
                if r == 'rc':
                    amt = random.randint(2500, 6000)
                    total_rc += amt
                    user.radcoins += amt
                elif r == 'rf':
                    amt = random.randint(150, 500)
                    total_rf += amt
                    user.radfragments += amt
                elif r == 'armor3':
                    add_item('🥉 Тактическая броня')
                    add_item_to_inventory(user, 'броня3', 1)
                elif r == 'rifle':
                    add_item('🔫 Винтовка')
                    add_item_to_inventory(user, 'винтовка', 1)
                elif r == 'harpoon':
                    add_item('🎣 Гарпун')
                    add_item_to_inventory(user, 'гарпун', 1)
                elif r == 'medkit':
                    amt = random.randint(2, 5)
                    add_item(f'💊 Аптечка x{amt}')
                    add_item_to_inventory(user, 'аптечка', amt)
                elif r == 'reducer_advanced':
                    add_item('⚙️ Продвинутый редуктор')
                    add_item_to_inventory(user, 'редуктор_advanced', 1)
                elif r == 'energy_adrenaline':
                    add_item('💉 Энергетик Adrenaline')
                    add_item_to_inventory(user, 'энергетик_adrenaline', 1)
                elif r == 'pet':
                    if not pet_added_this and not pet_gained and random.random() < 0.005:
                        pets = ['овчарка', 'волк', 'рысь', 'пума', 'попугай', 'кайот']
                        pet_gained = random.choice(pets)
                        user.pet = pet_gained
                        pet_names = {
                            'овчарка': '🐕 Овчарка', 'волк': '🐺 Волк',
                            'рысь': '🐈 Рысь', 'пума': '🐆 Пума',
                            'попугай': '🦜 Попугай', 'кайот': '🐕 Кайот'
                        }
                        add_item(f'🐾 {pet_names.get(pet_gained, pet_gained)}')
                        pet_added_this = True
                elif r == 'chest_epic':
                    add_item('🟣 Эпический сундук')
                    user.chest_epic += 1
                elif r == 'backpack1':
                    add_item('🎒 Маленький рюкзак')
                    add_item_to_inventory(user, 'backpack1', 1)
            user.chest_mythic -= 1

        # ==================== 5. ЛЕГЕНДАРНЫЕ СУНДУКИ ====================
        for _ in range(user.chest_legendary):
            items = ['rc', 'rf', 'armor5', 'gauss', 'medkit', 'reducer_quantum', 'energy_redbull', 'pet', 'harpoon', 'chest_mythic', 'backpack2', 'backpack3', 'metal_detector']
            random.shuffle(items)
            selected = items[:5]
            pet_added_this = False
            for r in selected:
                if r == 'rc':
                    amt = random.randint(5000, 15000)
                    total_rc += amt
                    user.radcoins += amt
                elif r == 'rf':
                    amt = random.randint(500, 1500)
                    total_rf += amt
                    user.radfragments += amt
                elif r == 'armor5':
                    add_item('🥇 Силовая броня')
                    add_item_to_inventory(user, 'броня5', 1)
                elif r == 'gauss':
                    add_item('⚡ Винтовка Гаусса')
                    add_item_to_inventory(user, 'гаусс', 1)
                elif r == 'medkit':
                    amt = random.randint(2, 5)
                    add_item(f'💊 Аптечка x{amt}')
                    add_item_to_inventory(user, 'аптечка', amt)
                elif r == 'reducer_quantum':
                    add_item('🌀 Квантовый редуктор')
                    add_item_to_inventory(user, 'редуктор_quantum', 1)
                elif r == 'energy_redbull':
                    add_item('🔴 Энергетик RedBull')
                    add_item_to_inventory(user, 'энергетик_redbull', 1)
                elif r == 'pet':
                    if not pet_added_this and not pet_gained and random.random() < 0.02:
                        pets = ['овчарка', 'волк', 'рысь', 'пума', 'попугай', 'кайот']
                        pet_gained = random.choice(pets)
                        user.pet = pet_gained
                        pet_names = {
                            'овчарка': '🐕 Овчарка', 'волк': '🐺 Волк',
                            'рысь': '🐈 Рысь', 'пума': '🐆 Пума',
                            'попугай': '🦜 Попугай', 'кайот': '🐕 Кайот'
                        }
                        add_item(f'🐾 {pet_names.get(pet_gained, pet_gained)}')
                        pet_added_this = True
                elif r == 'harpoon':
                    add_item('🎣 Гарпун')
                    add_item_to_inventory(user, 'гарпун', 1)
                elif r == 'chest_mythic':
                    add_item('🟡 Мифический сундук')
                    user.chest_mythic += 1
                elif r == 'backpack2':
                    add_item('🎒 Тактический рюкзак')
                    add_item_to_inventory(user, 'backpack2', 1)
                elif r == 'backpack3':
                    add_item('🎒 Профессиональный рюкзак')
                    add_item_to_inventory(user, 'backpack3', 1)
                elif r == 'metal_detector':
                    add_item('🔍 Металлоискатель')
                    add_item_to_inventory(user, 'metal_detector', 1)
            user.chest_legendary -= 1

        session.commit()

        safe_log_user_action(
            log_user_id, log_username, 'chest_open_all',
            amount_rc=total_rc, amount_rf=total_rf,
            item=f"common:{total_common}, rare:{total_rare}, epic:{total_epic}, mythic:{total_mythic}, legendary:{total_legendary}"
        )

        result_text = f"🎁 *Результат открытия сундуков*\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        if total_rc > 0:
            result_text += f"💰 ☢️ +{total_rc} RC\n"
        if total_rf > 0:
            result_text += f"💰 ☣️ +{total_rf} RF\n\n"

        if items_gained:
            result_text += f"📦 *Предметы:*\n"
            for item, count in items_gained.items():
                result_text += f"• {item} x{count}\n"

        if pet_gained:
            pet_names = {
                'овчарка': '🐕 Овчарка', 'волк': '🐺 Волк',
                'рысь': '🐈 Рысь', 'пума': '🐆 Пума',
                'попугай': '🦜 Попугай', 'кайот': '🐕 Кайот'
            }
            result_text += f"\n🐾 *Новый питомец:* {pet_names.get(pet_gained, pet_gained)}!\n"

        await update.message.reply_text(result_text, parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Error in chest_open_all: {e}")
        session.rollback()
        await update.message.reply_text("❌ Ошибка при открытии сундуков")
    finally:
        session.close()
