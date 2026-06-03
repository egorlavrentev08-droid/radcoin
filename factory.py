# factory.py - Фабрики (ресурсные точки)
# Версия: 4.0.0 (ALPHA)

import json
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import ContextTypes
from config import logger, FACTORIES
from core import send_to_private, is_admin
from database import Session, User
from utils import log_user_action


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


# ==================== ФАБРИКИ (РЕСУРСНЫЕ ТОЧКИ) ====================

async def factory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Управление фабриками"""
    if not context.args:
        text = "🏭 *Ресурсные точки*\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        for key, f in FACTORIES.items():
            text += f"{f['name']}\n"
            text += f"   • Мест: {f['slots']}\n"
            text += f"   • Цена: {f['price']} RC (3 суток)\n"
            text += f"   • Доход: {f['income']} {f['income_type']}/час\n"
            if f['level'] > 1:
                text += f"   • Требуется: {f['level']} уровень\n"
            text += "\n"
        text += "📝 Команды:\n"
        text += "/factory list — список точек\n"
        text += "/factory buy [название] — купить точку\n"
        text += "/factory money — забрать доход\n"
        text += "/factory my — мои точки\n"
        text += "/factory leave [название] — освободить точку"
        await update.message.reply_text(text, parse_mode='Markdown')
        return
    
    action = context.args[0].lower()
    
    if action == 'list':
        await factory_list(update, context)
    elif action == 'buy':
        if len(context.args) < 2:
            await update.message.reply_text("❌ /factory buy [название]")
            return
        await factory_buy(update, context, ' '.join(context.args[1:]).lower())
    elif action == 'money':
        await factory_money(update, context)
    elif action == 'my':
        await factory_my(update, context)
    elif action == 'leave':
        if len(context.args) < 2:
            await update.message.reply_text("❌ /factory leave [название]")
            return
        await factory_leave(update, context, ' '.join(context.args[1:]).lower())
    else:
        await update.message.reply_text("❌ Используйте: list, buy, money, my, leave")


async def factory_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Список точек со свободными местами"""
    session = Session()
    try:
        users = session.query(User).all()
        occupied = {}
        for user in users:
            if user.factories and user.factories != '[]':
                factories = json.loads(user.factories)
                for f in factories:
                    name = f.get('name')
                    if name:
                        occupied[name] = occupied.get(name, 0) + 1
        
        text = "🏭 *Доступные точки*\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        for key, f in FACTORIES.items():
            free = f['slots'] - occupied.get(key, 0)
            text += f"{f['name']}\n"
            text += f"   • Свободно: {free}/{f['slots']}\n"
            text += f"   • Цена: {f['price']} RC (3 суток)\n"
            text += f"   • Доход: {f['income']} {f['income_type']}/час\n"
            if f['level'] > 1:
                text += f"   • Требуется: {f['level']} уровень\n"
            text += "\n"
        await update.message.reply_text(text, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error in factory_list: {e}")
        await update.message.reply_text("❌ Ошибка")
    finally:
        session.close()


async def factory_buy(update: Update, context: ContextTypes.DEFAULT_TYPE, factory_name: str):
    """Купить/арендовать точку"""
    if factory_name not in FACTORIES:
        await update.message.reply_text("❌ Неизвестная точка. Используйте: свалка, мастерская, станция, дамба, химка, комплекс, реактор")
        return
    
    factory = FACTORIES[factory_name]
    session = Session()
    try:
        user = session.query(User).filter_by(user_id=update.effective_user.id).first()
        if not user:
            await update.message.reply_text("❌ /start")
            return
        
        if user.level < factory['level']:
            await update.message.reply_text(f"❌ Нужен {factory['level']} уровень! У вас {user.level}")
            return
        
        if user.radcoins < factory['price']:
            await update.message.reply_text(f"❌ Нужно {factory['price']} RC, у вас {user.radcoins:.0f}")
            return
        
        # Проверяем свободные места
        users = session.query(User).all()
        occupied = 0
        for u in users:
            if u.factories and u.factories != '[]':
                facs = json.loads(u.factories)
                for f in facs:
                    if f.get('name') == factory_name:
                        occupied += 1
        
        if occupied >= factory['slots']:
            await update.message.reply_text(f"❌ Нет свободных мест на {factory['name']}!")
            return
        
        # Проверяем, не арендовал ли уже эту точку
        current = json.loads(user.factories) if user.factories else []
        for f in current:
            if f.get('name') == factory_name:
                await update.message.reply_text(f"❌ Вы уже арендуете {factory['name']}!")
                return
        
        # Покупаем
        user.radcoins -= factory['price']
        current.append({
            'name': factory_name,
            'bought_at': datetime.now().isoformat(),
            'last_collect': datetime.now().isoformat()
        })
        user.factories = json.dumps(current)
        
        log_user_id = user.user_id
        log_username = user.username
        log_price = factory['price']
        
        session.commit()
        
        safe_log_user_action(
            log_user_id, log_username, 'factory_buy',
            amount_rc=-log_price, item=factory_name
        )
        
        await update.message.reply_text(
            f"✅ *Арендована {factory['name']}!*\n\n"
            f"💰 Потрачено: {factory['price']} RC\n"
            f"⏰ Срок: 3 суток\n"
            f"📈 Доход: {factory['income']} {factory['income_type']}/час\n\n"
            f"💡 Забирайте доход командой `/factory money`",
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Error in factory_buy: {e}")
        session.rollback()
        await update.message.reply_text("❌ Ошибка")
    finally:
        session.close()


async def factory_money(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Забрать накопленный доход (без 36-часового блокиратора)"""
    session = Session()
    try:
        user = session.query(User).filter_by(user_id=update.effective_user.id).first()
        if not user:
            await update.message.reply_text("❌ /start")
            return
        
        if not user.factories or user.factories == '[]':
            await update.message.reply_text("❌ У вас нет арендованных точек")
            return
        
        factories = json.loads(user.factories)
        now = datetime.now()
        total_income = 0
        updated = []
        expired = []
        income_type = 'RC'
        log_user_id = user.user_id
        log_username = user.username
        
        for f in factories:
            name = f.get('name')
            if name not in FACTORIES:
                continue
            
            factory = FACTORIES[name]
            bought_at = datetime.fromisoformat(f['bought_at'])
            last_collect = datetime.fromisoformat(f.get('last_collect', bought_at.isoformat()))
            
            # Проверка срока аренды (3 суток)
            if now - bought_at > timedelta(hours=72):
                expired.append(name)
                continue
            
            # Расчёт дохода (без блокировки 36 часов)
            hours = (now - last_collect).total_seconds() / 3600
            income = int(hours * factory['income'])
            total_income += income
            income_type = factory['income_type']
            
            # Обновляем время последнего сбора
            f['last_collect'] = now.isoformat()
            updated.append(f)
        
        if expired:
            # Удаляем просроченные точки
            for name in expired:
                factories = [f for f in factories if f.get('name') != name]
            await update.message.reply_text(
                f"⚠️ *Точки аннулированы!*\n\n"
                f"❌ {', '.join(expired)} — срок аренды истёк",
                parse_mode='Markdown'
            )
        
        if total_income > 0:
            # Добавляем доход
            for f in updated:
                factory = FACTORIES[f['name']]
                if factory['income_type'] == 'RC':
                    user.radcoins += total_income
                else:
                    user.radfragments += total_income
            
            user.factories = json.dumps(factories)
            session.commit()
            
            if income_type == 'RC':
                safe_log_user_action(
                    log_user_id, log_username, 'factory_money',
                    amount_rc=total_income, item=f"{len(updated)} точек"
                )
            else:
                safe_log_user_action(
                    log_user_id, log_username, 'factory_money',
                    amount_rf=total_income, item=f"{len(updated)} точек"
                )
            
            await update.message.reply_text(
                f"💰 *Доход получен!*\n\n"
                f"📦 Сумма: +{total_income} {income_type}\n"
                f"🏭 Точки: {', '.join([f['name'] for f in factories if f not in expired])}",
                parse_mode='Markdown'
            )
        elif expired:
            user.factories = json.dumps(factories)
            session.commit()
        else:
            await update.message.reply_text("💰 Нет накопленного дохода. Зайдите позже!")
        
    except Exception as e:
        logger.error(f"Error in factory_money: {e}")
        session.rollback()
        await update.message.reply_text("❌ Ошибка")
    finally:
        session.close()


async def factory_my(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать мои точки"""
    session = Session()
    try:
        user = session.query(User).filter_by(user_id=update.effective_user.id).first()
        if not user:
            await update.message.reply_text("❌ /start")
            return
        
        if not user.factories or user.factories == '[]':
            await update.message.reply_text("🏭 У вас нет арендованных точек", parse_mode='Markdown')
            return
        
        factories = json.loads(user.factories)
        now = datetime.now()
        text = "🏭 *Мои точки*\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        for f in factories:
            name = f.get('name')
            if name not in FACTORIES:
                continue
            
            factory = FACTORIES[name]
            bought_at = datetime.fromisoformat(f['bought_at'])
            
            expires_in = (bought_at + timedelta(hours=72)) - now
            hours_left = expires_in.seconds // 3600
            minutes_left = (expires_in.seconds % 3600) // 60
            
            text += f"{factory['name']}\n"
            text += f"   • Доход: {factory['income']} {factory['income_type']}/час\n"
            text += f"   • Срок: {hours_left}ч {minutes_left}мин\n"
            text += f"   • Накоплено: зайдите за доходом!\n\n"
        
        text += "💡 `/factory money` — забрать доход"
        await update.message.reply_text(text, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error in factory_my: {e}")
        await update.message.reply_text("❌ Ошибка")
    finally:
        session.close()


async def factory_leave(update: Update, context: ContextTypes.DEFAULT_TYPE, factory_name: str):
    """Освободить точку"""
    if factory_name not in FACTORIES:
        await update.message.reply_text("❌ Неизвестная точка")
        return
    
    session = Session()
    try:
        user = session.query(User).filter_by(user_id=update.effective_user.id).first()
        if not user:
            await update.message.reply_text("❌ /start")
            return
        
        if not user.factories or user.factories == '[]':
            await update.message.reply_text("❌ У вас нет арендованных точек")
            return
        
        factories = json.loads(user.factories)
        new_factories = [f for f in factories if f.get('name') != factory_name]
        
        if len(new_factories) == len(factories):
            await update.message.reply_text(f"❌ У вас нет точки {factory_name}")
            return
        
        user.factories = json.dumps(new_factories)
        
        log_user_id = user.user_id
        log_username = user.username
        
        session.commit()
        
        safe_log_user_action(
            log_user_id, log_username, 'factory_leave', item=factory_name
        )
        
        await update.message.reply_text(
            f"✅ *Точка {FACTORIES[factory_name]['name']} освобождена*",
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Error in factory_leave: {e}")
        session.rollback()
        await update.message.reply_text("❌ Ошибка")
    finally:
        session.close()


# ==================== АДМИН-КОМАНДЫ ФАБРИК ====================

async def afactory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Админ-команды для управления фабриками"""
    if not await is_admin(update, context):
        await update.message.reply_text("❌ Нет прав!")
        return
    
    if not context.args:
        await update.message.reply_text(
            "👑 *Админ-панель фабрик*\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "/afactory list — список всех точек\n"
            "/afactory list [название] — игроки на точке\n"
            "/afactory remove @ник [точка] — убрать игрока\n"
            "/afactory add @ник [точка] — добавить игрока\n"
            "/afactory ban @ник [точка] — заблокировать\n"
            "/afactory unban @ник [точка] — разблокировать\n"
            "/afactory clean [точка] — очистить точку",
            parse_mode='Markdown'
        )
        return
    
    action = context.args[0].lower()
    
    if action == 'list':
        if len(context.args) > 1:
            await afactory_list_point(update, context, context.args[1].lower())
        else:
            await afactory_list_all(update, context)
    elif action == 'remove':
        if len(context.args) < 3:
            await update.message.reply_text("❌ /afactory remove @ник [точка]")
            return
        await afactory_remove(update, context, context.args[1].lstrip('@'), context.args[2].lower())
    elif action == 'add':
        if len(context.args) < 3:
            await update.message.reply_text("❌ /afactory add @ник [точка]")
            return
        await afactory_add(update, context, context.args[1].lstrip('@'), context.args[2].lower())
    elif action == 'ban':
        if len(context.args) < 3:
            await update.message.reply_text("❌ /afactory ban @ник [точка]")
            return
        await afactory_ban(update, context, context.args[1].lstrip('@'), context.args[2].lower())
    elif action == 'unban':
        if len(context.args) < 3:
            await update.message.reply_text("❌ /afactory unban @ник [точка]")
            return
        await afactory_unban(update, context, context.args[1].lstrip('@'), context.args[2].lower())
    elif action == 'clean':
        if len(context.args) < 2:
            await update.message.reply_text("❌ /afactory clean [точка]")
            return
        await afactory_clean(update, context, context.args[1].lower())
    else:
        await update.message.reply_text("❌ Неизвестная команда")


async def afactory_list_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Список всех точек с занятостью"""
    session = Session()
    try:
        users = session.query(User).all()
        occupied = {}
        banned = {}
        
        for user in users:
            if user.factories and user.factories != '[]':
                factories = json.loads(user.factories)
                for f in factories:
                    name = f.get('name')
                    if name:
                        occupied[name] = occupied.get(name, 0) + 1
            if user.factory_bans and user.factory_bans != '[]':
                bans = json.loads(user.factory_bans)
                for name in bans:
                    banned[name] = banned.get(name, 0) + 1
        
        text = "👑 *Список фабрик*\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        for key, f in FACTORIES.items():
            free = f['slots'] - occupied.get(key, 0)
            banned_count = banned.get(key, 0)
            text += f"🏭 *{f['name']}*\n"
            text += f"   • Свободно: {free}/{f['slots']}\n"
            text += f"   • Забанено: {banned_count}\n"
            text += "\n"
        await update.message.reply_text(text, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error in afactory_list_all: {e}")
        await update.message.reply_text("❌ Ошибка")
    finally:
        session.close()


async def afactory_list_point(update: Update, context: ContextTypes.DEFAULT_TYPE, point_name: str):
    """Список игроков на конкретной точке"""
    if point_name not in FACTORIES:
        await update.message.reply_text("❌ Неизвестная точка. Доступны: свалка, мастерская, станция, дамба, химка, комплекс, реактор")
        return
    
    session = Session()
    try:
        users = session.query(User).all()
        players = []
        banned_players = []
        
        for user in users:
            if user.factories and user.factories != '[]':
                factories = json.loads(user.factories)
                for f in factories:
                    if f.get('name') == point_name:
                        players.append(user)
                        break
            if user.factory_bans and user.factory_bans != '[]':
                bans = json.loads(user.factory_bans)
                if point_name in bans:
                    banned_players.append(user)
        
        text = f"👑 *{FACTORIES[point_name]['name']}*\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        text += f"📊 *Всего мест:* {FACTORIES[point_name]['slots']}\n"
        text += f"🔓 *Свободно:* {FACTORIES[point_name]['slots'] - len(players)}\n"
        text += f"👥 *Активных:* {len(players)}\n"
        text += f"🔴 *Забанено:* {len(banned_players)}\n\n"
        
        if players:
            text += "*✅ Активные игроки:*\n"
            for i, p in enumerate(players, 1):
                safe_name = escape_markdown(p.username or f"ID:{p.user_id}")
                text += f"{i}. {safe_name}\n"
        
        if banned_players:
            text += "\n*❌ Забаненные:*\n"
            for i, p in enumerate(banned_players, 1):
                safe_name = escape_markdown(p.username or f"ID:{p.user_id}")
                text += f"{i}. {safe_name}\n"
        
        await update.message.reply_text(text, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error in afactory_list_point: {e}")
        await update.message.reply_text("❌ Ошибка")
    finally:
        session.close()


async def afactory_remove(update: Update, context: ContextTypes.DEFAULT_TYPE, username: str, point_name: str):
    """Убрать игрока с точки"""
    if point_name not in FACTORIES:
        await update.message.reply_text("❌ Неизвестная точка")
        return
    
    session = Session()
    try:
        user = session.query(User).filter_by(username=username).first()
        if not user:
            await update.message.reply_text(f"❌ @{username} не найден")
            return
        
        if not user.factories or user.factories == '[]':
            await update.message.reply_text(f"❌ У @{username} нет арендованных точек")
            return
        
        factories = json.loads(user.factories)
        new_factories = [f for f in factories if f.get('name') != point_name]
        
        if len(new_factories) == len(factories):
            await update.message.reply_text(f"❌ У @{username} нет точки {point_name}")
            return
        
        user.factories = json.dumps(new_factories)
        session.commit()
        
        safe_log_user_action(
            user.user_id, user.username, 'factory_admin_remove',
            item=f"{point_name} (админ)"
        )
        
        await update.message.reply_text(
            f"✅ *@{username} убран с точки {FACTORIES[point_name]['name']}*",
            parse_mode='Markdown'
        )
        
        try:
            await context.bot.send_message(
                user.user_id,
                f"👑 *Администратор убрал вас с точки {FACTORIES[point_name]['name']}!*"
            )
        except:
            pass
    except Exception as e:
        logger.error(f"Error in afactory_remove: {e}")
        session.rollback()
        await update.message.reply_text("❌ Ошибка")
    finally:
        session.close()


async def afactory_add(update: Update, context: ContextTypes.DEFAULT_TYPE, username: str, point_name: str):
    """Добавить игрока на точку (бесплатно)"""
    if point_name not in FACTORIES:
        await update.message.reply_text("❌ Неизвестная точка")
        return
    
    session = Session()
    try:
        user = session.query(User).filter_by(username=username).first()
        if not user:
            await update.message.reply_text(f"❌ @{username} не найден")
            return
        
        bans = json.loads(user.factory_bans) if user.factory_bans else []
        if point_name in bans:
            await update.message.reply_text(f"❌ @{username} забанен на точке {point_name}")
            return
        
        current = json.loads(user.factories) if user.factories else []
        
        for f in current:
            if f.get('name') == point_name:
                await update.message.reply_text(f"❌ @{username} уже арендует точку {point_name}")
                return
        
        current.append({
            'name': point_name,
            'bought_at': datetime.now().isoformat(),
            'last_collect': datetime.now().isoformat()
        })
        user.factories = json.dumps(current)
        session.commit()
        
        safe_log_user_action(
            user.user_id, user.username, 'factory_admin_add',
            item=f"{point_name} (админ)"
        )
        
        await update.message.reply_text(
            f"✅ *@{username} добавлен на точку {FACTORIES[point_name]['name']}!*",
            parse_mode='Markdown'
        )
        
        try:
            await context.bot.send_message(
                user.user_id,
                f"👑 *Администратор добавил вас на точку {FACTORIES[point_name]['name']}!*\n\n"
                f"💰 Доход: {FACTORIES[point_name]['income']} {FACTORIES[point_name]['income_type']}/час\n"
                f"📝 Забирайте доход командой `/factory money`",
                parse_mode='Markdown'
            )
        except:
            pass
    except Exception as e:
        logger.error(f"Error in afactory_add: {e}")
        session.rollback()
        await update.message.reply_text("❌ Ошибка")
    finally:
        session.close()


async def afactory_ban(update: Update, context: ContextTypes.DEFAULT_TYPE, username: str, point_name: str):
    """Забанить игрока на точке"""
    if point_name not in FACTORIES:
        await update.message.reply_text("❌ Неизвестная точка")
        return
    
    session = Session()
    try:
        user = session.query(User).filter_by(username=username).first()
        if not user:
            await update.message.reply_text(f"❌ @{username} не найден")
            return
        
        bans = json.loads(user.factory_bans) if user.factory_bans else []
        if point_name in bans:
            await update.message.reply_text(f"❌ @{username} уже забанен на точке {point_name}")
            return
        
        bans.append(point_name)
        user.factory_bans = json.dumps(bans)
        
        if user.factories and user.factories != '[]':
            factories = json.loads(user.factories)
            new_factories = [f for f in factories if f.get('name') != point_name]
            user.factories = json.dumps(new_factories)
        
        session.commit()
        
        safe_log_user_action(
            user.user_id, user.username, 'factory_admin_ban', item=point_name
        )
        
        await update.message.reply_text(
            f"✅ *@{username} забанен на точке {FACTORIES[point_name]['name']}*",
            parse_mode='Markdown'
        )
        
        try:
            await context.bot.send_message(
                user.user_id,
                f"🔴 *Вас забанили на точке {FACTORIES[point_name]['name']}!*"
            )
        except:
            pass
    except Exception as e:
        logger.error(f"Error in afactory_ban: {e}")
        session.rollback()
        await update.message.reply_text("❌ Ошибка")
    finally:
        session.close()


async def afactory_unban(update: Update, context: ContextTypes.DEFAULT_TYPE, username: str, point_name: str):
    """Разбанить игрока на точке"""
    if point_name not in FACTORIES:
        await update.message.reply_text("❌ Неизвестная точка")
        return
    
    session = Session()
    try:
        user = session.query(User).filter_by(username=username).first()
        if not user:
            await update.message.reply_text(f"❌ @{username} не найден")
            return
        
        bans = json.loads(user.factory_bans) if user.factory_bans else []
        if point_name not in bans:
            await update.message.reply_text(f"❌ @{username} не забанен на точке {point_name}")
            return
        
        bans.remove(point_name)
        user.factory_bans = json.dumps(bans)
        session.commit()
        
        safe_log_user_action(
            user.user_id, user.username, 'factory_admin_unban', item=point_name
        )
        
        await update.message.reply_text(
            f"✅ *@{username} разбанен на точке {FACTORIES[point_name]['name']}*",
            parse_mode='Markdown'
        )
        
        try:
            await context.bot.send_message(
                user.user_id,
                f"🟢 *Вас разбанили на точке {FACTORIES[point_name]['name']}!*"
            )
        except:
            pass
    except Exception as e:
        logger.error(f"Error in afactory_unban: {e}")
        session.rollback()
        await update.message.reply_text("❌ Ошибка")
    finally:
        session.close()


async def afactory_clean(update: Update, context: ContextTypes.DEFAULT_TYPE, point_name: str):
    """Очистить точку — удалить всех игроков"""
    if point_name not in FACTORIES:
        await update.message.reply_text("❌ Неизвестная точка")
        return
    
    session = Session()
    try:
        users = session.query(User).all()
        removed = 0
        
        for user in users:
            if user.factories and user.factories != '[]':
                factories = json.loads(user.factories)
                new_factories = [f for f in factories if f.get('name') != point_name]
                if len(new_factories) != len(factories):
                    user.factories = json.dumps(new_factories)
                    removed += 1
        
        session.commit()
        
        await update.message.reply_text(
            f"✅ *Точка {FACTORIES[point_name]['name']} очищена!*\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📊 Удалено игроков: {removed}",
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Error in afactory_clean: {e}")
        session.rollback()
        await update.message.reply_text("❌ Ошибка")
    finally:
        session.close()
