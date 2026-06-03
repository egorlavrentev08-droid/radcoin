# admin.py - Админ-панель
# Версия: 4.0.0 (ALPHA)

import json
import asyncio
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import ContextTypes

from config import logger, MAX_LEVEL, get_exp_for_level, ADMIN_CODE, SUPER_ADMIN_IDS, CASINO_PUBLIC_CHANCE, CASINO_PUBLIC_CASH_MULT, BACKPACKS
from core import send_to_private, is_admin
from database import Session, User, Clan, UserLog
from utils import add_item_to_inventory, remove_item_from_inventory, get_item_count, log_user_action, get_backpack, get_medkits_in_backpack


# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

def escape_markdown(text: str) -> str:
    """Экранирует спецсимволы для Markdown"""
    if not text:
        return "Неизвестно"
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


MAX_INVENTORY_STACK = 999


# ==================== ВЫДАЧА ПРАВ ====================

async def admin_giveme(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получить админ-права по коду"""
    if not context.args:
        await update.message.reply_text("❌ /givemeplsadmin [код]")
        return
    if context.args[0] == ADMIN_CODE:
        session = Session()
        try:
            user = session.query(User).filter_by(user_id=update.effective_user.id).first()
            if not user:
                user = User(user_id=update.effective_user.id, username=update.effective_user.username)
                session.add(user)
            user.is_admin = True
            user.is_blocked = False
            session.commit()
            await update.message.reply_text("✅ *Админ-права получены!*", parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Error in admin_giveme: {e}")
            await update.message.reply_text("❌ Ошибка")
        finally:
            session.close()
    else:
        await update.message.reply_text("❌ *Неверный код!*", parse_mode='Markdown')


# ==================== УПРАВЛЕНИЕ РЮКЗАКАМИ (НОВОЕ) ====================

async def admin_backpack(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выдать или забрать рюкзак у игрока"""
    if not await is_admin(update, context):
        await update.message.reply_text("❌ Нет прав!")
        return
    
    if len(context.args) < 4:
        await update.message.reply_text(
            "🎒 *Управление рюкзаками*\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "/backpack give @ник [тип] [кол-во]\n"
            "/backpack take @ник [тип] [кол-во]\n\n"
            "Типы рюкзаков:\n"
            "• backpack1 — Маленький (20% RC, 10% RF, 1 аптечка)\n"
            "• backpack2 — Тактический (30% RC, 15% RF, 2 аптечки)\n"
            "• backpack3 — Профессиональный (45% RC, 18% RF, 3 аптечки)\n\n"
            "Пример: `/backpack give @Player backpack1 1`",
            parse_mode='Markdown'
        )
        return
    
    action = context.args[0].lower()
    username = context.args[1].lstrip('@')
    backpack_type = context.args[2].lower()
    try:
        count = int(context.args[3])
        if count <= 0 or count > 10:
            await update.message.reply_text("❌ 1-10 штук")
            return
    except ValueError:
        await update.message.reply_text("❌ Введите число")
        return
    
    valid_backpacks = ['backpack1', 'backpack2', 'backpack3']
    if backpack_type not in valid_backpacks:
        await update.message.reply_text(f"❌ Доступны: {', '.join(valid_backpacks)}")
        return
    
    session = Session()
    try:
        user = session.query(User).filter_by(username=username).first()
        if not user:
            await update.message.reply_text(f"❌ @{username} не найден")
            return
        
        if action == 'give':
            current = get_item_count(user, backpack_type)
            if current + count > MAX_INVENTORY_STACK:
                await update.message.reply_text(f"❌ У игрока уже {current} шт, лимит {MAX_INVENTORY_STACK}")
                return
            add_item_to_inventory(user, backpack_type, count)
            session.commit()
            safe_log_user_action(
                user.user_id, user.username, 'admin_backpack_give',
                item=f"{backpack_type}x{count} от {update.effective_user.username}"
            )
            backpack_name = BACKPACKS.get(backpack_type, {}).get('name', backpack_type)
            await update.message.reply_text(f"✅ *Выдано {backpack_name} x{count} игроку @{username}*", parse_mode='Markdown')
            try:
                await context.bot.send_message(user.user_id, f"🎒 *Вам выдали {backpack_name} x{count}!*")
            except:
                pass
        
        elif action == 'take':
            available = get_item_count(user, backpack_type)
            if available < count:
                await update.message.reply_text(f"❌ У @{username} только {available} шт {backpack_type}")
                return
            
            # Проверяем, не экипирован ли такой рюкзак
            equipped = get_backpack(user)
            if equipped == backpack_type:
                await update.message.reply_text(f"❌ Рюкзак экипирован! Сначала снимите командой /equip рюкзак 0")
                return
            
            remove_item_from_inventory(user, backpack_type, count)
            session.commit()
            safe_log_user_action(
                user.user_id, user.username, 'admin_backpack_take',
                item=f"{backpack_type}x{count} от {update.effective_user.username}"
            )
            backpack_name = BACKPACKS.get(backpack_type, {}).get('name', backpack_type)
            await update.message.reply_text(f"✅ *Забрано {backpack_name} x{count} у @{username}*", parse_mode='Markdown')
        
        else:
            await update.message.reply_text("❌ Используйте give или take")
    
    except Exception as e:
        logger.error(f"Error in admin_backpack: {e}")
        session.rollback()
        await update.message.reply_text("❌ Ошибка")
    finally:
        session.close()


# ==================== ОЧИСТКА ЭФФЕКТОВ ИГРОКА (НОВОЕ) ====================

async def admin_effect_clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Очистить активные эффекты у игрока"""
    if not await is_admin(update, context):
        await update.message.reply_text("❌ Нет прав!")
        return
    
    if len(context.args) < 1:
        await update.message.reply_text("❌ /effect_clear @ник")
        return
    
    username = context.args[0].lstrip('@')
    session = Session()
    try:
        user = session.query(User).filter_by(username=username).first()
        if not user:
            await update.message.reply_text(f"❌ @{username} не найден")
            return
        
        # Сохраняем инфу о том, что было
        had_energy = user.energy_drink_until and user.energy_drink_until > datetime.now()
        had_reducer = user.cooldown_reducer_until and user.cooldown_reducer_until > datetime.now()
        
        user.energy_drink_until = None
        user.energy_drink_stacks = 0
        user.cooldown_reducer_until = None
        user.reducer_stacks = 0
        
        session.commit()
        
        safe_log_user_action(
            user.user_id, user.username, 'admin_effect_clear',
            item=f"энергетик:{had_energy}, редуктор:{had_reducer} от {update.effective_user.username}"
        )
        
        msg = f"✅ *Эффекты @{username} очищены!*\n"
        if had_energy:
            msg += "⚡ Энергетик был активен — удалён\n"
        if had_reducer:
            msg += "⏱️ Редуктор был активен — удалён\n"
        if not had_energy and not had_reducer:
            msg += "❌ Активных эффектов не было\n"
        
        await update.message.reply_text(msg, parse_mode='Markdown')
        
        try:
            await context.bot.send_message(
                user.user_id,
                "⚠️ *Администратор очистил все ваши активные эффекты!*"
            )
        except:
            pass
    
    except Exception as e:
        logger.error(f"Error in admin_effect_clear: {e}")
        session.rollback()
        await update.message.reply_text("❌ Ошибка")
    finally:
        session.close()


# ==================== УПРАВЛЕНИЕ РЕСУРСАМИ ====================

async def admin_give(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выдать ресурсы игроку"""
    if not await is_admin(update, context):
        await update.message.reply_text("❌ Нет прав!")
        return
    if len(context.args) < 3:
        await update.message.reply_text("❌ /give @ник [сумма] {RC,RF,RCr}")
        return
    username = context.args[0].lstrip('@')
    try:
        amount = int(context.args[1])
        if amount <= 0:
            await update.message.reply_text("❌ Положительная сумма")
            return
    except ValueError:
        await update.message.reply_text("❌ Введите число")
        return
    resource = context.args[2].upper()
    session = Session()
    try:
        user = session.query(User).filter_by(username=username).first()
        if not user:
            await update.message.reply_text("❌ Пользователь не найден")
            return
        
        if resource == 'RC':
            user.radcoins += amount
            safe_log_user_action(
                user.user_id, user.username, 'admin_give',
                amount_rc=amount, item=f"{resource} от {update.effective_user.username}"
            )
        elif resource == 'RF':
            user.radfragments += amount
            safe_log_user_action(
                user.user_id, user.username, 'admin_give',
                amount_rf=amount, item=f"{resource} от {update.effective_user.username}"
            )
        elif resource == 'RCR':
            if user.clan_id:
                clan = session.query(Clan).filter_by(id=user.clan_id).first()
                if clan:
                    clan.treasury_crystals += amount
                    safe_log_user_action(
                        user.user_id, user.username, 'admin_give',
                        amount_crystals=amount, item=f"{resource} в казну клана {clan.name} от {update.effective_user.username}"
                    )
                    await update.message.reply_text(f"✅ *Выдано {amount} {resource} в казну клана {clan.name}!*", parse_mode='Markdown')
                    session.commit()
                    try:
                        await context.bot.send_message(user.user_id, f"💰 *Вам выдали {amount} {resource} в казну клана!*")
                    except:
                        pass
                    session.close()
                    return
            user.radcrystals += amount
            safe_log_user_action(
                user.user_id, user.username, 'admin_give',
                amount_crystals=amount, item=f"{resource} лично от {update.effective_user.username}"
            )
            await update.message.reply_text(f"✅ *Выдано {amount} {resource} лично @{username}*", parse_mode='Markdown')
            try:
                await context.bot.send_message(user.user_id, f"💰 *Вам выдали {amount} {resource}!*")
            except:
                pass
            session.commit()
            session.close()
            return
        else:
            await update.message.reply_text("❌ RC, RF или RCr")
            session.close()
            return
        
        session.commit()
        await update.message.reply_text(f"✅ *Выдано {amount} {resource} @{username}*", parse_mode='Markdown')
        try:
            await context.bot.send_message(user.user_id, f"💰 *Вам выдали {amount} {resource}!*")
        except:
            pass
    except Exception as e:
        logger.error(f"Error in admin_give: {e}")
        session.rollback()
        await update.message.reply_text("❌ Ошибка")
    finally:
        session.close()


async def admin_take(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Забрать ресурсы у игрока"""
    if not await is_admin(update, context):
        await update.message.reply_text("❌ Нет прав!")
        return
    if len(context.args) < 3:
        await update.message.reply_text("❌ /take @ник [сумма] {RC,RF,RCr}")
        return
    username = context.args[0].lstrip('@')
    try:
        amount = int(context.args[1])
        if amount <= 0:
            await update.message.reply_text("❌ Положительная сумма")
            return
    except ValueError:
        await update.message.reply_text("❌ Введите число")
        return
    resource = context.args[2].upper()
    session = Session()
    try:
        user = session.query(User).filter_by(username=username).first()
        if not user:
            await update.message.reply_text("❌ Пользователь не найден")
            return
        
        if user.radcoins is None:
            user.radcoins = 0
        if user.radfragments is None:
            user.radfragments = 0
        if user.radcrystals is None:
            user.radcrystals = 0
        
        if resource == 'RC':
            if user.radcoins < amount:
                await update.message.reply_text(f"❌ У @{username} {user.radcoins:.0f} RC")
                return
            user.radcoins -= amount
            safe_log_user_action(
                user.user_id, user.username, 'admin_take',
                amount_rc=-amount, item=f"{resource} от {update.effective_user.username}"
            )
        elif resource == 'RF':
            if user.radfragments < amount:
                await update.message.reply_text(f"❌ У @{username} {user.radfragments} RF")
                return
            user.radfragments -= amount
            safe_log_user_action(
                user.user_id, user.username, 'admin_take',
                amount_rf=-amount, item=f"{resource} от {update.effective_user.username}"
            )
        elif resource == 'RCR':
            if user.radcrystals < amount:
                await update.message.reply_text(f"❌ У @{username} {user.radcrystals} RCr")
                return
            user.radcrystals -= amount
            safe_log_user_action(
                user.user_id, user.username, 'admin_take',
                amount_crystals=-amount, item=f"{resource} от {update.effective_user.username}"
            )
        else:
            await update.message.reply_text("❌ RC, RF или RCr")
            return
        session.commit()
        await update.message.reply_text(f"✅ *Забрано {amount} {resource} у @{username}*", parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error in admin_take: {e}")
        session.rollback()
        await update.message.reply_text("❌ Ошибка")
    finally:
        session.close()


async def admin_setlevel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Установить уровень игроку"""
    if not await is_admin(update, context):
        await update.message.reply_text("❌ Нет прав!")
        return
    if len(context.args) < 2:
        await update.message.reply_text("❌ /setlevel @ник [уровень]")
        return
    username = context.args[0].lstrip('@')
    try:
        level = int(context.args[1])
    except ValueError:
        await update.message.reply_text("❌ Введите число")
        return
    if level < 1 or level > MAX_LEVEL:
        await update.message.reply_text(f"❌ 1-{MAX_LEVEL}")
        return
    session = Session()
    try:
        user = session.query(User).filter_by(username=username).first()
        if not user:
            await update.message.reply_text("❌ Пользователь не найден")
            return
        old = user.level
        user.level = level
        user.experience = get_exp_for_level(level)
        session.commit()
        
        safe_log_user_action(
            user.user_id, user.username, 'admin_setlevel',
            item=f"{old} → {level} от {update.effective_user.username}"
        )
        
        await update.message.reply_text(f"📈 *@{username}: {old} → {level}*", parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error in admin_setlevel: {e}")
        session.rollback()
        await update.message.reply_text("❌ Ошибка")
    finally:
        session.close()


# ==================== УПРАВЛЕНИЕ КУЛДАУНАМИ ====================

async def admin_cd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Установить кулдаун сбора"""
    if not await is_admin(update, context):
        await update.message.reply_text("❌ Нет прав!")
        return
    if len(context.args) < 2:
        await update.message.reply_text("❌ /cd @ник [минуты] (0=сброс)")
        return
    username = context.args[0].lstrip('@')
    try:
        minutes = int(context.args[1])
        if minutes < 0:
            await update.message.reply_text("❌ Неотрицательное число")
            return
    except ValueError:
        await update.message.reply_text("❌ Введите число")
        return
    session = Session()
    try:
        user = session.query(User).filter_by(username=username).first()
        if not user:
            await update.message.reply_text("❌ Пользователь не найден")
            return
        if minutes == 0:
            user.next_collection_time = None
            await update.message.reply_text(f"✅ *Кулдаун @{username} сброшен*", parse_mode='Markdown')
        else:
            user.next_collection_time = datetime.now() + timedelta(minutes=minutes)
            await update.message.reply_text(f"⏰ *Кулдаун @{username} на {minutes} мин*", parse_mode='Markdown')
        session.commit()
    except Exception as e:
        logger.error(f"Error in admin_cd: {e}")
        session.rollback()
        await update.message.reply_text("❌ Ошибка")
    finally:
        session.close()


async def admin_resethunt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сбросить кулдаун охоты"""
    if not await is_admin(update, context):
        await update.message.reply_text("❌ Нет прав!")
        return
    if len(context.args) < 1:
        await update.message.reply_text("❌ /resethunt @ник")
        return
    username = context.args[0].lstrip('@')
    session = Session()
    try:
        user = session.query(User).filter_by(username=username).first()
        if not user:
            await update.message.reply_text("❌ Пользователь не найден")
            return
        user.last_hunt = None
        session.commit()
        await update.message.reply_text(f"✅ *Кулдаун охоты @{username} сброшен*", parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error in admin_resethunt: {e}")
        session.rollback()
        await update.message.reply_text("❌ Ошибка")
    finally:
        session.close()


# ==================== УПРАВЛЕНИЕ ПРЕДМЕТАМИ ====================

async def admin_item(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выдать или забрать предмет"""
    if not await is_admin(update, context):
        await update.message.reply_text("❌ Нет прав!")
        return
    
    if len(context.args) < 4:
        await update.message.reply_text(
            "📦 *Выдача предметов*\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "/item give @ник [предмет] [кол-во]\n"
            "/item take @ник [предмет] [кол-во]\n\n"
            "Доступные предметы:\n"
            "• Броня: броня1-5\n"
            "• Оружие: ружье, гарпун, винтовка, гаусс\n"
            "• Аптечка\n"
            "• Энергетики: strike, tornado, adrenaline, redbull\n"
            "• Редукторы: basic, advanced, quantum\n"
            "• Рюкзаки: backpack1, backpack2, backpack3\n"
            "• Металлоискатель: metal_detector\n\n"
            "Пример: `/item give @Player strike 10`",
            parse_mode='Markdown'
        )
        return
    
    action = context.args[0].lower()
    username = context.args[1].lstrip('@')
    item = context.args[2].lower()
    try:
        count = int(context.args[3])
        if count <= 0:
            await update.message.reply_text("❌ Положительное число")
            return
    except ValueError:
        await update.message.reply_text("❌ Введите число")
        return
    
    # Список всех предметов
    old_items = ['броня1', 'броня2', 'броня3', 'броня4', 'броня5',
                 'ружье', 'гарпун', 'винтовка', 'гаусс', 'аптечка']
    
    # Энергетики
    new_energies = ['strike', 'tornado', 'adrenaline', 'redbull']
    
    # Редукторы
    new_reducers = ['basic', 'advanced', 'quantum']
    
    # Рюкзаки (НОВЫЕ)
    backpacks = ['backpack1', 'backpack2', 'backpack3']
    
    # Металлоискатель (НОВЫЙ)
    metal_detector = ['metal_detector']
    
    valid_items = old_items + new_energies + new_reducers + backpacks + metal_detector
    
    if item not in valid_items:
        await update.message.reply_text(f"❌ Неизвестный предмет. Доступны: {', '.join(valid_items[:20])}...")
        return
    
    session = Session()
    try:
        user = session.query(User).filter_by(username=username).first()
        if not user:
            await update.message.reply_text(f"❌ @{username} не найден")
            return
        
        if item in new_energies:
            item_name = f'энергетик_{item}'
        elif item in new_reducers:
            item_name = f'редуктор_{item}'
        else:
            item_name = item
        
        if action == 'give':
            current = get_item_count(user, item_name)
            if current + count > MAX_INVENTORY_STACK:
                await update.message.reply_text(f"❌ У игрока уже {current} шт {item}, лимит {MAX_INVENTORY_STACK}")
                return
            add_item_to_inventory(user, item_name, count)
            session.commit()
            safe_log_user_action(
                user.user_id, user.username, 'admin_item_give',
                item=f"{item_name}x{count} от {update.effective_user.username}"
            )
            await update.message.reply_text(f"✅ *Выдано {item} x{count} игроку @{username}*", parse_mode='Markdown')
            try:
                await context.bot.send_message(user.user_id, f"📦 *Вам выдали {item} x{count}!*")
            except:
                pass
        
        elif action == 'take':
            available = get_item_count(user, item_name)
            if available < count:
                await update.message.reply_text(f"❌ У @{username} только {available} шт {item}")
                return
            remove_item_from_inventory(user, item_name, count)
            session.commit()
            safe_log_user_action(
                user.user_id, user.username, 'admin_item_take',
                item=f"{item_name}x{count} от {update.effective_user.username}"
            )
            await update.message.reply_text(f"✅ *Забрано {item} x{count} у @{username}*", parse_mode='Markdown')
        
        else:
            await update.message.reply_text("❌ Используйте give или take")
    
    except Exception as e:
        logger.error(f"Error in admin_item: {e}")
        session.rollback()
        await update.message.reply_text("❌ Ошибка")
    finally:
        session.close()


# ==================== УПРАВЛЕНИЕ ПИТОМЦАМИ ====================

async def admin_pets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Управление питомцами"""
    if not await is_admin(update, context):
        await update.message.reply_text("❌ Нет прав!")
        return
    if len(context.args) < 3:
        await update.message.reply_text("❌ /pets give/take @ник [питомец]")
        return
    action = context.args[0].lower()
    username = context.args[1].lstrip('@')
    session = Session()
    try:
        user = session.query(User).filter_by(username=username).first()
        if not user:
            await update.message.reply_text(f"❌ @{username} не найден")
            return
        valid_pets = ['овчарка', 'волк', 'рысь', 'пума', 'попугай', 'кайот']
        
        if action == 'give':
            pet_name = context.args[2].lower()
            if pet_name not in valid_pets:
                await update.message.reply_text(f"❌ Доступны: {', '.join(valid_pets)}")
                return
            user.pet = pet_name
            session.commit()
            safe_log_user_action(
                user.user_id, user.username, 'admin_pet_give',
                item=f"{pet_name} от {update.effective_user.username}"
            )
            await update.message.reply_text(f"🐾 *Выдан питомец {pet_name} @{username}*", parse_mode='Markdown')
            try:
                await context.bot.send_message(user.user_id, f"🐾 *Вам выдали питомца {pet_name}!*")
            except:
                pass
        elif action == 'take':
            if not user.pet:
                await update.message.reply_text(f"❌ У @{username} нет питомца")
                return
            user.pet = None
            session.commit()
            safe_log_user_action(
                user.user_id, user.username, 'admin_pet_take',
                item=f"удалён питомец от {update.effective_user.username}"
            )
            await update.message.reply_text(f"🐾 *Забран питомец у @{username}*", parse_mode='Markdown')
        else:
            await update.message.reply_text("❌ give или take")
    except Exception as e:
        logger.error(f"Error in admin_pets: {e}")
        session.rollback()
        await update.message.reply_text("❌ Ошибка")
    finally:
        session.close()


# ==================== УПРАВЛЕНИЕ АДМИНАМИ ====================

async def admin_manage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Управление администраторами (только главный админ)"""
    if update.effective_user.id not in SUPER_ADMIN_IDS:
        await update.message.reply_text("❌ Только главный администратор!")
        return
    if len(context.args) < 2:
        await update.message.reply_text(
            "👑 *Управление админами*\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "/admin add @ник — добавить админа\n"
            "/admin remove @ник — удалить админа\n"
            "/admin block @ник — заблокировать\n"
            "/admin unblock @ник — разблокировать\n"
            "/admin list — список админов",
            parse_mode='Markdown'
        )
        return
    action = context.args[0].lower()
    username = context.args[1].lstrip('@')
    session = Session()
    try:
        user = session.query(User).filter_by(username=username).first()
        if not user:
            await update.message.reply_text(f"❌ @{username} не найден")
            return
        if action == 'add':
            if user.is_admin:
                await update.message.reply_text("❌ Уже админ")
                return
            user.is_admin = True
            user.is_blocked = False
            session.commit()
            safe_log_user_action(
                user.user_id, user.username, 'admin_add',
                item=f"добавлен админом {update.effective_user.username}"
            )
            await update.message.reply_text(f"✅ *@{username} добавлен в админы*", parse_mode='Markdown')
            try:
                await context.bot.send_message(user.user_id, "👑 *Вы назначены администратором Пустоши!*")
            except:
                pass
        elif action == 'remove':
            if not user.is_admin:
                await update.message.reply_text("❌ Не админ")
                return
            user.is_admin = False
            user.is_blocked = False
            session.commit()
            safe_log_user_action(
                user.user_id, user.username, 'admin_remove',
                item=f"удалён админом {update.effective_user.username}"
            )
            await update.message.reply_text(f"✅ *@{username} удалён из админов*", parse_mode='Markdown')
        elif action == 'block':
            if not user.is_admin:
                await update.message.reply_text("❌ Не админ")
                return
            if user.user_id in SUPER_ADMIN_IDS:
                await update.message.reply_text("❌ Нельзя заблокировать главного админа")
                return
            user.is_blocked = True
            session.commit()
            safe_log_user_action(
                user.user_id, user.username, 'admin_block',
                item=f"заблокирован админом {update.effective_user.username}"
            )
            await update.message.reply_text(f"✅ *@{username} заблокирован*", parse_mode='Markdown')
        elif action == 'unblock':
            if not user.is_admin:
                await update.message.reply_text("❌ Не админ")
                return
            user.is_blocked = False
            session.commit()
            safe_log_user_action(
                user.user_id, user.username, 'admin_unblock',
                item=f"разблокирован админом {update.effective_user.username}"
            )
            await update.message.reply_text(f"✅ *@{username} разблокирован*", parse_mode='Markdown')
        elif action == 'list':
            admins = session.query(User).filter(User.is_admin == True).all()
            if not admins:
                await update.message.reply_text("📋 *Нет админов*", parse_mode='Markdown')
                return
            text = "👑 *Список администраторов*\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            for i, a in enumerate(admins, 1):
                status = "🔴" if a.is_blocked else "🟢"
                main = " (ГЛАВНЫЙ)" if a.user_id in SUPER_ADMIN_IDS else ""
                safe_name = escape_markdown(a.username or f"ID:{a.user_id}")
                text += f"{i}. {status} *{safe_name}*{main}\n"
            await update.message.reply_text(text, parse_mode='Markdown')
        else:
            await update.message.reply_text("❌ add/remove/block/unblock/list")
    except Exception as e:
        logger.error(f"Error in admin_manage: {e}")
        session.rollback()
        await update.message.reply_text("❌ Ошибка")
    finally:
        session.close()


async def admins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Список администраторов (для всех)"""
    session = Session()
    try:
        admins_list = session.query(User).filter(User.is_admin == True).all()
        if not admins_list:
            await update.message.reply_text("📋 *Нет администраторов*", parse_mode='Markdown')
            return
        text = "👑 *Администраторы Пустоши*\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        for i, a in enumerate(admins_list, 1):
            status = "🔴" if a.is_blocked else "🟢"
            main = " (ГЛАВНЫЙ)" if a.user_id in SUPER_ADMIN_IDS else ""
            safe_name = escape_markdown(a.username or f"ID:{a.user_id}")
            text += f"{i}. {status} *{safe_name}*{main}\n"
        await update.message.reply_text(text, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error in admins: {e}")
        await update.message.reply_text("❌ Ошибка")
    finally:
        session.close()


# ==================== УПРАВЛЕНИЕ КЛАССАМИ ====================

async def admin_classes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сменить класс игроку (админ)"""
    if not await is_admin(update, context):
        await update.message.reply_text("❌ Нет прав!")
        return
    if len(context.args) < 3 or context.args[0].lower() != 'set':
        await update.message.reply_text(
            "👑 *Смена класса (админ)*\n\n"
            "/classes set @ник [класс]\n\n"
            "Доступные классы:\n"
            "• сталкер — базовый\n"
            "• военный — +30% опыт, +20% RC, -30% RF\n"
            "• бандит — +40% RF, +15% RC, -25% опыт\n"
            "• ученый — +50% опыт, +25% RF, -20% RC",
            parse_mode='Markdown'
        )
        return
    username = context.args[1].lstrip('@')
    class_name = context.args[2].lower()
    valid_classes = {'сталкер': 'stalker', 'военный': 'military', 'бандит': 'bandit', 'ученый': 'scientist'}
    if class_name not in valid_classes:
        await update.message.reply_text("❌ Доступные классы: сталкер, военный, бандит, ученый")
        return
    session = Session()
    try:
        user = session.query(User).filter_by(username=username).first()
        if not user:
            await update.message.reply_text(f"❌ @{username} не найден")
            return
        old_class = user.user_class if hasattr(user, 'user_class') else 'stalker'
        user.user_class = valid_classes[class_name]
        user.last_free_class_change = datetime.now()
        session.commit()
        
        safe_log_user_action(
            user.user_id, user.username, 'admin_class_change',
            item=f"{old_class} → {class_name} от {update.effective_user.username}"
        )
        
        class_emoji = {'stalker': '🟢', 'military': '🔫', 'bandit': '🗡️', 'scientist': '🔬'}
        await update.message.reply_text(
            f"✅ *Класс @{username} изменён!*\n\n"
            f"🎭 {class_emoji.get(old_class, '🟢')} {old_class} → {class_emoji.get(valid_classes[class_name], '🟢')} {class_name}",
            parse_mode='Markdown'
        )
        try:
            await context.bot.send_message(
                user.user_id,
                f"👑 *Администратор изменил ваш класс на {class_name}!*"
            )
        except:
            pass
    except Exception as e:
        logger.error(f"Error in admin_classes: {e}")
        session.rollback()
        await update.message.reply_text("❌ Ошибка")
    finally:
        session.close()


# ==================== УПРАВЛЕНИЕ СУНДУКАМИ ====================

async def gchest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выдать сундуки игроку"""
    if not await is_admin(update, context):
        await update.message.reply_text("❌ Нет прав!")
        return
    if len(context.args) < 2:
        await update.message.reply_text("❌ /gchest @ник [тип] [кол-во]\n\nТипы: common, rare, epic, mythic, legendary")
        return
    username = context.args[0].lstrip('@')
    chest_type = context.args[1].lower()
    count = 1
    if len(context.args) > 2:
        try:
            count = int(context.args[2])
            if count <= 0 or count > 100:
                await update.message.reply_text("❌ 1-100")
                return
        except ValueError:
            await update.message.reply_text("❌ Введите число")
            return
    session = Session()
    try:
        user = session.query(User).filter_by(username=username).first()
        if not user:
            await update.message.reply_text(f"❌ @{username} не найден")
            return
        emoji = ""
        if chest_type == 'common':
            user.chest_common += count
            emoji = "🟢"
        elif chest_type == 'rare':
            user.chest_rare += count
            emoji = "🔵"
        elif chest_type == 'epic':
            user.chest_epic += count
            emoji = "🟣"
        elif chest_type == 'mythic':
            user.chest_mythic += count
            emoji = "🟡"
        elif chest_type == 'legendary':
            user.chest_legendary += count
            emoji = "🟠"
        else:
            await update.message.reply_text("❌ Тип: common, rare, epic, mythic, legendary")
            return
        session.commit()
        
        safe_log_user_action(
            user.user_id, user.username, 'admin_gchest',
            item=f"{count}x{chest_type} от {update.effective_user.username}"
        )
        
        await update.message.reply_text(f"✅ *Выдано {count} {emoji} {chest_type} сундуков @{username}*", parse_mode='Markdown')
        try:
            await context.bot.send_message(user.user_id, f"🎁 *Вам выдали {count} {chest_type} сундуков!*")
        except:
            pass
    except Exception as e:
        logger.error(f"Error in gchest: {e}")
        session.rollback()
        await update.message.reply_text("❌ Ошибка")
    finally:
        session.close()


# ==================== РАССЫЛКИ ====================

async def call(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Массовая рассылка всем игрокам с прогрессом"""
    if not await is_admin(update, context):
        await update.message.reply_text("❌ Нет прав!")
        return
    if not context.args:
        await update.message.reply_text("❌ /call [текст]")
        return
    
    status_msg = await update.message.reply_text("⏳ *Начинаю рассылку...*", parse_mode='Markdown')
    
    msg = ' '.join(context.args)
    admin_name = update.effective_user.first_name or "Администратор"
    admin_name = escape_markdown(admin_name)
    
    session = Session()
    try:
        users = session.query(User).all()
        sent = 0
        total = len(users)
        
        for i, u in enumerate(users):
            try:
                safe_msg = escape_markdown(msg)
                await context.bot.send_message(
                    u.user_id, 
                    f"📢 *Объявление от администратора*\n\n{safe_msg}\n\n👑 {admin_name}", 
                    parse_mode='Markdown'
                )
                sent += 1
            except Exception as e:
                logger.error(f"Не удалось отправить {u.user_id}: {e}")
            
            if (i + 1) % 10 == 0:
                try:
                    await status_msg.edit_text(f"⏳ *Рассылка:* {sent}/{total}...", parse_mode='Markdown')
                except:
                    pass
            
            await asyncio.sleep(0.3)
        
        await status_msg.edit_text(f"✅ *Рассылка завершена!*\n📨 Отправлено: {sent}/{total}", parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Error in call: {e}")
        await update.message.reply_text("❌ Ошибка")
    finally:
        session.close()


async def lscall(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Личная рассылка игроку"""
    if not await is_admin(update, context):
        await update.message.reply_text("❌ Нет прав!")
        return
    if len(context.args) < 2:
        await update.message.reply_text("❌ /lscall @ник [текст]")
        return
    username = context.args[0].lstrip('@')
    msg = ' '.join(context.args[1:])
    admin = update.effective_user.first_name or "Администратор"
    session = Session()
    try:
        user = session.query(User).filter_by(username=username).first()
        if not user:
            await update.message.reply_text(f"❌ @{username} не найден")
            return
        safe_msg = escape_markdown(msg)
        safe_admin = escape_markdown(admin)
        await context.bot.send_message(
            user.user_id, 
            f"📨 *Личное сообщение от администратора*\n\n{safe_msg}\n\n👑 {safe_admin}", 
            parse_mode='Markdown'
        )
        await update.message.reply_text(f"✅ *Сообщение отправлено @{username}*", parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error in lscall: {e}")
        await update.message.reply_text("❌ Ошибка")
    finally:
        session.close()


# ==================== УПРАВЛЕНИЕ ВИДИМОСТЬЮ В ТОПАХ ====================

async def admin_hide(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Скрыть/показать игрока в топах"""
    if not await is_admin(update, context):
        await update.message.reply_text("❌ Нет прав!")
        return
    if len(context.args) < 2:
        await update.message.reply_text("❌ /hide @ник — скрыть из топов\n/show @ник — показать")
        return
    action = context.args[0].lower()
    username = context.args[1].lstrip('@')
    session = Session()
    try:
        user = session.query(User).filter_by(username=username).first()
        if not user:
            await update.message.reply_text("❌ Пользователь не найден")
            return
        if action == 'hide':
            user.is_admin_visible = False
            session.commit()
            safe_log_user_action(
                user.user_id, user.username, 'admin_hide',
                item=f"скрыт из топов админом {update.effective_user.username}"
            )
            await update.message.reply_text(f"✅ *@{username} скрыт из топов*", parse_mode='Markdown')
        elif action == 'show':
            user.is_admin_visible = True
            session.commit()
            safe_log_user_action(
                user.user_id, user.username, 'admin_show',
                item=f"показан в топах админом {update.effective_user.username}"
            )
            await update.message.reply_text(f"✅ *@{username} виден в топах*", parse_mode='Markdown')
        else:
            await update.message.reply_text("❌ Используйте hide или show")
    except Exception as e:
        logger.error(f"Error in admin_hide: {e}")
        session.rollback()
        await update.message.reply_text("❌ Ошибка")
    finally:
        session.close()


# ==================== ТАБЛИЦА ЛИДЕРОВ ====================

async def top_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Таблица лидеров"""
    if not context.args:
        await update.message.reply_text(
            "🏆 *Таблица лидеров*\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "/top level — по уровню\n"
            "/top rc — по РадКоинами\n"
            "/top boss — по убитым Боссам\n"
            "/top hunt — по мутантам\n"
            "/top clan — по кланам",
            parse_mode='Markdown'
        )
        return
    cat = context.args[0].lower()
    session = Session()
    try:
        if cat == 'level':
            users = session.query(User).filter(User.is_admin_visible == True).order_by(User.level.desc()).limit(10).all()
            title = "🏆 *Топ-10 по уровню*"
            val = lambda u: u.level
        elif cat == 'rc':
            users = session.query(User).filter(User.is_admin_visible == True).order_by(User.radcoins.desc()).limit(10).all()
            title = "💰 *Топ-10 по РадКоинами*"
            val = lambda u: f"{u.radcoins:.0f}"
        elif cat == 'boss':
            users = session.query(User).filter(User.is_admin_visible == True).order_by(User.bosses_killed.desc()).limit(10).all()
            title = "👑 *Топ-10 по Боссам*"
            val = lambda u: u.bosses_killed
        elif cat == 'hunt':
            users = session.query(User).filter(User.is_admin_visible == True).order_by(User.mutants_killed.desc()).limit(10).all()
            title = "🧬 *Топ-10 по мутантам*"
            val = lambda u: u.mutants_killed
        elif cat == 'clan':
            clans = session.query(Clan).all()
            stats = [(c.name, session.query(User).filter_by(clan_id=c.id).count()) for c in clans]
            stats.sort(key=lambda x: x[1], reverse=True)
            text = "🏰 *Топ-10 кланов*\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            for i, (n, c) in enumerate(stats[:10], 1):
                medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
                safe_name = escape_markdown(n)
                text += f"{medal} *{safe_name}* — 👥 {c}\n"
            await update.message.reply_text(text, parse_mode='Markdown')
            return
        else:
            await update.message.reply_text("❌ Используйте: level, rc, boss, hunt, clan")
            return
        
        if not users:
            await update.message.reply_text("📋 *Нет игроков*", parse_mode='Markdown')
            return
        
        text = f"{title}\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        for i, u in enumerate(users, 1):
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            safe_name = escape_markdown(u.username or f"ID:{u.user_id}")
            text += f"{medal} *{safe_name}* — {val(u)}\n"
        await update.message.reply_text(text, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error in top: {e}")
        await update.message.reply_text("❌ Ошибка")
    finally:
        session.close()


# ==================== ФАЗЫ ПУСТОШИ ====================

async def admin_phase(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Смена фазы Пустоши"""
    if not await is_admin(update, context):
        await update.message.reply_text("❌ Нет прав!")
        return
    if not context.args:
        await update.message.reply_text("❌ /phase 1/2/3")
        return
    try:
        phase = int(context.args[0])
        if phase not in [1, 2, 3]:
            await update.message.reply_text("❌ 1, 2 или 3")
            return
        context.bot_data['phase'] = phase
        phases = {1: "🟢 Мирная", 2: "🟡 Опасная", 3: "🔴 Апокалиптическая"}
        await update.message.reply_text(f"🌍 *Фаза изменена на {phases[phase]}*", parse_mode='Markdown')
    except ValueError:
        await update.message.reply_text("❌ Введите число")


# ==================== НАСТРОЙКА КАЗИНО (ТОЛЬКО ГЛАВНЫЙ АДМИН) ====================

async def acasino(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Настройка казино (только главный админ)"""
    if update.effective_user.id not in SUPER_ADMIN_IDS:
        await update.message.reply_text("❌ Только главный администратор!")
        return
    
    if len(context.args) < 3:
        await update.message.reply_text(
            "🎰 *Настройка казино*\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "/acasino public chance [1-100] — публичный шанс\n"
            "/acasino public cash [1-1000] — публичный множитель\n"
            "/acasino private @username chance [1-100] — личный шанс\n"
            "/acasino private @username cash [1-1000] — личный множитель\n"
            "/acasino reset @username — сбросить личные настройки\n"
            "/acasino stats @username — посмотреть настройки",
            parse_mode='Markdown'
        )
        return
    
    action = context.args[0].lower()
    
    if action == 'public':
        if len(context.args) < 3:
            await update.message.reply_text("❌ /acasino public [chance/cash] [значение]")
            return
        setting = context.args[1].lower()
        try:
            value = int(context.args[2])
        except ValueError:
            await update.message.reply_text("❌ Введите число")
            return
        
        if setting == 'chance':
            if value < 1 or value > 100:
                await update.message.reply_text("❌ Шанс от 1 до 100")
                return
            context.bot_data['casino_public_chance'] = value
            await update.message.reply_text(f"✅ *Публичный шанс казино: {value}%*", parse_mode='Markdown')
        elif setting == 'cash':
            if value < 1 or value > 1000:
                await update.message.reply_text("❌ Множитель от 1 до 1000")
                return
            context.bot_data['casino_public_cash_mult'] = value
            await update.message.reply_text(f"✅ *Публичный множитель казино: x{value}*", parse_mode='Markdown')
        else:
            await update.message.reply_text("❌ chance или cash")
    
    elif action == 'private':
        if len(context.args) < 4:
            await update.message.reply_text("❌ /acasino private @username [chance/cash] [значение]")
            return
        username = context.args[1].lstrip('@')
        setting = context.args[2].lower()
        try:
            value = int(context.args[3])
        except ValueError:
            await update.message.reply_text("❌ Введите число")
            return
        
        session = Session()
        try:
            user = session.query(User).filter_by(username=username).first()
            if not user:
                await update.message.reply_text(f"❌ @{username} не найден")
                return
            
            if setting == 'chance':
                if value < 1 or value > 100:
                    await update.message.reply_text("❌ Шанс от 1 до 100")
                    return
                user.casino_chance = value
                session.commit()
                safe_log_user_action(
                    user.user_id, user.username, 'admin_casino_chance',
                    item=f"{value}% от {update.effective_user.username}"
                )
                await update.message.reply_text(f"✅ *Личный шанс @{username}: {value}%*", parse_mode='Markdown')
            elif setting == 'cash':
                if value < 1 or value > 1000:
                    await update.message.reply_text("❌ Множитель от 1 до 1000")
                    return
                user.casino_cash_mult = value
                session.commit()
                safe_log_user_action(
                    user.user_id, user.username, 'admin_casino_mult',
                    item=f"x{value} от {update.effective_user.username}"
                )
                await update.message.reply_text(f"✅ *Личный множитель @{username}: x{value}*", parse_mode='Markdown')
            else:
                await update.message.reply_text("❌ chance или cash")
        except Exception as e:
            logger.error(f"Error in acasino private: {e}")
            session.rollback()
            await update.message.reply_text("❌ Ошибка")
        finally:
            session.close()
    
    elif action == 'reset':
        if len(context.args) < 2:
            await update.message.reply_text("❌ /acasino reset @username")
            return
        username = context.args[1].lstrip('@')
        session = Session()
        try:
            user = session.query(User).filter_by(username=username).first()
            if not user:
                await update.message.reply_text(f"❌ @{username} не найден")
                return
            user.casino_chance = None
            user.casino_cash_mult = None
            session.commit()
            safe_log_user_action(
                user.user_id, user.username, 'admin_casino_reset',
                item=f"сброшены настройки админом {update.effective_user.username}"
            )
            await update.message.reply_text(f"✅ *Личные настройки казино @{username} сброшены*", parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Error in acasino reset: {e}")
            session.rollback()
            await update.message.reply_text("❌ Ошибка")
        finally:
            session.close()
    
    elif action == 'stats':
        if len(context.args) < 2:
            await update.message.reply_text("❌ /acasino stats @username")
            return
        username = context.args[1].lstrip('@')
        session = Session()
        try:
            user = session.query(User).filter_by(username=username).first()
            if not user:
                await update.message.reply_text(f"❌ @{username} не найден")
                return
            
            pub_chance = context.bot_data.get('casino_public_chance', CASINO_PUBLIC_CHANCE)
            pub_mult = context.bot_data.get('casino_public_cash_mult', CASINO_PUBLIC_CASH_MULT)
            priv_chance = user.casino_chance if user.casino_chance is not None else "не задан"
            priv_mult = user.casino_cash_mult if user.casino_cash_mult is not None else "не задан"
            
            text = (
                f"🎰 *Настройки казино @{username}*\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"📊 *Публичные:*\n"
                f"   • Шанс: {pub_chance}%\n"
                f"   • Множитель: x{pub_mult}\n\n"
                f"🔒 *Личные:*\n"
                f"   • Шанс: {priv_chance}\n"
                f"   • Множитель: {priv_mult}"
            )
            await update.message.reply_text(text, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Error in acasino stats: {e}")
            await update.message.reply_text("❌ Ошибка")
        finally:
            session.close()
    
    else:
        await update.message.reply_text("❌ Используйте: public, private, reset, stats")


# ==================== СОВЕТЫ ====================

async def advice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Советы Старого сталкера"""
    text = (
        "📖 *Советы Старого сталкера*\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Напиши `/advice` и слово:\n\n"
        "🎲 `сбор` — как добывать ресурсы\n"
        "🏹 `охота` — как охотиться на мутантов\n"
        "🛒 `магазин` — что и зачем покупать\n"
        "🛠️ `крафт` — что можно создать\n"
        "💱 `обмен` — как менять фрагменты\n"
        "🎰 `казино` — как испытать удачу\n"
        "🐾 `питомцы` — как найти друга\n"
        "🏰 `кланы` — как создать и развивать\n"
        "🌪️ `аномалии` — что случается в Пустоши\n"
        "🔔 `уведомления` — как не пропустить\n"
        "🎭 `классы` — система классов\n"
        "🗺️ `локации` — все локации\n"
        "🎁 `сундуки` — типы сундуков\n"
        "📦 `предметы` — описание всех предметов\n"
        "🎒 `рюкзаки` — бонусы и аптечки\n"
        "🚇 `метро` — хардкорное подземелье\n"
        "⚡ `эффекты` — энергетики и редукторы\n\n"
        "Пример: `/advice предметы`"
    )
    await send_to_private(update, context, text)


async def advice_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик советов"""
    if not context.args:
        await advice(update, context)
        return
    topic = context.args[0].lower()
    tips = {
        'сбор': "🎲 *СБОР РЕСУРСОВ*\n\n/collect — 30-120 мин. Находка: RC, опыт, RF, сундуки.",
        'охота': "🏹 *ОХОТА НА МУТАНТОВ*\n\n/hunt — раз в сутки. Шансы зависят от оружия. +Классовая война!",
        'магазин': "🛒 *МАГАЗИН ПУСТОШИ*\n\n/shop — все цены. /buy [товар] [кол-во]",
        'крафт': "🛠️ *КРАФТ ПРЕДМЕТОВ*\n\n/craft [предмет]. Аптечка — 2 RF",
        'обмен': "💱 *ОБМЕН ФРАГМЕНТОВ*\n\n/exchange [количество]. 1RF=50RC",
        'казино': "🎰 *КАЗИНО*\n\n/casino [сумма]. Ставка от 100 до 100000 RC",
        'питомцы': "🐾 *ПИТОМЦЫ*\n\nПри сборе 0.5% шанс встретить. /pet accept — приручить",
        'кланы': "🏰 *КЛАНЫ*\n\n/clan create [название] (2ур,1000RC)",
        'аномалии': "🌪️ *АНОМАЛИИ* (3 фаза)\n\nДобытчик(+30%RC), Ловец(риск 90%)",
        'уведомления': "🔔 *УВЕДОМЛЕНИЯ*\n\n/announce on — включить",
        'классы': "🎭 *КЛАССЫ*\n\n/class [сталкер/военный/бандит/ученый]",
        'локации': "🗺️ *ЛОКАЦИИ*\n\n/locate [normal/military/city/wasteland/lab/forest/market/metro]",
        'сундуки': "🎁 *СУНДУКИ*\n\n/chest open [common/rare/epic/mythic/legendary/all]",
        'рюкзаки': "🎒 *РЮКЗАКИ*\n\n/equip рюкзак [backpack1/2/3] — бонусы к сбору + хранение аптечек",
        'метро': "🚇 *МЕТРО*\n\n/metro — хардкорное подземелье (10+ уровень). Бой до 3 аптечек.",
        'эффекты': "⚡ *ЭФФЕКТЫ*\n\n/effect — показать активные эффекты\n/effect clear — очистить все",
        'предметы': "📦 *ПРЕДМЕТЫ*\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                   "*🛡️ БРОНЯ*\n"
                   "• броня1 (1000 RC) — +25% выживания\n"
                   "• броня2 (2500 RC) — +40% выживания (10 ур)\n"
                   "• броня3 (5000 RC) — +50% выживания\n"
                   "• броня4 (10000 RC) — +60% выживания (25 ур)\n"
                   "• броня5 (25000 RC) — +75% выживания (50 ур)\n\n"
                   "*⚔️ ОРУЖИЕ*\n"
                   "• ружьё (300 RC) — шансы 75/20/4/1%\n"
                   "• гарпун (500 RC) — шансы 70/20/9/1% (10 ур)\n"
                   "• винтовка (5000 RC) — шансы 50/30/15/5% (25 ур)\n"
                   "• гаусс (20000 RC) — шансы 40/25/20/15% (50 ур)\n\n"
                   "*💊 РАСХОДНИКИ*\n"
                   "• аптечка (125 RC) — +25% шанс выжить\n"
                   "• энергетик — 4 уровня (Strike/Tornado/Adrenaline/RedBull)\n"
                   "• редуктор — 3 уровня (Базовый/Продвинутый/Квантовый)\n\n"
                   "*🎒 РЮКЗАКИ*\n"
                   "• backpack1 (5000 RC) — +20% RC, +10% RF, 1 аптечка (10 ур)\n"
                   "• backpack2 (15000 RC) — +30% RC, +15% RF, 2 аптечки (25 ур)\n"
                   "• backpack3 (40000 RC) — +45% RC, +18% RF, 3 аптечки (50 ур)\n\n"
                   "*🔍 ПРОЧЕЕ*\n"
                   "• металлоискатель (10000 RC) — 10% шанс найти сундук\n\n"
                   "💡 Предметы можно купить в `/shop`, продать через `/sell`, экипировать через `/equip`",
    }
    await send_to_private(update, context, tips.get(topic, "❌ Неизвестный раздел. Используйте /advice"))


# ==================== СПИСОК ИГРОКОВ (АДМИН) ====================

async def admin_players(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Список всех игроков (админ)"""
    if not await is_admin(update, context):
        await update.message.reply_text("❌ Нет прав!")
        return
    session = Session()
    try:
        users = session.query(User).order_by(User.level.desc()).all()
        if not users:
            await update.message.reply_text("📋 *Нет игроков*", parse_mode='Markdown')
            return
        text = "👥 *Список игроков*\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        for i, u in enumerate(users, 1):
            safe_name = escape_markdown(u.username or f"ID:{u.user_id}")
            clan_name = "—"
            if u.clan_id:
                clan = session.query(Clan).filter_by(id=u.clan_id).first()
                if clan:
                    clan_name = escape_markdown(clan.name)
            text += f"{i}. *{safe_name}* — ур.{u.level}, RC:{u.radcoins:.0f}, 🏰{clan_name}\n"
            if len(text) > 3500:
                await update.message.reply_text(text, parse_mode='Markdown')
                text = ""
        if text:
            await update.message.reply_text(text, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error in admin_players: {e}")
        await update.message.reply_text("❌ Ошибка")
    finally:
        session.close()


# ==================== КОМАНДА /check ====================

async def check_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Проверка действий пользователя (админ)"""
    if not await is_admin(update, context):
        await update.message.reply_text("❌ Нет прав!")
        return
    
    if len(context.args) < 1:
        await update.message.reply_text(
            "🔍 *Команда /check*\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "/check @ник — последние 25 действий\n"
            "/check @ник rc — транзакции RC\n"
            "/check @ник rf — транзакции RF\n"
            "/check @ник crystals — транзакции кристаллов\n"
            "/check @ник factory — последние действия с бизнесом\n"
            "/check @ник shop — покупки в магазине\n"
            "/check @ник craft — крафт предметов\n"
            "/check @ник hunt — охота на мутантов\n"
            "/check @ник collect — сбор ресурсов\n"
            "/check @ник casino — казино\n"
            "/check @ник exchange — обмен RF на RC\n"
            "/check @ник metro — походы в метро",
            parse_mode='Markdown'
        )
        return
    
    username = context.args[0].lstrip('@')
    flag = context.args[1].lower() if len(context.args) > 1 else None
    
    session = Session()
    try:
        user = session.query(User).filter_by(username=username).first()
        if not user:
            await update.message.reply_text(f"❌ Пользователь @{username} не найден")
            return
        
        query = session.query(UserLog).filter_by(user_id=user.user_id)
        
        if flag == 'rc':
            query = query.filter(UserLog.amount_rc != 0)
        elif flag == 'rf':
            query = query.filter(UserLog.amount_rf != 0)
        elif flag == 'crystals':
            query = query.filter(UserLog.amount_crystals != 0)
        elif flag == 'factory':
            query = query.filter(UserLog.action == 'factory_money')
        elif flag == 'shop':
            query = query.filter(UserLog.action == 'buy')
        elif flag == 'craft':
            query = query.filter(UserLog.action == 'craft')
        elif flag == 'hunt':
            query = query.filter(UserLog.action == 'hunt')
        elif flag == 'collect':
            query = query.filter(UserLog.action == 'collect')
        elif flag == 'casino':
            query = query.filter(UserLog.action == 'casino')
        elif flag == 'exchange':
            query = query.filter(UserLog.action == 'exchange')
        elif flag == 'metro':
            query = query.filter(UserLog.action.like('metro%'))
        
        logs = query.order_by(UserLog.timestamp.desc()).limit(25).all()
        
        if not logs:
            await update.message.reply_text(f"📋 Нет действий для @{username}")
            return
        
        safe_username = escape_markdown(username)
        text = f"📜 *История @{safe_username}* (последние {len(logs)})\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        for log in logs:
            time_str = log.timestamp.strftime('%d.%m %H:%M:%S')
            if log.amount_rc != 0:
                sign = '+' if log.amount_rc > 0 else ''
                text += f"💰 [{time_str}] {log.action}: {sign}{log.amount_rc:.0f} RC\n"
            elif log.amount_rf != 0:
                sign = '+' if log.amount_rf > 0 else ''
                text += f"☣️ [{time_str}] {log.action}: {sign}{log.amount_rf} RF\n"
            elif log.amount_crystals != 0:
                sign = '+' if log.amount_crystals > 0 else ''
                text += f"💎 [{time_str}] {log.action}: {sign}{log.amount_crystals} кристаллов\n"
            elif log.item:
                safe_item = escape_markdown(log.item)
                text += f"📦 [{time_str}] {log.action}: {safe_item}\n"
            else:
                text += f"🔄 [{time_str}] {log.action}\n"
        
        await send_to_private(update, context, text)
    except Exception as e:
        logger.error(f"Error in check_user: {e}")
        await update.message.reply_text("❌ Ошибка")
    finally:
        session.close()


# ==================== РАСПРОДАЖИ ====================

async def sale(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Устроить распродажу в магазине (админ)"""
    if not await is_admin(update, context):
        await update.message.reply_text("❌ Нет прав!")
        return
    
    if not context.args:
        await update.message.reply_text(
            "🏷️ *Распродажа*\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "/sale [скидка%] [часы] — устроить распродажу\n"
            "/sale end — завершить распродажу\n\n"
            "Пример: `/sale 50 24` — скидка 50% на 24 часа",
            parse_mode='Markdown'
        )
        return
    
    if context.args[0].lower() == 'end':
        context.bot_data['sale_discount'] = 0
        context.bot_data['sale_until'] = None
        await update.message.reply_text("✅ *Распродажа завершена!* Цены вернулись к обычным.", parse_mode='Markdown')
        return
    
    try:
        discount = int(context.args[0])
        hours = int(context.args[1])
        
        if discount < 1 or discount > 90:
            await update.message.reply_text("❌ Скидка от 1% до 90%")
            return
        if hours < 1 or hours > 168:
            await update.message.reply_text("❌ Время от 1 до 168 часов")
            return
        
        context.bot_data['sale_discount'] = discount
        context.bot_data['sale_until'] = datetime.now() + timedelta(hours=hours)
        
        await update.message.reply_text(
            f"🏷️ *РАСПРОДАЖА!*\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🎉 Скидка {discount}% на ВСЕ товары!\n"
            f"⏰ Длительность: {hours} часов\n"
            f"📅 До: {(datetime.now() + timedelta(hours=hours)).strftime('%d.%m %H:%M')}\n\n"
            f"🛒 Торопитесь, предложение ограничено!",
            parse_mode='Markdown'
        )
    except (ValueError, IndexError):
        await update.message.reply_text("❌ Пример: `/sale 50 24`", parse_mode='Markdown')


# ==================== СБРОС ИГРОКА ====================

async def admin_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Полный сброс игрока (админ)"""
    if not await is_admin(update, context):
        await update.message.reply_text("❌ Нет прав!")
        return
    
    if len(context.args) < 1:
        await update.message.reply_text("❌ /reset @ник")
        return
    
    username = context.args[0].lstrip('@')
    session = Session()
    try:
        user = session.query(User).filter_by(username=username).first()
        if not user:
            await update.message.reply_text(f"❌ @{username} не найден")
            return
        
        log_user_id = user.user_id
        log_username = user.username
        
        # Сбрасываем всё
        user.radcoins = 0
        user.radfragments = 0
        user.radcrystals = 0
        user.level = 1
        user.experience = 0
        user.total_collects = 0
        user.total_rc_earned = 0
        user.best_collect = 0
        user.mutants_killed = 0
        user.mutants_lvl3 = 0
        user.bosses_killed = 0
        user.deaths = 0
        user.crit_collects = 0
        user.daily_streak = 0
        user.last_collect_date = None
        user.next_collection_time = None
        user.last_hunt = None
        user.cooldown_reducer_until = None
        user.energy_drink_until = None
        user.armor_type = None
        user.weapon = None
        user.medkits = 0
        user.pet = None
        user.achievements = '[]'
        user.total_purchases = 0
        user.notifications_enabled = False
        user.location = 'normal'
        user.user_class = 'stalker'
        user.last_free_class_change = None
        user.radio_active = False
        user.radio_code = None
        user.radio_banned = False
        user.inventory = '[]'
        user.equipped = '{}'
        user.chest_common = 0
        user.chest_rare = 0
        user.chest_epic = 0
        user.chest_mythic = 0
        user.chest_legendary = 0
        user.shop_purchases = '{}'
        user.last_shop_reset = None
        user.energy_drink_stacks = 0
        user.reducer_stacks = 0
        user.energy_drink_level = 'strike'
        user.reducer_level = 'basic'
        user.last_metal_detector = None
        user.last_metal_detector_duration = 3
        
        if user.clan_id:
            user.clan_id = None
        
        session.commit()
        
        safe_log_user_action(
            log_user_id, log_username, 'admin_reset',
            item=f"сброшен админом {update.effective_user.username}"
        )
        
        await update.message.reply_text(f"🔄 *@{username} сброшен!*", parse_mode='Markdown')
        
        try:
            await context.bot.send_message(
                user.user_id,
                "⚠️ *Ваш аккаунт был сброшен администратором!*\n\n"
                "Все ресурсы, уровень, инвентарь и прогресс обнулены.",
                parse_mode='Markdown'
            )
        except:
            pass
    except Exception as e:
        logger.error(f"Error in admin_reset: {e}")
        session.rollback()
        await update.message.reply_text("❌ Ошибка")
    finally:
        session.close()
