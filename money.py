# money.py - Экономика и магазин
# Версия: 4.0.0 (ALPHA)

import random
import json
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import ContextTypes

from config import (
    logger, MAX_MEDKITS, CASINO_PUBLIC_CHANCE, CASINO_PUBLIC_CASH_MULT,
    CASINO_MIN_BET, CASINO_MAX_BET, SHOP_LIMITS, SHOP_RESET_HOURS,
    ENERGY_DRINKS, REDUCERS, BACKPACKS, METAL_DETECTOR,
    get_energy_bonus, get_reducer_bonus
)
from core import send_to_private
from database import Session, User
from utils import (
    get_inventory, get_equipped, get_item_count, add_item_to_inventory,
    remove_item_from_inventory, check_achievements, save_equipped,
    log_user_action, escape_markdown, get_backpack, get_medkits_in_backpack,
    add_medkits_to_backpack, remove_medkits_from_backpack
)


# ==================== ОБЩИЕ ЛИМИТЫ ====================

def check_global_shop_limit(item, count, context):
    """Проверка общих лимитов магазина"""
    if item not in SHOP_LIMITS:
        return True, None
    
    now = datetime.now()
    last_reset = context.bot_data.get('last_shop_reset')
    limits = context.bot_data.get('shop_limits', {})
    
    if last_reset and now - last_reset > timedelta(hours=SHOP_RESET_HOURS):
        context.bot_data['shop_limits'] = SHOP_LIMITS.copy()
        context.bot_data['last_shop_reset'] = now
        limits = context.bot_data['shop_limits']
    
    available = limits.get(item, 0)
    
    if count > available:
        next_reset = last_reset + timedelta(hours=SHOP_RESET_HOURS) if last_reset else now + timedelta(hours=SHOP_RESET_HOURS)
        remaining = next_reset - now
        hours = remaining.seconds // 3600
        minutes = (remaining.seconds % 3600) // 60
        return False, f"❌ Лимит на {item}: осталось {available} шт. Поставка через {hours}ч {minutes}мин"
    
    return True, None


def apply_global_shop_limit(item, count, context):
    """Списать товар из общих лимитов"""
    limits = context.bot_data.get('shop_limits', {})
    if item in limits:
        limits[item] -= count
        context.bot_data['shop_limits'] = limits


# ==================== ИНВЕНТАРЬ ====================

async def inv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать инвентарь и экипировку"""
    session = Session()
    try:
        user = session.query(User).filter_by(user_id=update.effective_user.id).first()
        if not user:
            await update.message.reply_text("❌ /start")
            return
        
        inventory = get_inventory(user)
        equipped = get_equipped(user)
        
        text = "📦 *Инвентарь*\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        # Экипировка
        text += "*🟢 ЭКИПИРОВАНО*\n"
        armor_display = {
            'броня1': '🟢 Лёгкая броня (25%)',
            'броня2': '🔵 Утяжеленная броня (40%)',
            'броня3': '🟣 Тактическая броня (50%)',
            'броня4': '🟠 Тяжёлая броня (60%)',
            'броня5': '🔴 Силовая броня (75%)'
        }
        if equipped.get('armor'):
            text += f"{armor_display.get(equipped['armor'], equipped['armor'])} — активна\n"
        
        weapon_display = {
            'ружье': '🔫 Ружьё',
            'гарпун': '🎣 Гарпун',
            'винтовка': '🔫 Винтовка',
            'гаусс': '⚡ Винтовка Гаусса'
        }
        if equipped.get('weapon'):
            text += f"{weapon_display.get(equipped['weapon'], equipped['weapon'])} — экипировано\n"
        
        # Рюкзак (НОВОЕ!)
        backpack_display = {
            'backpack1': '🎒 Маленький рюкзак (+20% RC, +10% RF, 1 аптечка)',
            'backpack2': '🎒 Тактический рюкзак (+30% RC, +15% RF, 2 аптечки)',
            'backpack3': '🎒 Профессиональный рюкзак (+45% RC, +18% RF, 3 аптечки)'
        }
        if equipped.get('backpack'):
            backpack_type = equipped.get('backpack')
            medkits_in_backpack = get_medkits_in_backpack(user)
            text += f"{backpack_display.get(backpack_type, backpack_type)} — экипирован"
            text += f" (💊 {medkits_in_backpack}/{BACKPACKS.get(backpack_type, {}).get('medkit_slots', 0)} аптечек)\n"
        
        if not any([equipped.get('armor'), equipped.get('weapon'), equipped.get('backpack')]):
            text += "❌ Нет экипированных предметов\n"
        
        # Предметы в инвентаре
        text += "\n*📦 ПРЕДМЕТЫ*\n"
        inventory.sort(key=lambda x: x['item'])
        
        item_names = {
            'броня1': '🟢 Лёгкая броня', 'броня2': '🔵 Утяжеленная броня',
            'броня3': '🟣 Тактическая броня', 'броня4': '🟠 Тяжёлая броня',
            'броня5': '🔴 Силовая броня', 'ружье': '🔫 Ружьё',
            'гарпун': '🎣 Гарпун', 'винтовка': '🔫 Винтовка',
            'гаусс': '⚡ Винтовка Гаусса', 'аптечка': '💊 Аптечка',
            'металлоискатель': '🔍 Металлоискатель',
            'backpack1': '🎒 Маленький рюкзак',
            'backpack2': '🎒 Тактический рюкзак',
            'backpack3': '🎒 Профессиональный рюкзак'
        }
        
        # Энергетики
        for key, data in ENERGY_DRINKS.items():
            item_names[f'энергетик_{key}'] = data['name']
        
        # Редукторы
        for key, data in REDUCERS.items():
            item_names[f'редуктор_{key}'] = data['name']
        
        for item in inventory:
            name = item['item']
            count = item['count']
            display_name = item_names.get(name, name)
            expires = item.get('expires')
            if expires:
                exp_date = datetime.fromisoformat(expires)
                if exp_date > datetime.now():
                    text += f"{display_name} — {count} шт (до {exp_date.strftime('%d.%m %H:%M')})\n"
            else:
                text += f"{display_name} — {count} шт\n"
        
        if not inventory:
            text += "❌ Инвентарь пуст\n"
        
        # Активные эффекты
        text += "\n*⚡ АКТИВНЫЕ ЭФФЕКТЫ*\n"
        now = datetime.now()
        
        if user.energy_drink_until and user.energy_drink_until > now:
            remaining = user.energy_drink_until - now
            hours = remaining.seconds // 3600
            minutes = (remaining.seconds % 3600) // 60
            energy_level = getattr(user, 'energy_drink_level', 'strike')
            energy_data = get_energy_bonus(energy_level)
            text += f"⚡ {energy_data['name']} — {hours}ч {minutes}мин (стеков: {user.energy_drink_stacks})\n"
        else:
            text += "⚡ Энергетик — не активен\n"
        
        if user.cooldown_reducer_until and user.cooldown_reducer_until > now:
            remaining = user.cooldown_reducer_until - now
            days = remaining.days
            hours = remaining.seconds // 3600
            reducer_level = getattr(user, 'reducer_level', 'basic')
            reducer_data = get_reducer_bonus(reducer_level)
            text += f"⏱️ {reducer_data['name']} — {days}д {hours}ч (стеков: {user.reducer_stacks})\n"
        else:
            text += "⏱️ Редуктор — не активен\n"
        
        text += "\n💡 Команды:\n/sell [предмет] [кол-во]\n/equip броня/оружие/рюкзак [название]\n/equip броня/оружие/рюкзак 0 — снять\n/use энергетик/редуктор [кол-во]\n/use аптечка [кол-во] — положить в рюкзак\n/use_metal_detector — использовать металлоискатель"
        
        await send_to_private(update, context, text)
    except Exception as e:
        logger.error(f"Error in inv: {e}")
        await update.message.reply_text("❌ Ошибка")
    finally:
        session.close()


# ==================== МАГАЗИН ====================

async def shop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать магазин (только доступные товары)"""
    session = Session()
    try:
        user = session.query(User).filter_by(user_id=update.effective_user.id).first()
        if not user:
            await update.message.reply_text("❌ /start")
            return
        
        now = datetime.now()
        discount = context.bot_data.get('sale_discount', 0)
        sale_until = context.bot_data.get('sale_until')
        
        sale_line = ""
        if discount > 0 and sale_until and sale_until > now:
            remaining = sale_until - now
            hours = remaining.seconds // 3600
            minutes = (remaining.seconds % 3600) // 60
            sale_line = f"\n\n🔥 *РАСПРОДАЖА {discount}%!* {hours}ч {minutes}мин 🔥"
        
        text = f"🛒 *Магазин Пустоши*{sale_line}\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
        text += f"👤 *Ваш уровень:* {user.level}\n\n"
        
        # Броня
        text += "*🛡️ БРОНЯ*\n"
        if user.level >= 1:
            text += "• 🟢 Лёгкая броня (1000) — 25%\n"
        if user.level >= 10:
            text += "• 🔵 Утяжеленная броня (2500) — 40%\n"
        if user.level >= 1:
            text += "• 🟣 Тактическая броня (5000) — 50% (лимит 10)\n"
        if user.level >= 25:
            text += "• 🟠 Тяжёлая броня (10000) — 60% (лимит 7)\n"
        if user.level >= 50:
            text += "• 🔴 Силовая броня (25000) — 75% (лимит 5)\n"
        text += "\n"
        
        # Оружие
        text += "*⚔️ ОРУЖИЕ*\n"
        if user.level >= 1:
            text += "• 🔫 Ружьё (300)\n"
        if user.level >= 10:
            text += "• 🎣 Гарпун (500)\n"
        if user.level >= 25:
            text += "• 🔫 Винтовка (5000) (лимит 7)\n"
        if user.level >= 50:
            text += "• ⚡ Винтовка Гаусса (20000) (лимит 5)\n"
        text += "\n"
        
        # Энергетики (без лимитов!)
        text += "*⚡ ЭНЕРГЕТИКИ* (6 часов, без лимитов)\n"
        for key, data in ENERGY_DRINKS.items():
            if user.level >= data['level_required']:
                text += f"• {data['name']} ({data['price']}) — +{(data['rc_bonus']-1)*100:.0f}% RC, +{(data['rf_bonus']-1)*100:.0f}% RF, +{data['survive_bonus']}% выживание\n"
        text += "\n"
        
        # Редукторы (без лимитов!)
        text += "*⏱️ РЕДУКТОРЫ* (3 дня, без лимитов)\n"
        for key, data in REDUCERS.items():
            if user.level >= data['level_required']:
                text += f"• {data['name']} ({data['price']}) — ускорение {int((1-data['cooldown_reduction'])*100)}%\n"
        text += "\n"
        
        # Рюкзаки (НОВЫЕ! без лимитов)
        text += "*🎒 РЮКЗАКИ* (без лимитов)\n"
        for key, data in BACKPACKS.items():
            if user.level >= data['level_required']:
                text += f"• {data['name']} ({data['price']}) — +{data['rc_bonus']}% RC, +{data['rf_bonus']}% RF, {data['medkit_slots']} аптечка\n"
        text += "\n"
        
        # Металлоискатель (НОВЫЙ!)
        if user.level >= METAL_DETECTOR['level_required']:
            text += "*🔍 ПРОЧЕЕ*\n"
            text += f"• {METAL_DETECTOR['name']} ({METAL_DETECTOR['price']}) — {METAL_DETECTOR['chest_chance']}% шанс найти сундук\n\n"
        
        # Расходники
        text += "*💊 РАСХОДНИКИ*\n"
        text += "• 💊 Аптечка (125) (лимит 75)\n"
        
        # Остатки на складе (только для лимитированных товаров)
        limits = context.bot_data.get('shop_limits', {})
        text += "\n*📦 ОСТАТКИ НА СКЛАДЕ*\n"
        text += f"• Тактическая броня ({limits.get('броня3', 10)}/10)\n"
        text += f"• Тяжёлая броня ({limits.get('броня4', 7)}/7)\n"
        text += f"• Силовая броня ({limits.get('броня5', 5)}/5)\n"
        text += f"• Винтовка ({limits.get('винтовка', 7)}/7)\n"
        text += f"• Гаусс ({limits.get('гаусс', 5)}/5)\n"
        text += f"• Аптечка ({limits.get('аптечка', 75)}/75)\n"
        
        last_reset = context.bot_data.get('last_shop_reset')
        if last_reset:
            next_reset = last_reset + timedelta(hours=SHOP_RESET_HOURS)
            if next_reset > now:
                remaining = next_reset - now
                hours = remaining.seconds // 3600
                minutes = (remaining.seconds % 3600) // 60
                text += f"\n🔄 Поставка через: {hours}ч {minutes}мин\n"
            else:
                text += "\n🔄 Новая поставка уже доступна!\n"
        
        text += "\n📝 */buy [товар] [кол-во]*"
        
        await send_to_private(update, context, text)
    except Exception as e:
        logger.error(f"Error in shop: {e}")
        await update.message.reply_text("❌ Ошибка")
    finally:
        session.close()


# ==================== ПОКУПКА ====================

async def buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Купить предмет (включая новые энергетики, редукторы, рюкзаки, металлоискатель)"""
    if not context.args:
        await update.message.reply_text("❌ /buy [товар] [кол-во]")
        return
    
    item = context.args[0].lower()
    count = 1
    if len(context.args) > 1:
        try:
            count = int(context.args[1])
            if count <= 0 or count > 100:
                await update.message.reply_text("❌ 1-100 штук за раз")
                return
        except ValueError:
            await update.message.reply_text("❌ Введите число")
            return
    
    session = Session()
    try:
        user = session.query(User).filter_by(user_id=update.effective_user.id).first()
        if not user:
            await update.message.reply_text("❌ /start")
            return
        
        # Цены на товары
        prices = {
            'аптечка': 125,
            'ружье': 300, 'гарпун': 500, 'винтовка': 5000, 'гаусс': 20000,
            'броня1': 1000, 'броня2': 2500, 'броня3': 5000,
            'броня4': 10000, 'броня5': 25000,
            'металлоискатель': METAL_DETECTOR['price']
        }
        
        # Добавляем цены на энергетики
        for key, data in ENERGY_DRINKS.items():
            prices[key] = data['price']
        
        # Добавляем цены на редукторы
        for key, data in REDUCERS.items():
            prices[key] = data['price']
        
        # Добавляем цены на рюкзаки (НОВЫЕ!)
        for key, data in BACKPACKS.items():
            prices[key] = data['price']
        
        if item not in prices:
            await update.message.reply_text(f"❌ Товар '{item}' не найден")
            return
        
        # Проверка уровня для новых предметов
        if item in ENERGY_DRINKS:
            required_level = ENERGY_DRINKS[item]['level_required']
            if user.level < required_level:
                await update.message.reply_text(f"❌ {ENERGY_DRINKS[item]['name']} доступен с {required_level} уровня!")
                return
        elif item in REDUCERS:
            required_level = REDUCERS[item]['level_required']
            if user.level < required_level:
                await update.message.reply_text(f"❌ {REDUCERS[item]['name']} доступен с {required_level} уровня!")
                return
        elif item in BACKPACKS:
            required_level = BACKPACKS[item]['level_required']
            if user.level < required_level:
                await update.message.reply_text(f"❌ {BACKPACKS[item]['name']} доступен с {required_level} уровня!")
                return
        elif item == 'металлоискатель':
            if user.level < METAL_DETECTOR['level_required']:
                await update.message.reply_text(f"❌ Металлоискатель доступен с {METAL_DETECTOR['level_required']} уровня!")
                return
        
        # Проверка уровня для старых предметов
        if item == 'гарпун' and user.level < 10:
            await update.message.reply_text("❌ Гарпун доступен с 10 уровня!")
            return
        if item == 'винтовка' and user.level < 25:
            await update.message.reply_text("❌ Винтовка доступна с 25 уровня!")
            return
        if item == 'гаусс' and user.level < 50:
            await update.message.reply_text("❌ Винтовка Гаусса доступна с 50 уровня!")
            return
        if item == 'броня2' and user.level < 10:
            await update.message.reply_text("❌ Утяжеленная броня доступна с 10 уровня!")
            return
        if item == 'броня4' and user.level < 25:
            await update.message.reply_text("❌ Тяжёлая броня доступна с 25 уровня!")
            return
        if item == 'броня5' and user.level < 50:
            await update.message.reply_text("❌ Силовая броня доступна с 50 уровня!")
            return
        
        # Проверка лимита (только для старых лимитированных товаров)
        if item in SHOP_LIMITS:
            can_buy, limit_msg = check_global_shop_limit(item, count, context)
            if not can_buy:
                await update.message.reply_text(limit_msg, parse_mode='Markdown')
                return
        
        # Расчёт стоимости со скидкой
        total = prices[item] * count
        now = datetime.now()
        discount = context.bot_data.get('sale_discount', 0)
        sale_until = context.bot_data.get('sale_until')
        
        if discount > 0 and sale_until and sale_until > now:
            old_total = total
            total = int(total * (100 - discount) / 100)
            discount_msg = f"\n🏷️ Скидка {discount}%: {old_total} → {total} RC!"
        else:
            discount_msg = ""
        
        if user.radcoins < total:
            await update.message.reply_text(f"❌ Нужно {total} RC, у вас {user.radcoins:.0f}")
            return
        
        user.radcoins -= total
        
        # Выдача предмета
        if item in ENERGY_DRINKS:
            add_item_to_inventory(user, f'энергетик_{item}', count)
        elif item in REDUCERS:
            add_item_to_inventory(user, f'редуктор_{item}', count)
        elif item in BACKPACKS:
            add_item_to_inventory(user, item, count)
        elif item == 'металлоискатель':
            add_item_to_inventory(user, 'metal_detector', count)
        elif item == 'ружье':
            add_item_to_inventory(user, 'ружье', count)
        elif item == 'гарпун':
            add_item_to_inventory(user, 'гарпун', count)
        elif item == 'винтовка':
            add_item_to_inventory(user, 'винтовка', count)
        elif item == 'гаусс':
            add_item_to_inventory(user, 'гаусс', count)
        elif item == 'аптечка':
            add_item_to_inventory(user, 'аптечка', count)
        elif item == 'броня1':
            add_item_to_inventory(user, 'броня1', count)
        elif item == 'броня2':
            add_item_to_inventory(user, 'броня2', count)
        elif item == 'броня3':
            add_item_to_inventory(user, 'броня3', count)
        elif item == 'броня4':
            add_item_to_inventory(user, 'броня4', count)
        elif item == 'броня5':
            add_item_to_inventory(user, 'броня5', count)
        
        # Списание из общих лимитов (только для старых лимитированных товаров)
        if item in SHOP_LIMITS:
            apply_global_shop_limit(item, count, context)
        
        user.total_purchases += count
        check_achievements(user)
        
        session.commit()
        
        log_user_action(
            user.user_id, user.username, 'buy',
            amount_rc=-total, item=f"{item}x{count}"
        )
        
        # Формируем название предмета для вывода
        item_names = {
            'аптечка': '💊 Аптечка',
            'ружье': '🔫 Ружьё', 'гарпун': '🎣 Гарпун',
            'винтовка': '🔫 Винтовка', 'гаусс': '⚡ Винтовка Гаусса',
            'броня1': '🟢 Лёгкая броня', 'броня2': '🔵 Утяжеленная броня',
            'броня3': '🟣 Тактическая броня', 'броня4': '🟠 Тяжёлая броня',
            'броня5': '🔴 Силовая броня',
            'металлоискатель': '🔍 Металлоискатель'
        }
        
        for key, data in ENERGY_DRINKS.items():
            item_names[key] = data['name']
        for key, data in REDUCERS.items():
            item_names[key] = data['name']
        for key, data in BACKPACKS.items():
            item_names[key] = data['name']
        
        display_name = item_names.get(item, item)
        msg = f"✅ *Куплено {display_name} x{count}*\n💰 -{total} RC{discount_msg}\n☢️ Осталось: {user.radcoins:.0f} RC"
        
        if item in SHOP_LIMITS:
            limits = context.bot_data.get('shop_limits', {})
            available = limits.get(item, 0)
            total_limit = SHOP_LIMITS[item]
            msg += f"\n📦 Осталось на складе: {available}/{total_limit}"
        
        await update.message.reply_text(msg, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Error in buy: {e}")
        session.rollback()
        await update.message.reply_text("❌ Ошибка")
    finally:
        session.close()


# ==================== ПРОДАЖА ====================

async def sell(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Продать предмет (включая новые)"""
    if not context.args:
        await update.message.reply_text(
            "💰 *Продажа предметов*\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "/sell [предмет] — продать 1 шт\n"
            "/sell [предмет] [кол-во] — продать N шт\n"
            "/sell all [предмет] — продать все\n\n"
            "Доступные предметы:\n"
            "броня1-5, ружье, гарпун, винтовка, гаусс,\n"
            "аптечка, металлоискатель,\n"
            "энергетики: strike, tornado, adrenaline, redbull,\n"
            "редукторы: basic, advanced, quantum,\n"
            "рюкзаки: backpack1, backpack2, backpack3\n\n"
            "💰 Комиссия: 20%",
            parse_mode='Markdown'
        )
        return
    
    session = Session()
    try:
        user = session.query(User).filter_by(user_id=update.effective_user.id).first()
        if not user:
            await update.message.reply_text("❌ /start")
            return
        
        item = context.args[0].lower()
        count = 1
        sell_all = False
        
        if len(context.args) > 1:
            if context.args[1].lower() == 'all':
                sell_all = True
            else:
                try:
                    count = int(context.args[1])
                    if count <= 0:
                        await update.message.reply_text("❌ Положительное число")
                        return
                except ValueError:
                    await update.message.reply_text("❌ Введите число")
                    return
        
        # Цены продажи (80% от покупки)
        sell_prices = {
            'броня1': 800, 'броня2': 2000, 'броня3': 4000,
            'броня4': 8000, 'броня5': 20000,
            'ружье': 240, 'гарпун': 400, 'винтовка': 4000, 'гаусс': 16000,
            'аптечка': 100, 'металлоискатель': int(METAL_DETECTOR['price'] * 0.8)
        }
        
        for key, data in ENERGY_DRINKS.items():
            sell_prices[key] = int(data['price'] * 0.8)
        
        for key, data in REDUCERS.items():
            sell_prices[key] = int(data['price'] * 0.8)
        
        for key, data in BACKPACKS.items():
            sell_prices[key] = int(data['price'] * 0.8)
        
        # Определяем имя предмета в инвентаре
        if item in ENERGY_DRINKS:
            item_name = f'энергетик_{item}'
        elif item in REDUCERS:
            item_name = f'редуктор_{item}'
        elif item in BACKPACKS:
            item_name = item
        else:
            item_name = item
        
        if item not in sell_prices:
            await update.message.reply_text(f"❌ Неизвестный предмет: {item}")
            return
        
        available = get_item_count(user, item_name)
        if available == 0:
            await update.message.reply_text(f"❌ У вас нет {item}")
            return
        
        if sell_all:
            count = available
        elif count > available:
            await update.message.reply_text(f"❌ У вас только {available} шт")
            return
        
        # Проверка, не экипирован ли предмет
        equipped = get_equipped(user)
        if item_name == equipped.get('armor') or item_name == equipped.get('weapon') or item_name == equipped.get('backpack'):
            await update.message.reply_text(f"❌ Предмет {item} экипирован! Снимите его перед продажей.")
            return
        
        remove_item_from_inventory(user, item_name, count)
        total = sell_prices[item] * count
        user.radcoins += total
        check_achievements(user)
        
        session.commit()
        
        log_user_action(
            user.user_id, user.username, 'sell',
            amount_rc=total, item=f"{item}x{count}"
        )
        
        item_names = {
            'броня1': '🟢 Лёгкая броня', 'броня2': '🔵 Утяжеленная броня',
            'броня3': '🟣 Тактическая броня', 'броня4': '🟠 Тяжёлая броня',
            'броня5': '🔴 Силовая броня',
            'ружье': '🔫 Ружьё', 'гарпун': '🎣 Гарпун',
            'винтовка': '🔫 Винтовка', 'гаусс': '⚡ Винтовка Гаусса',
            'аптечка': '💊 Аптечка', 'металлоискатель': '🔍 Металлоискатель'
        }
        
        for key, data in ENERGY_DRINKS.items():
            item_names[key] = data['name']
        for key, data in REDUCERS.items():
            item_names[key] = data['name']
        for key, data in BACKPACKS.items():
            item_names[key] = data['name']
        
        display_name = item_names.get(item, item)
        await update.message.reply_text(
            f"💰 *Продажа!*\n\n"
            f"📦 {display_name} x{count}\n"
            f"💵 Получено: +{total} RC\n"
            f"📊 Осталось: {user.radcoins:.0f} RC",
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Error in sell: {e}")
        session.rollback()
        await update.message.reply_text("❌ Ошибка")
    finally:
        session.close()


# ==================== ЭКИПИРОВКА ====================

async def equip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Экипировать предметы (броня, оружие, рюкзак)"""
    if len(context.args) < 2:
        await update.message.reply_text(
            "⚔️ *Экипировка*\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "/equip броня [название] — надеть броню\n"
            "/equip броня 0 — снять броню\n"
            "/equip оружие [название] — надеть оружие\n"
            "/equip оружие 0 — снять оружие\n"
            "/equip рюкзак [название] — надеть рюкзак\n"
            "/equip рюкзак 0 — снять рюкзак\n\n"
            "Доступные предметы:\n"
            "броня1-5, ружье, гарпун, винтовка, гаусс,\n"
            "рюкзак1 (backpack1), рюкзак2 (backpack2), рюкзак3 (backpack3)",
            parse_mode='Markdown'
        )
        return
    
    equip_type = context.args[0].lower()
    value = context.args[1].lower()
    
    session = Session()
    try:
        user = session.query(User).filter_by(user_id=update.effective_user.id).first()
        if not user:
            await update.message.reply_text("❌ /start")
            return
        
        equipped = get_equipped(user)
        
        armor_names = {
            'броня1': '🟢 Лёгкая броня', 'броня2': '🔵 Утяжеленная броня',
            'броня3': '🟣 Тактическая броня', 'броня4': '🟠 Тяжёлая броня',
            'броня5': '🔴 Силовая броня'
        }
        weapon_names = {
            'ружье': '🔫 Ружьё', 'гарпун': '🎣 Гарпун',
            'винтовка': '🔫 Винтовка', 'гаусс': '⚡ Винтовка Гаусса'
        }
        backpack_names = {
            'backpack1': '🎒 Маленький рюкзак',
            'backpack2': '🎒 Тактический рюкзак',
            'backpack3': '🎒 Профессиональный рюкзак'
        }
        
        # Броня
        if equip_type == 'броня':
            if value == '0':
                old_armor = equipped.get('armor')
                if old_armor:
                    add_item_to_inventory(user, old_armor, 1)
                    equipped['armor'] = None
                    save_equipped(user, equipped)
                    session.commit()
                    await update.message.reply_text(f"✅ *Снята броня*\n\n{armor_names.get(old_armor, old_armor)} снята", parse_mode='Markdown')
                else:
                    await update.message.reply_text("❌ Нет надетой брони")
                return
            
            if value not in armor_names:
                await update.message.reply_text("❌ Доступно: броня1-5")
                return
            
            if get_item_count(user, value) == 0:
                await update.message.reply_text(f"❌ У вас нет {armor_names.get(value, value)}")
                return
            
            old_armor = equipped.get('armor')
            if old_armor:
                add_item_to_inventory(user, old_armor, 1)
            
            remove_item_from_inventory(user, value, 1)
            equipped['armor'] = value
            save_equipped(user, equipped)
            session.commit()
            
            old_text = f"{armor_names.get(old_armor, old_armor)}" if old_armor else "ничего"
            await update.message.reply_text(
                f"✅ *Экипировано!*\n\n"
                f"🛡️ {armor_names.get(value, value)}\n"
                f"📦 Прежнее: {old_text}",
                parse_mode='Markdown'
            )
        
        # Оружие
        elif equip_type == 'оружие':
            if value == '0':
                old_weapon = equipped.get('weapon')
                if old_weapon:
                    add_item_to_inventory(user, old_weapon, 1)
                    equipped['weapon'] = None
                    save_equipped(user, equipped)
                    session.commit()
                    await update.message.reply_text(f"✅ *Снято оружие*\n\n{weapon_names.get(old_weapon, old_weapon)} снято", parse_mode='Markdown')
                else:
                    await update.message.reply_text("❌ Нет экипированного оружия")
                return
            
            if value not in weapon_names:
                await update.message.reply_text("❌ Доступно: ружье, гарпун, винтовка, гаусс")
                return
            
            if get_item_count(user, value) == 0:
                await update.message.reply_text(f"❌ У вас нет {weapon_names.get(value, value)}")
                return
            
            old_weapon = equipped.get('weapon')
            if old_weapon:
                add_item_to_inventory(user, old_weapon, 1)
            
            remove_item_from_inventory(user, value, 1)
            equipped['weapon'] = value
            save_equipped(user, equipped)
            session.commit()
            
            old_text = f"{weapon_names.get(old_weapon, old_weapon)}" if old_weapon else "ничего"
            await update.message.reply_text(
                f"✅ *Экипировано!*\n\n"
                f"⚔️ {weapon_names.get(value, value)}\n"
                f"📦 Прежнее: {old_text}",
                parse_mode='Markdown'
            )
        
        # Рюкзак (НОВОЕ!)
        elif equip_type == 'рюкзак':
            if value == '0':
                old_backpack = equipped.get('backpack')
                if old_backpack:
                    # При снятии рюкзака аптечки возвращаются в инвентарь
                    medkits = get_medkits_in_backpack(user)
                    if medkits > 0:
                        add_item_to_inventory(user, 'аптечка', medkits)
                        remove_medkits_from_backpack(user, medkits)
                    add_item_to_inventory(user, old_backpack, 1)
                    equipped['backpack'] = None
                    save_equipped(user, equipped)
                    session.commit()
                    await update.message.reply_text(f"✅ *Снят рюкзак*\n\n{backpack_names.get(old_backpack, old_backpack)} снят, аптечки возвращены в инвентарь", parse_mode='Markdown')
                else:
                    await update.message.reply_text("❌ Нет экипированного рюкзака")
                return
            
            if value not in backpack_names:
                await update.message.reply_text("❌ Доступно: backpack1, backpack2, backpack3")
                return
            
            if get_item_count(user, value) == 0:
                await update.message.reply_text(f"❌ У вас нет {backpack_names.get(value, value)}")
                return
            
            old_backpack = equipped.get('backpack')
            if old_backpack:
                # При смене рюкзака аптечки возвращаются в инвентарь
                medkits = get_medkits_in_backpack(user)
                if medkits > 0:
                    add_item_to_inventory(user, 'аптечка', medkits)
                    remove_medkits_from_backpack(user, medkits)
                add_item_to_inventory(user, old_backpack, 1)
            
            remove_item_from_inventory(user, value, 1)
            equipped['backpack'] = value
            save_equipped(user, equipped)
            session.commit()
            
            old_text = f"{backpack_names.get(old_backpack, old_backpack)}" if old_backpack else "ничего"
            await update.message.reply_text(
                f"✅ *Экипировано!*\n\n"
                f"🎒 {backpack_names.get(value, value)}\n"
                f"📦 Прежнее: {old_text}\n\n"
                f"💡 Положите аптечки в рюкзак: `/use аптечка [кол-во]`",
                parse_mode='Markdown'
            )
        
        else:
            await update.message.reply_text("❌ Используйте: броня, оружие, рюкзак")
    
    except Exception as e:
        logger.error(f"Error in equip: {e}")
        session.rollback()
        await update.message.reply_text("❌ Ошибка")
    finally:
        session.close()


# ==================== ИСПОЛЬЗОВАНИЕ ПРЕДМЕТОВ ====================

async def use_item(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Использовать расходный предмет (энергетик, редуктор, или положить аптечку в рюкзак)"""
    if not context.args:
        await update.message.reply_text(
            "⚡ *Использование предметов*\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "/use энергетик [кол-во] — активировать энергетик (вашего уровня)\n"
            "/use редуктор [кол-во] — активировать редуктор (вашего уровня)\n"
            "/use аптечка [кол-во] — положить аптечки в рюкзак\n\n"
            "📦 Можно использовать несколько штук сразу, эффекты суммируются.\n"
            "💡 Уровень энергетика/редуктора определяется вашим текущим уровнем расходника.\n"
            "🎒 Аптечки в рюкзаке спасают от смерти в метро!",
            parse_mode='Markdown'
        )
        return
    
    item = context.args[0].lower()
    count = 1
    if len(context.args) > 1:
        try:
            count = int(context.args[1])
            if count <= 0 or count > 100:
                await update.message.reply_text("❌ 1-100 штук за раз")
                return
        except ValueError:
            await update.message.reply_text("❌ Введите число")
            return
    
    session = Session()
    try:
        user = session.query(User).filter_by(user_id=update.effective_user.id).first()
        if not user:
            await update.message.reply_text("❌ /start")
            return
        
        now = datetime.now()
        
        # ==================== ЭНЕРГЕТИК ====================
        if item == 'энергетик':
            energy_level = getattr(user, 'energy_drink_level', 'strike')
            item_name = f'энергетик_{energy_level}'
            energy_data = get_energy_bonus(energy_level)
            
            available = get_item_count(user, item_name)
            if available < count:
                await update.message.reply_text(f"❌ У вас только {available} энергетиков уровня {energy_level}!")
                return
            
            remove_item_from_inventory(user, item_name, count)
            
            if user.energy_drink_until and user.energy_drink_until > now:
                user.energy_drink_until += timedelta(hours=energy_data['duration_hours'] * count)
                user.energy_drink_stacks += count
            else:
                user.energy_drink_until = now + timedelta(hours=energy_data['duration_hours'] * count)
                user.energy_drink_stacks = count
                user.energy_drink_level = energy_level
            
            session.commit()
            
            log_user_action(
                user.user_id, user.username, 'use_energy',
                item=f"{energy_level}x{count}"
            )
            
            hours = energy_data['duration_hours'] * count
            await update.message.reply_text(
                f"⚡ *{energy_data['name']} активирован!*\n\n"
                f"📦 Использовано: {count} шт\n"
                f"⏰ Длительность: {hours} часов\n"
                f"✨ Бонусы:\n"
                f"  • +{(energy_data['rc_bonus']-1)*100:.0f}% к сбору RC\n"
                f"  • +{(energy_data['rf_bonus']-1)*100:.0f}% к сбору RF\n"
                f"  • +{(energy_data['crystal_bonus']-1)*100:.0f}% к кристаллам\n"
                f"  • +{energy_data['survive_bonus']}% к выживанию на охоте\n\n"
                f"📊 Активно до: {user.energy_drink_until.strftime('%d.%m %H:%M')}",
                parse_mode='Markdown'
            )
        
        # ==================== РЕДУКТОР ====================
        elif item == 'редуктор':
            reducer_level = getattr(user, 'reducer_level', 'basic')
            item_name = f'редуктор_{reducer_level}'
            reducer_data = get_reducer_bonus(reducer_level)
            
            available = get_item_count(user, item_name)
            if available < count:
                await update.message.reply_text(f"❌ У вас только {available} редукторов уровня {reducer_level}!")
                return
            
            remove_item_from_inventory(user, item_name, count)
            
            if user.cooldown_reducer_until and user.cooldown_reducer_until > now:
                user.cooldown_reducer_until += timedelta(days=reducer_data['duration_days'] * count)
                user.reducer_stacks += count
            else:
                user.cooldown_reducer_until = now + timedelta(days=reducer_data['duration_days'] * count)
                user.reducer_stacks = count
                user.reducer_level = reducer_level
            
            session.commit()
            
            log_user_action(
                user.user_id, user.username, 'use_reducer',
                item=f"{reducer_level}x{count}"
            )
            
            days = reducer_data['duration_days'] * count
            await update.message.reply_text(
                f"⏱️ *{reducer_data['name']} активирован!*\n\n"
                f"📦 Использовано: {count} шт\n"
                f"⏰ Длительность: {days} дней\n"
                f"⚡ Эффект: ускорение восстановления сбора на {int((1-reducer_data['cooldown_reduction'])*100)}%\n\n"
                f"📊 Активно до: {user.cooldown_reducer_until.strftime('%d.%m %H:%M')}",
                parse_mode='Markdown'
            )
        
        # ==================== АПТЕЧКА В РЮКЗАК (НОВОЕ!) ====================
        elif item == 'аптечка':
            # Проверяем, есть ли экипированный рюкзак
            backpack = get_backpack(user)
            if not backpack:
                await update.message.reply_text(
                    "❌ *У вас нет экипированного рюкзака!*\n\n"
                    "Сначала наденьте рюкзак: `/equip рюкзак backpack1/2/3`",
                    parse_mode='Markdown'
                )
                return
            
            backpack_data = BACKPACKS.get(backpack)
            if not backpack_data:
                await update.message.reply_text("❌ Ошибка: рюкзак не найден в конфигурации")
                return
            
            max_slots = backpack_data['medkit_slots']
            current = get_medkits_in_backpack(user)
            
            if current >= max_slots:
                await update.message.reply_text(f"❌ В рюкзаке уже {current}/{max_slots} аптечек! Максимум.", parse_mode='Markdown')
                return
            
            # Проверяем, сколько аптечек есть в инвентаре
            available = get_item_count(user, 'аптечка')
            if available < count:
                await update.message.reply_text(f"❌ У вас только {available} аптечек в инвентаре!")
                return
            
            # Сколько можно положить
            can_add = min(count, max_slots - current)
            if can_add < count:
                await update.message.reply_text(f"❌ В рюкзак помещается только {can_add} аптечек (свободно {max_slots - current}/{max_slots})", parse_mode='Markdown')
                return
            
            # Перекладываем аптечки
            remove_item_from_inventory(user, 'аптечка', can_add)
            add_medkits_to_backpack(user, can_add)
            session.commit()
            
            log_user_action(
                user.user_id, user.username, 'use_medkit_to_backpack',
                item=f"{can_add} шт"
            )
            
            await update.message.reply_text(
                f"💊 *Аптечки положены в рюкзак!*\n\n"
                f"📦 Положили: {can_add} шт\n"
                f"🎒 Теперь в рюкзаке: {current + can_add}/{max_slots}\n\n"
                f"💡 Аптечки в рюкзаке спасут вас от смерти в метро!",
                parse_mode='Markdown'
            )
        
        else:
            await update.message.reply_text("❌ Доступно: энергетик, редуктор, аптечка")
    
    except Exception as e:
        logger.error(f"Error in use_item: {e}")
        session.rollback()
        await update.message.reply_text("❌ Ошибка")
    finally:
        session.close()


# ==================== КАЗИНО ====================

async def casino(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Казино с настраиваемыми шансами"""
    if not context.args:
        await update.message.reply_text(f"🎰 /casino [сумма]\n💰 Ставка от {CASINO_MIN_BET} до {CASINO_MAX_BET} RC")
        return
    
    try:
        bet = int(context.args[0])
        if bet < CASINO_MIN_BET or bet > CASINO_MAX_BET:
            await update.message.reply_text(f"❌ Ставка от {CASINO_MIN_BET} до {CASINO_MAX_BET} RC")
            return
    except ValueError:
        await update.message.reply_text("❌ Введите число")
        return
    
    session = Session()
    try:
        user = session.query(User).filter_by(user_id=update.effective_user.id).first()
        if not user:
            await update.message.reply_text("❌ /start")
            return
        if user.radcoins < bet:
            await update.message.reply_text(f"❌ Не хватает! У вас {user.radcoins:.0f} RC")
            return
        
        chance = user.casino_chance if user.casino_chance is not None else CASINO_PUBLIC_CHANCE
        mult = user.casino_cash_mult if user.casino_cash_mult is not None else CASINO_PUBLIC_CASH_MULT
        
        user.radcoins -= bet
        
        if random.random() < chance / 100:
            win = bet * mult
            user.radcoins += win
            session.commit()
            
            log_user_action(
                user.user_id, user.username, 'casino',
                amount_rc=win
            )
            
            await update.message.reply_text(
                f"🎰 *ДЖЕКПОТ!*\n\n"
                f"💰 +{win} RC!\n"
                f"🎲 Шанс: {chance}%\n"
                f"✨ Множитель: x{mult}\n"
                f"📊 Баланс: {user.radcoins:.0f} RC",
                parse_mode='Markdown'
            )
        else:
            session.commit()
            
            log_user_action(
                user.user_id, user.username, 'casino',
                amount_rc=-bet
            )
            
            await update.message.reply_text(
                f"💀 *Проигрыш!*\n\n"
                f"📉 -{bet} RC\n"
                f"🎲 Шанс: {chance}%\n"
                f"📊 Баланс: {user.radcoins:.0f} RC",
                parse_mode='Markdown'
            )
    except Exception as e:
        logger.error(f"Error in casino: {e}")
        session.rollback()
        await update.message.reply_text("❌ Ошибка")
    finally:
        session.close()


# ==================== ОБМЕН ====================

async def exchange(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обмен фрагментов на коины (лимит 1 000 000 RF)"""
    if not context.args:
        await update.message.reply_text("💱 /exchange [количество]\n📊 1 RF = 50 RC + бонусы\n⚠️ Лимит: 1 000 000 RF за раз")
        return
    
    try:
        amount = int(context.args[0])
        if amount <= 0:
            await update.message.reply_text("❌ Положительное число")
            return
        if amount > 1000000:
            await update.message.reply_text("❌ Лимит 1 000 000 RF за раз!")
            return
    except ValueError:
        await update.message.reply_text("❌ Введите число")
        return
    
    session = Session()
    try:
        user = session.query(User).filter_by(user_id=update.effective_user.id).first()
        if not user:
            await update.message.reply_text("❌ /start")
            return
        if user.radfragments < amount:
            await update.message.reply_text(f"❌ Не хватает! У вас {user.radfragments} RF")
            return
        
        if amount >= 100:
            coins = amount * 65 + 1500
        elif amount >= 50:
            coins = amount * 60 + 500
        elif amount >= 10:
            coins = amount * 55 + 50
        else:
            coins = amount * 50
        
        user.radfragments -= amount
        user.radcoins += coins
        
        session.commit()
        
        log_user_action(
            user.user_id, user.username, 'exchange',
            amount_rc=coins, amount_rf=-amount
        )
        
        await update.message.reply_text(
            f"💱 *Обмен*\n\n"
            f"📦 {amount} RF → {coins} RC\n"
            f"☢️ Баланс: {user.radcoins:.0f} RC",
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Error in exchange: {e}")
        session.rollback()
        await update.message.reply_text("❌ Ошибка")
    finally:
        session.close()


# ==================== КРАФТ ====================

async def craft(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Крафт предметов (включая новые)"""
    if not context.args:
        await update.message.reply_text(
            "🛠️ *Крафт предметов*\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "*💊 АПТЕЧКИ*\n"
            "• 💊 Аптечка (25%) — 2 RF\n\n"
            "*⚡ ЭНЕРГЕТИКИ*\n"
            "• ⚡ Strike — 5 RF + 50 RC\n"
            "• 🌀 Tornado — 25 RF + 250 RC\n"
            "• 💉 Adrenaline — 125 RF + 1250 RC\n"
            "• 🔴 RedBull — 250 RF + 2500 RC\n\n"
            "*⏱️ РЕДУКТОРЫ*\n"
            "• ⏱️ Базовый редуктор — 50 RF + 500 RC\n"
            "• ⚙️ Продвинутый редуктор — 175 RF + 1750 RC\n"
            "• 🌀 Квантовый редуктор — 375 RF + 3750 RC\n\n"
            "*🎒 РЮКЗАКИ*\n"
            "• 🎒 Маленький рюкзак — 250 RF + 2500 RC\n"
            "• 🎒 Тактический рюкзак — 750 RF + 7500 RC\n"
            "• 🎒 Профессиональный рюкзак — 2000 RF + 20000 RC\n\n"
            "*🎣 ОРУЖИЕ*\n"
            "• 🎣 Гарпун — 300 RF + 700 RC\n"
            "• 🔫 Винтовка — 250 RF + 3500 RC\n\n"
            "*🥇 БРОНЯ*\n"
            "• 🥈 Броня 2 — 250 RF + 2700 RC\n"
            "• 🥇 Броня 3 — 800 RF + 6700 RC\n\n"
            "📝 */craft [предмет]*",
            parse_mode='Markdown'
        )
        return
    
    item = context.args[0].lower()
    session = Session()
    try:
        user = session.query(User).filter_by(user_id=update.effective_user.id).first()
        if not user:
            await update.message.reply_text("❌ /start")
            return
        
        recipes = {
            'аптечка': {'rf': 2, 'rc': 0, 'level': 1},
            'гарпун': {'rf': 300, 'rc': 700, 'level': 1},
            'винтовка': {'rf': 250, 'rc': 3500, 'level': 4},
            'броня2': {'rf': 250, 'rc': 2700, 'level': 11},
            'броня3': {'rf': 800, 'rc': 6700, 'level': 21}
        }
        
        # Добавляем рецепты для энергетиков
        for key, data in ENERGY_DRINKS.items():
            recipes[key] = {
                'rf': int(data['price'] / 2),
                'rc': int(data['price'] / 2),
                'level': data['level_required']
            }
        
        # Добавляем рецепты для редукторов
        for key, data in REDUCERS.items():
            recipes[key] = {
                'rf': int(data['price'] / 2),
                'rc': int(data['price'] / 2),
                'level': data['level_required']
            }
        
        # Добавляем рецепты для рюкзаков (НОВЫЕ!)
        for key, data in BACKPACKS.items():
            recipes[key] = {
                'rf': int(data['price'] / 2),
                'rc': int(data['price'] / 2),
                'level': data['level_required']
            }
        
        if item not in recipes:
            await update.message.reply_text("❌ Неизвестный рецепт")
            return
        
        recipe = recipes[item]
        if user.level < recipe['level']:
            await update.message.reply_text(f"❌ Нужен {recipe['level']} уровень")
            return
        if user.radfragments < recipe['rf']:
            await update.message.reply_text(f"❌ Нужно {recipe['rf']} RF")
            return
        if user.radcoins < recipe['rc']:
            await update.message.reply_text(f"❌ Нужно {recipe['rc']} RC")
            return
        
        user.radfragments -= recipe['rf']
        user.radcoins -= recipe['rc']
        
        # Выдача предмета
        if item in ENERGY_DRINKS:
            add_item_to_inventory(user, f'энергетик_{item}', 1)
        elif item in REDUCERS:
            add_item_to_inventory(user, f'редуктор_{item}', 1)
        elif item in BACKPACKS:
            add_item_to_inventory(user, item, 1)
        elif item == 'гарпун':
            add_item_to_inventory(user, 'гарпун', 1)
        elif item == 'винтовка':
            add_item_to_inventory(user, 'винтовка', 1)
        elif item == 'броня2':
            add_item_to_inventory(user, 'броня2', 1)
        elif item == 'броня3':
            add_item_to_inventory(user, 'броня3', 1)
        else:
            add_item_to_inventory(user, 'аптечка', 1)
        
        session.commit()
        
        log_user_action(
            user.user_id, user.username, 'craft',
            amount_rc=-recipe['rc'], amount_rf=-recipe['rf'], item=item
        )
        
        item_names = {'аптечка': '💊 Аптечка'}
        for key, data in ENERGY_DRINKS.items():
            item_names[key] = data['name']
        for key, data in REDUCERS.items():
            item_names[key] = data['name']
        for key, data in BACKPACKS.items():
            item_names[key] = data['name']
        
        display_name = item_names.get(item, item)
        await update.message.reply_text(
            f"✅ *Создано: {display_name}*\n"
            f"💰 Потрачено: {recipe['rf']} RF + {recipe['rc']} RC",
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Error in craft: {e}")
        session.rollback()
        await update.message.reply_text("❌ Ошибка")
    finally:
        session.close()
