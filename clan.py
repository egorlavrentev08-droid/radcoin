# clan.py - Кланы и радио
# Версия: 4.0.0 (ALPHA)

from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import ContextTypes
from config import logger, MAX_CLAN_BONUS
from core import send_to_private, is_admin
from database import Session, User, Clan, RadioGroup
from utils import log_user_action as old_log_user_action


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


# ==================== РАБОТА С БАЗОЙ РАДИО-ГРУПП ====================

def load_radio_groups(context):
    """Загрузить группы из БД в bot_data"""
    session = Session()
    try:
        groups = session.query(RadioGroup).all()
        context.bot_data['radio_groups'] = {g.chat_id for g in groups}
        logger.info(f"📻 Загружено {len(groups)} групп радио из БД")
    except Exception as e:
        logger.error(f"Ошибка загрузки радио-групп: {e}")
        context.bot_data['radio_groups'] = set()
    finally:
        session.close()


def save_radio_group(chat_id, chat_title=None):
    """Сохранить группу в БД"""
    session = Session()
    try:
        existing = session.query(RadioGroup).filter_by(chat_id=chat_id).first()
        if not existing:
            group = RadioGroup(chat_id=chat_id, chat_title=chat_title)
            session.add(group)
            session.commit()
            logger.info(f"📻 Группа {chat_id} добавлена в БД")
    except Exception as e:
        logger.error(f"Ошибка сохранения радио-группы: {e}")
    finally:
        session.close()


def remove_radio_group(chat_id):
    """Удалить группу из БД"""
    session = Session()
    try:
        session.query(RadioGroup).filter_by(chat_id=chat_id).delete()
        session.commit()
        logger.info(f"📻 Группа {chat_id} удалена из БД")
    except Exception as e:
        logger.error(f"Ошибка удаления радио-группы: {e}")
    finally:
        session.close()


# ==================== КЛАНЫ ====================

async def clan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Главная команда кланов"""
    if not context.args:
        await update.message.reply_text(
            "🏰 *Кланы Пустоши*\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "/clan create [название] — создать (2ур, 1000RC)\n"
            "/clan join [название] — вступить (1ур)\n"
            "/clan info — информация\n"
            "/clan invest [сумма] — вложить RC\n"
            "/clan withdraw [сумма] — снять RC (лидер)\n"
            "/clan give @ник [сумма] — выдать RC участнику (лидер)\n"
            "/clan up [коллектор/опыт/удвоение] — улучшить\n"
            "/clan list — список кланов\n"
            "/clan players [название] — список участников\n"
            "/clan goodbye — распустить (дважды)",
            parse_mode='Markdown'
        )
        return
    
    action = context.args[0].lower()
    
    if action == "create":
        await clan_create(update, context)
    elif action == "join":
        await clan_join(update, context)
    elif action == "info":
        await clan_info(update, context)
    elif action == "invest":
        await clan_invest(update, context)
    elif action == "withdraw":
        await clan_withdraw(update, context)
    elif action == "give":
        await clan_give(update, context)
    elif action == "up":
        await clan_upgrade(update, context)
    elif action == "list":
        await clan_list(update, context)
    elif action == "players":
        await clan_players(update, context)
    elif action == "goodbye":
        await clan_goodbye(update, context)
    else:
        await update.message.reply_text("❌ Неизвестная команда")


async def clan_create(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Создать клан"""
    if len(context.args) < 2:
        await update.message.reply_text("❌ /clan create [название]")
        return
    name = ' '.join(context.args[1:])
    if len(name) > 30:
        await update.message.reply_text("❌ Название до 30 символов")
        return
    session = Session()
    try:
        user = session.query(User).filter_by(user_id=update.effective_user.id).first()
        if not user:
            await update.message.reply_text("❌ Сначала /start")
            return
        if user.clan_id:
            await update.message.reply_text("❌ Вы уже в клане")
            return
        if user.level < 2:
            await update.message.reply_text("❌ Для создания клана нужен 2 уровень")
            return
        if user.radcoins < 1000:
            await update.message.reply_text(f"❌ Нужно 1000 RC, у вас {user.radcoins:.0f}")
            return
        existing = session.query(Clan).filter_by(name=name).first()
        if existing:
            await update.message.reply_text("❌ Клан с таким названием уже существует")
            return
        
        clan = Clan(name=name, leader_id=user.user_id, max_members=50)
        session.add(clan)
        session.flush()
        user.clan_id = clan.id
        user.radcoins -= 1000
        
        session.commit()
        
        safe_log_user_action(
            user.user_id, user.username, 'clan_create',
            amount_rc=-1000, item=name
        )
        
        safe_name = escape_markdown(name)
        await update.message.reply_text(f"🏰 *Клан {safe_name} создан!*", parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error in clan_create: {e}")
        session.rollback()
        await update.message.reply_text("❌ Ошибка")
    finally:
        session.close()


async def clan_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Вступить в клан с проверкой лимита участников"""
    if len(context.args) < 2:
        await update.message.reply_text("❌ /clan join [название]")
        return
    name = ' '.join(context.args[1:])
    session = Session()
    try:
        user = session.query(User).filter_by(user_id=update.effective_user.id).first()
        if not user:
            await update.message.reply_text("❌ /start")
            return
        if user.clan_id:
            await update.message.reply_text("❌ Вы уже в клане")
            return
        
        clan = session.query(Clan).filter_by(name=name).first()
        if not clan:
            await update.message.reply_text("❌ Клан не найден")
            return
        
        # Проверка лимита участников
        current_members = session.query(User).filter_by(clan_id=clan.id).count()
        max_members = clan.max_members if hasattr(clan, 'max_members') else 50
        
        if current_members >= max_members:
            await update.message.reply_text(f"❌ В клане уже {max_members} участников!")
            return
        
        user.clan_id = clan.id
        session.commit()
        
        safe_log_user_action(
            user.user_id, user.username, 'clan_join', item=name
        )
        
        safe_name = escape_markdown(clan.name)
        await update.message.reply_text(f"✅ *Вы вступили в клан {safe_name}!*", parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error in clan_join: {e}")
        session.rollback()
        await update.message.reply_text("❌ Ошибка")
    finally:
        session.close()


async def clan_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Информация о клане (с max_members)"""
    session = Session()
    try:
        user = session.query(User).filter_by(user_id=update.effective_user.id).first()
        if not user or not user.clan_id:
            await update.message.reply_text("❌ Вы не в клане")
            return
        clan = session.query(Clan).filter_by(id=user.clan_id).first()
        if not clan:
            await update.message.reply_text("❌ Клан не найден")
            return
        members = session.query(User).filter_by(clan_id=clan.id).count()
        leader = session.query(User).filter_by(user_id=clan.leader_id).first()
        max_members = clan.max_members if hasattr(clan, 'max_members') else 50
        
        safe_name = escape_markdown(clan.name)
        leader_name = escape_markdown(leader.username) if leader else "?"
        
        text = (
            f"🏰 *{safe_name}*\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👑 *Лидер:* @{leader_name}\n"
            f"👥 *Участников:* {members}/{max_members}\n"
            f"💰 *Казна:* {clan.treasury_coins:.0f} RC\n"
            f"💎 *Кристаллы:* {clan.treasury_crystals}\n\n"
            f"📈 *Улучшения:*\n"
            f"  • +{clan.collect_bonus}% к сбору\n"
            f"  • +{clan.exp_bonus * 5}% к опыту\n"
            f"  • +{clan.double_bonus}% к удвоению"
        )
        await update.message.reply_text(text, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error in clan_info: {e}")
        await update.message.reply_text("❌ Ошибка")
    finally:
        session.close()


async def clan_invest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Инвестировать в казну клана"""
    if len(context.args) < 2:
        await update.message.reply_text("❌ /clan invest [сумма]")
        return
    try:
        amount = int(context.args[1])
        if amount <= 0:
            await update.message.reply_text("❌ Положительная сумма")
            return
    except ValueError:
        await update.message.reply_text("❌ Введите число")
        return
    session = Session()
    try:
        user = session.query(User).filter_by(user_id=update.effective_user.id).first()
        if not user or not user.clan_id:
            await update.message.reply_text("❌ Вы не в клане")
            return
        clan = session.query(Clan).filter_by(id=user.clan_id).first()
        if not clan:
            await update.message.reply_text("❌ Клан не найден")
            return
        if user.radcoins < amount:
            await update.message.reply_text(f"❌ Не хватает! У вас {user.radcoins:.0f} RC")
            return
        user.radcoins -= amount
        clan.treasury_coins += amount
        
        session.commit()
        
        safe_log_user_action(
            user.user_id, user.username, 'clan_invest',
            amount_rc=-amount, item=clan.name
        )
        
        safe_name = escape_markdown(clan.name)
        await update.message.reply_text(f"💰 *Инвестировано {amount} RC в {safe_name}*", parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error in clan_invest: {e}")
        session.rollback()
        await update.message.reply_text("❌ Ошибка")
    finally:
        session.close()


async def clan_withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Снять средства из казны (только лидер) с подтверждением"""
    if len(context.args) < 2:
        await update.message.reply_text("❌ /clan withdraw [сумма]")
        return
    try:
        amount = int(context.args[1])
        if amount <= 0:
            await update.message.reply_text("❌ Положительная сумма")
            return
    except ValueError:
        await update.message.reply_text("❌ Введите число")
        return
    session = Session()
    try:
        user = session.query(User).filter_by(user_id=update.effective_user.id).first()
        if not user or not user.clan_id:
            await update.message.reply_text("❌ Вы не в клане")
            return
        clan = session.query(Clan).filter_by(id=user.clan_id).first()
        if not clan:
            await update.message.reply_text("❌ Клан не найден")
            return
        if clan.leader_id != user.user_id:
            await update.message.reply_text("❌ Только лидер может снимать средства")
            return
        if clan.treasury_coins < amount:
            await update.message.reply_text(f"❌ В казне {clan.treasury_coins:.0f} RC")
            return
        
        # Подтверждение вывода
        if not context.user_data.get('confirm_withdraw'):
            context.user_data['confirm_withdraw'] = True
            safe_name = escape_markdown(clan.name)
            await update.message.reply_text(
                f"⚠️ *Подтвердите вывод {amount} RC из казны*\n"
                f"💰 В казне клана {safe_name}: {clan.treasury_coins:.0f} RC\n\n"
                f"📝 Отправьте `/clan withdraw {amount}` ещё раз для подтверждения.",
                parse_mode='Markdown'
            )
            return
        
        context.user_data.pop('confirm_withdraw')
        clan.treasury_coins -= amount
        user.radcoins += amount
        
        session.commit()
        
        safe_log_user_action(
            user.user_id, user.username, 'clan_withdraw',
            amount_rc=amount, item=clan.name
        )
        
        safe_name = escape_markdown(clan.name)
        await update.message.reply_text(
            f"💰 *Снято {amount} RC из казны*\n\n"
            f"🏰 Клан: {safe_name}\n"
            f"📊 Остаток: {clan.treasury_coins:.0f} RC",
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Error in clan_withdraw: {e}")
        session.rollback()
        await update.message.reply_text("❌ Ошибка")
    finally:
        session.close()


async def clan_give(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выдать средства участнику (только лидер)"""
    if len(context.args) < 3:
        await update.message.reply_text("❌ /clan give @ник [сумма]")
        return
    username = context.args[1].lstrip('@')
    try:
        amount = int(context.args[2])
        if amount <= 0:
            await update.message.reply_text("❌ Положительная сумма")
            return
    except ValueError:
        await update.message.reply_text("❌ Введите число")
        return
    session = Session()
    try:
        user = session.query(User).filter_by(user_id=update.effective_user.id).first()
        if not user or not user.clan_id:
            await update.message.reply_text("❌ Вы не в клане")
            return
        clan = session.query(Clan).filter_by(id=user.clan_id).first()
        if not clan:
            await update.message.reply_text("❌ Клан не найден")
            return
        if clan.leader_id != user.user_id:
            await update.message.reply_text("❌ Только лидер может выдавать средства")
            return
        target = session.query(User).filter_by(username=username).first()
        if not target or target.clan_id != clan.id:
            await update.message.reply_text(f"❌ @{username} не состоит в клане")
            return
        if clan.treasury_coins < amount:
            await update.message.reply_text(f"❌ В казне {clan.treasury_coins:.0f} RC")
            return
        
        clan.treasury_coins -= amount
        target.radcoins += amount
        
        session.commit()
        
        safe_log_user_action(
            user.user_id, user.username, 'clan_give',
            amount_rc=-amount, item=f"{username} ({clan.name})"
        )
        safe_log_user_action(
            target.user_id, target.username, 'clan_receive',
            amount_rc=amount, item=clan.name
        )
        
        safe_name = escape_markdown(clan.name)
        await update.message.reply_text(
            f"💰 *Выдано {amount} RC участнику @{username}*\n\n"
            f"🏰 Клан: {safe_name}\n"
            f"📊 Остаток: {clan.treasury_coins:.0f} RC",
            parse_mode='Markdown'
        )
        try:
            await context.bot.send_message(
                target.user_id,
                f"💰 *Вам выдали {amount} RC из казны клана {safe_name}!*",
                parse_mode='Markdown'
            )
        except:
            pass
    except Exception as e:
        logger.error(f"Error in clan_give: {e}")
        session.rollback()
        await update.message.reply_text("❌ Ошибка")
    finally:
        session.close()


async def clan_upgrade(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Улучшить клан (только лидер)"""
    if len(context.args) < 2:
        await update.message.reply_text("❌ /clan up [коллектор/опыт/удвоение]")
        return
    upgrade = context.args[1].lower()
    session = Session()
    try:
        user = session.query(User).filter_by(user_id=update.effective_user.id).first()
        if not user or not user.clan_id:
            await update.message.reply_text("❌ Вы не в клане")
            return
        clan = session.query(Clan).filter_by(id=user.clan_id).first()
        if not clan:
            await update.message.reply_text("❌ Клан не найден")
            return
        if clan.leader_id != user.user_id:
            await update.message.reply_text("❌ Только лидер")
            return
        if upgrade == 'коллектор':
            if clan.collect_bonus >= MAX_CLAN_BONUS:
                await update.message.reply_text("❌ Максимум 10")
                return
            cost = 25 + clan.collect_bonus * 5
            clan.collect_bonus += 1
        elif upgrade == 'опыт':
            if clan.exp_bonus >= MAX_CLAN_BONUS:
                await update.message.reply_text("❌ Максимум 10")
                return
            cost = 25 + clan.exp_bonus * 5
            clan.exp_bonus += 1
        elif upgrade == 'удвоение':
            if clan.double_bonus >= MAX_CLAN_BONUS:
                await update.message.reply_text("❌ Максимум 10")
                return
            cost = 25 + clan.double_bonus * 5
            clan.double_bonus += 1
        else:
            await update.message.reply_text("❌ коллектор/опыт/удвоение")
            return
        if clan.treasury_crystals < cost:
            await update.message.reply_text(f"❌ Нужно {cost} 💎")
            return
        clan.treasury_crystals -= cost
        
        session.commit()
        
        safe_log_user_action(
            user.user_id, user.username, f'clan_upgrade_{upgrade}',
            amount_crystals=-cost, item=clan.name
        )
        
        await update.message.reply_text(f"📈 *Улучшен {upgrade}!*", parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error in clan_upgrade: {e}")
        session.rollback()
        await update.message.reply_text("❌ Ошибка")
    finally:
        session.close()


async def clan_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Список кланов (с max_members)"""
    session = Session()
    try:
        clans = session.query(Clan).order_by(Clan.created_at).all()
        if not clans:
            await update.message.reply_text("📋 *Нет кланов*", parse_mode='Markdown')
            return
        text = "📋 *Список кланов*\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        for clan in clans:
            members = session.query(User).filter_by(clan_id=clan.id).count()
            max_members = clan.max_members if hasattr(clan, 'max_members') else 50
            safe_name = escape_markdown(clan.name)
            text += f"🏰 *{safe_name}* — 👥 {members}/{max_members}\n"
        await update.message.reply_text(text, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error in clan_list: {e}")
        await update.message.reply_text("❌ Ошибка")
    finally:
        session.close()


async def clan_players(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Список игроков в клане (с max_members)"""
    if len(context.args) < 2:
        await update.message.reply_text("❌ /clan players [название клана]")
        return
    clan_name = ' '.join(context.args[1:])
    session = Session()
    try:
        clan = session.query(Clan).filter_by(name=clan_name).first()
        if not clan:
            await update.message.reply_text(f"❌ Клан '{clan_name}' не найден!")
            return
        members = session.query(User).filter_by(clan_id=clan.id).order_by(User.level.desc()).all()
        if not members:
            await update.message.reply_text(f"📋 В клане '{clan_name}' нет участников")
            return
        leader = session.query(User).filter_by(user_id=clan.leader_id).first()
        max_members = clan.max_members if hasattr(clan, 'max_members') else 50
        
        safe_name = escape_markdown(clan.name)
        leader_name = escape_markdown(leader.username) if leader else "?"
        
        text = f"🏰 *{safe_name}*\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
        text += f"👑 *Лидер:* @{leader_name}\n"
        text += f"👥 *Участников:* {len(members)}/{max_members}\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        for i, member in enumerate(members, 1):
            role = "👑 Лидер" if member.user_id == clan.leader_id else "🔹 Участник"
            safe_member = escape_markdown(member.username or f"ID:{member.user_id}")
            text += f"{i}. *{safe_member}* — {role} — {member.level} уровень\n"
        await update.message.reply_text(text, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error in clan_players: {e}")
        await update.message.reply_text("❌ Ошибка")
    finally:
        session.close()


async def clan_goodbye(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Распустить клан (только лидер)"""
    session = Session()
    try:
        user = session.query(User).filter_by(user_id=update.effective_user.id).first()
        if not user or not user.clan_id:
            await update.message.reply_text("❌ Вы не в клане")
            return
        clan = session.query(Clan).filter_by(id=user.clan_id).first()
        if not clan:
            await update.message.reply_text("❌ Клан не найден")
            return
        if clan.leader_id != user.user_id:
            await update.message.reply_text("❌ Только лидер")
            return
        if not context.user_data.get('confirm_clan_delete'):
            context.user_data['confirm_clan_delete'] = True
            safe_name = escape_markdown(clan.name)
            await update.message.reply_text(f"⚠️ *Распустить {safe_name}?* /clan goodbye ещё раз", parse_mode='Markdown')
            return
        context.user_data.pop('confirm_clan_delete')
        members = session.query(User).filter_by(clan_id=clan.id).all()
        for member in members:
            member.clan_id = None
        session.delete(clan)
        
        safe_name = escape_markdown(clan.name)
        session.commit()
        
        safe_log_user_action(
            user.user_id, user.username, 'clan_disband', item=clan.name
        )
        
        await update.message.reply_text(f"🏰 *Клан {safe_name} распущен*", parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error in clan_goodbye: {e}")
        session.rollback()
        await update.message.reply_text("❌ Ошибка")
    finally:
        session.close()


# ==================== РАДИО ====================

async def radion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Активация радио по коду"""
    if not context.args:
        await update.message.reply_text("❌ /radion [код]")
        return
    code = context.args[0]
    session = Session()
    try:
        user = session.query(User).filter_by(user_id=update.effective_user.id).first()
        if not user:
            await update.message.reply_text("❌ /start")
            return
        if user.radio_active:
            await update.message.reply_text("❌ Радио уже активировано!")
            return
        if user.radio_code != code:
            await update.message.reply_text("❌ Неверный код!")
            return
        if user.radio_banned:
            await update.message.reply_text("❌ Вы заблокированы в радио!")
            return
        
        user.radio_active = True
        session.commit()
        
        safe_log_user_action(
            user.user_id, user.username, 'radio_activate', item=code
        )
        
        await update.message.reply_text(
            "📻 *Радио активировано!*\n\n"
            "Теперь вы можете вещать командой:\n"
            "`/radio [текст]`\n\n"
            "📢 *Правила:*\n"
            "• Не чаще 1 раза в минуту\n"
            "• Не более 200 символов\n"
            "• Запрещены оскорбления и спам",
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Error in radion: {e}")
        await update.message.reply_text("❌ Ошибка")
    finally:
        session.close()


async def radio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправить сообщение в радиоэфир"""
    if not context.args:
        await update.message.reply_text("❌ /radio [текст]")
        return
    session = Session()
    try:
        user = session.query(User).filter_by(user_id=update.effective_user.id).first()
        if not user:
            await update.message.reply_text("❌ /start")
            return
        if not user.radio_active:
            await update.message.reply_text("❌ Радио не активировано! /radion [код]")
            return
        if user.radio_banned:
            await update.message.reply_text("❌ Вы заблокированы в радио!")
            return
        
        msg = ' '.join(context.args)
        if len(msg) > 200:
            await update.message.reply_text("❌ Не более 200 символов!")
            return
        
        last_radio = context.user_data.get('last_radio')
        if last_radio and datetime.now() - last_radio < timedelta(minutes=1):
            remaining = 60 - (datetime.now() - last_radio).seconds
            await update.message.reply_text(f"❌ Следующее сообщение через {remaining} секунд!")
            return
        
        context.user_data['last_radio'] = datetime.now()
        
        safe_username = escape_markdown(user.username)
        safe_msg = escape_markdown(msg)
        text = f"📻 *Радио Пустоши*\n\n🎙️ *Ведущий:* @{safe_username}\n\n📢 {safe_msg}"
        
        # Отправляем всем игрокам в личку
        users = session.query(User).all()
        sent = 0
        for u in users:
            try:
                await context.bot.send_message(chat_id=u.user_id, text=text, parse_mode='Markdown')
                sent += 1
            except:
                pass
        
        # Отправляем в группы из bot_data (загружены из БД)
        groups = context.bot_data.get('radio_groups', set())
        for chat_id in groups:
            try:
                await context.bot.send_message(chat_id=chat_id, text=text, parse_mode='Markdown')
            except:
                pass
        
        safe_log_user_action(
            user.user_id, user.username, 'radio_send',
            item=f"{len(msg)} символов, {sent} личек, {len(groups)} групп"
        )
        
        await update.message.reply_text(
            f"✅ *Сообщение отправлено!*\n\n"
            f"📨 В личку: {sent}\n"
            f"👥 В группы: {len(groups)}\n"
            f"📻 Вещание завершено.",
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Error in radio: {e}")
        await update.message.reply_text("❌ Ошибка")
    finally:
        session.close()


async def radio_register_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Регистрация группы для радио с сохранением в БД"""
    session = Session()
    try:
        if update.effective_chat.type in ['group', 'supergroup']:
            chat_id = update.effective_chat.id
            chat_title = update.effective_chat.title
            
            groups = context.bot_data.get('radio_groups', set())
            groups.add(chat_id)
            context.bot_data['radio_groups'] = groups
            
            # Сохраняем в БД
            save_radio_group(chat_id, chat_title)
            
            logger.info(f"📻 Группа {chat_id} добавлена в радио")
    except Exception as e:
        logger.error(f"Error in radio_register_group: {e}")
    finally:
        session.close()


# ==================== АДМИН-РАДИО ====================

async def aradio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Админ-панель радио с работой через БД"""
    if not await is_admin(update, context):
        await update.message.reply_text("❌ Нет прав!")
        return
    
    if not context.args:
        await update.message.reply_text(
            "📻 *Админ-панель радио*\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "/aradio give @ник [код] — выдать доступ\n"
            "/aradio take @ник — забрать доступ\n"
            "/aradio list — список ведущих\n"
            "/aradio ban @ник — заблокировать\n"
            "/aradio unban @ник — разблокировать\n"
            "/aradio check — список групп с радио\n"
            "/aradio add [ссылка/ID] — добавить группу\n"
            "/aradio clear [ссылка/ID] — удалить группу",
            parse_mode='Markdown'
        )
        return
    
    action = context.args[0].lower()
    session = Session()
    
    try:
        if action == 'give':
            if len(context.args) < 3:
                await update.message.reply_text("❌ /aradio give @ник [код]")
                return
            username = context.args[1].lstrip('@')
            code = context.args[2]
            user = session.query(User).filter_by(username=username).first()
            if not user:
                await update.message.reply_text(f"❌ @{username} не найден")
                return
            user.radio_code = code
            user.radio_active = False
            user.radio_banned = False
            session.commit()
            
            safe_log_user_action(
                user.user_id, user.username, 'radio_admin_give', item=code
            )
            
            await update.message.reply_text(f"✅ Радиодоступ выдан @{username} с кодом {code}")
            try:
                await context.bot.send_message(
                    user.user_id,
                    f"📻 Вам выдан доступ к радио!\n\n🔑 Код: {code}\n📝 Используйте: /radion {code}"
                )
            except:
                pass
        
        elif action == 'take':
            if len(context.args) < 2:
                await update.message.reply_text("❌ /aradio take @ник")
                return
            username = context.args[1].lstrip('@')
            user = session.query(User).filter_by(username=username).first()
            if not user:
                await update.message.reply_text(f"❌ @{username} не найден")
                return
            user.radio_active = False
            user.radio_code = None
            session.commit()
            
            safe_log_user_action(
                user.user_id, user.username, 'radio_admin_take'
            )
            
            await update.message.reply_text(f"✅ Радиодоступ у @{username} забран", parse_mode='Markdown')
        
        elif action == 'list':
            users = session.query(User).filter(User.radio_active == True).all()
            if not users:
                await update.message.reply_text("📋 *Нет активных радиоведущих*", parse_mode='Markdown')
                return
            text = "📻 *Активные радиоведущие*\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            for i, u in enumerate(users, 1):
                status = "🔴 ЗАБАНЕН" if u.radio_banned else "🟢 АКТИВЕН"
                safe_name = escape_markdown(u.username or f"ID:{u.user_id}")
                text += f"{i}. *{safe_name}* — {status}\n"
            await update.message.reply_text(text, parse_mode='Markdown')
        
        elif action == 'ban':
            if len(context.args) < 2:
                await update.message.reply_text("❌ /aradio ban @ник")
                return
            username = context.args[1].lstrip('@')
            user = session.query(User).filter_by(username=username).first()
            if not user:
                await update.message.reply_text(f"❌ @{username} не найден")
                return
            user.radio_banned = True
            session.commit()
            
            safe_log_user_action(
                user.user_id, user.username, 'radio_admin_ban'
            )
            
            await update.message.reply_text(f"✅ @{username} заблокирован в радио", parse_mode='Markdown')
        
        elif action == 'unban':
            if len(context.args) < 2:
                await update.message.reply_text("❌ /aradio unban @ник")
                return
            username = context.args[1].lstrip('@')
            user = session.query(User).filter_by(username=username).first()
            if not user:
                await update.message.reply_text(f"❌ @{username} не найден")
                return
            user.radio_banned = False
            session.commit()
            
            safe_log_user_action(
                user.user_id, user.username, 'radio_admin_unban'
            )
            
            await update.message.reply_text(f"✅ @{username} разблокирован в радио", parse_mode='Markdown')
        
        elif action == 'check':
            groups = context.bot_data.get('radio_groups', set())
            if not groups:
                await update.message.reply_text("📻 *Радио не активировано ни в одной группе*", parse_mode='Markdown')
                return
            text = "📻 *Список групп с радио*\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            for chat_id in groups:
                try:
                    chat = await context.bot.get_chat(chat_id)
                    title = chat.title or f"ID: {chat_id}"
                    safe_title = escape_markdown(title)
                    text += f"• {safe_title}\n  `{chat_id}`\n"
                except:
                    text += f"• `{chat_id}` (недоступна)\n"
            await send_to_private(update, context, text)
        
        elif action == 'add':
            groups = context.bot_data.get('radio_groups', set())
            chat_id = None
            
            if update.effective_chat.type in ['group', 'supergroup']:
                chat_id = update.effective_chat.id
                await update.message.reply_text(f"✅ Эта группа добавлена в радио!", parse_mode='Markdown')
            elif len(context.args) >= 2:
                identifier = context.args[1]
                if identifier.startswith('@'):
                    try:
                        chat = await context.bot.get_chat(identifier)
                        chat_id = chat.id
                    except:
                        await update.message.reply_text("❌ Не удалось найти чат по ссылке")
                        return
                elif identifier.lstrip('-').isdigit():
                    chat_id = int(identifier)
                else:
                    await update.message.reply_text("❌ Укажите ID чата, ссылку или вызовите команду в самой группе")
                    return
            else:
                await update.message.reply_text("❌ /aradio add [ссылка/ID] или вызовите команду в группе")
                return
            
            if chat_id:
                groups.add(chat_id)
                context.bot_data['radio_groups'] = groups
                save_radio_group(chat_id)
                if update.effective_chat.id != chat_id:
                    await update.message.reply_text(f"✅ Группа `{chat_id}` добавлена в радио", parse_mode='Markdown')
        
        elif action == 'clear':
            groups = context.bot_data.get('radio_groups', set())
            chat_id = None
            
            if update.effective_chat.type in ['group', 'supergroup']:
                chat_id = update.effective_chat.id
            elif len(context.args) >= 2:
                identifier = context.args[1]
                if identifier.startswith('@'):
                    try:
                        chat = await context.bot.get_chat(identifier)
                        chat_id = chat.id
                    except:
                        await update.message.reply_text("❌ Не удалось найти чат по ссылке")
                        return
                elif identifier.lstrip('-').isdigit():
                    chat_id = int(identifier)
                else:
                    await update.message.reply_text("❌ Укажите ID чата, ссылку или вызовите команду в самой группе")
                    return
            else:
                await update.message.reply_text("❌ /aradio clear [ссылка/ID] или вызовите команду в группе")
                return
            
            if chat_id in groups:
                groups.remove(chat_id)
                context.bot_data['radio_groups'] = groups
                remove_radio_group(chat_id)
                if update.effective_chat.id == chat_id:
                    await update.message.reply_text(f"✅ Эта группа удалена из радио!", parse_mode='Markdown')
                else:
                    await update.message.reply_text(f"✅ Группа `{chat_id}` удалена из радио", parse_mode='Markdown')
            else:
                await update.message.reply_text(f"❌ Группа не найдена в списке радио", parse_mode='Markdown')
        
        else:
            await update.message.reply_text("❌ Используйте: give, take, list, ban, unban, check, add, clear")
    
    except Exception as e:
        logger.error(f"Error in aradio: {e}")
        await update.message.reply_text("❌ Ошибка")
    finally:
        session.close()
