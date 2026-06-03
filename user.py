# user.py - Команды пользователя
# Версия: 4.0.0 (ALPHA)

from telegram import Update
from telegram.ext import ContextTypes
from config import logger, MAX_LEVEL, get_exp_for_level
from core import send_to_private
from database import Session, User, Clan
from utils import get_equipped, escape_markdown, get_backpack, get_medkits_in_backpack
import json
from datetime import datetime, timedelta


# ==================== ПРОФИЛЬ ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Стартовая команда"""
    user = update.effective_user
    session = Session()
    try:
        db_user = session.query(User).filter_by(user_id=user.id).first()
        is_new = False
        if not db_user:
            db_user = User(user_id=user.id, username=user.username)
            session.add(db_user)
            is_new = True
        elif user.username and db_user.username != user.username:
            db_user.username = user.username
        session.commit()
        
        if is_new:
            db_user.radcoins += 1000
            session.commit()
            await update.message.reply_text(
                "🌟 *RadCoin Bot — Пустошь*\n\n"
                "🎁 *Бонус новичка: 1000 RC!*\n\n"
                "💰 /collect — сбор ресурсов\n"
                "🏹 /hunt — охота на мутантов\n"
                "🚇 /metro — хардкорное подземелье (10+ уровень)\n"
                "🔬 /lab — лаборатория для учёных\n"
                "🛒 /shop — магазин\n"
                "📖 /help — справка",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                "🌟 *RadCoin Bot — Пустошь*\n\n"
                "💰 /collect — сбор ресурсов\n"
                "🏹 /hunt — охота\n"
                "🚇 /metro — метро (10+ уровень)\n"
                "🛒 /shop — магазин\n"
                "📖 /help — справка",
                parse_mode='Markdown'
            )
    except Exception as e:
        logger.error(f"Error in start: {e}")
        await update.message.reply_text("❌ Ошибка")
    finally:
        session.close()


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Справка"""
    text = (
        "📖 *RadCoin Bot — Пустошь*\n\n"
        "🎲 */collect* — сбор ресурсов\n"
        "🏹 */hunt* — охота\n"
        "🚇 */metro* — метро (хардкор, 10+ уровень)\n"
        "🛒 */shop* — магазин\n"
        "💰 */buy [товар] [кол-во]* — купить\n"
        "📦 */inv* — инвентарь\n"
        "👤 */profile* — профиль\n"
        "📊 */stats* — статистика\n"
        "🏆 */achievements* — достижения\n"
        "🎰 */casino [сумма]* — казино\n"
        "💱 */exchange [количество]* — RF→RC\n"
        "🛠️ */craft [предмет]* — крафт\n"
        "🔔 */announce on/off* — уведомления\n"
        "🗺️ */locate [название]* — сменить локацию\n"
        "🎭 */class [название]* — сменить класс\n"
        "🔬 */lab* — лаборатория (для учёных)\n"
        "⚡ */effect* — активные эффекты\n"
        "🏆 */top [level/rc/boss/hunt/clan]* — таблица\n\n"
        "🐾 *Питомцы:* /pet accept/deny/bye\n"
        "🏰 *Кланы:* /clan create/join/info/invest/up/list/goodbye\n"
        "🎁 *Сундуки:* /chest list/chance/open\n"
        "📻 *Радио:* /radio [текст], /radion [код]\n"
        "📖 *Советы:* /advice [раздел]"
    )
    await send_to_private(update, context, text)


async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Профиль пользователя"""
    user = update.effective_user
    session = Session()
    try:
        db_user = session.query(User).filter_by(user_id=user.id).first()
        if not db_user:
            db_user = User(user_id=user.id, username=user.username)
            session.add(db_user)
            session.commit()
        
        next_exp = get_exp_for_level(min(db_user.level + 1, MAX_LEVEL))
        exp_needed = max(0, next_exp - db_user.experience)
        
        class_names = {
            'stalker': '🟢 Сталкер',
            'military': '🔫 Военный',
            'bandit': '🗡️ Бандит',
            'scientist': '🔬 Учёный'
        }
        class_name = class_names.get(db_user.user_class, '🟢 Сталкер')
        
        equipped = get_equipped(db_user)
        armor_display = {
            'броня1': '🟢 Лёгкая броня (25%)',
            'броня2': '🔵 Утяжеленная броня (40%)',
            'броня3': '🟣 Тактическая броня (50%)',
            'броня4': '🟠 Тяжёлая броня (60%)',
            'броня5': '🔴 Силовая броня (75%)'
        }
        armor_text = ""
        if equipped.get('armor'):
            armor_text = f"\n🛡️ *Броня:* {armor_display.get(equipped['armor'], equipped['armor'])}"
        
        weapon_display = {
            'ружье': '🔫 Ружьё',
            'гарпун': '🎣 Гарпун',
            'винтовка': '🔫 Винтовка',
            'гаусс': '⚡ Винтовка Гаусса'
        }
        weapon_text = ""
        if equipped.get('weapon'):
            weapon_text = f"\n⚔️ *Оружие:* {weapon_display.get(equipped['weapon'], equipped['weapon'])}"
        
        # Рюкзак (НОВОЕ!)
        backpack_text = ""
        if equipped.get('backpack'):
            backpack_display = {
                'backpack1': '🎒 Маленький рюкзак (+20% RC, +10% RF, 1 аптечка)',
                'backpack2': '🎒 Тактический рюкзак (+30% RC, +15% RF, 2 аптечки)',
                'backpack3': '🎒 Профессиональный рюкзак (+45% RC, +18% RF, 3 аптечки)'
            }
            medkits = get_medkits_in_backpack(db_user)
            backpack_text = f"\n🎒 *Рюкзак:* {backpack_display.get(equipped['backpack'], equipped['backpack'])} (💊 {medkits})"
        
        safe_username = escape_markdown(db_user.username or "Игрок")
        
        text = (
            f"👤 *{safe_username}*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🎭 *Класс:* {class_name}\n"
            f"☢️ *РадКоины:* {db_user.radcoins:.0f}\n"
            f"☣️ *РадФрагменты:* {db_user.radfragments}\n"
            f"⚠️ *Уровень:* {db_user.level}"
        )
        
        if db_user.level < MAX_LEVEL:
            text += f" ({exp_needed} опыта до {db_user.level + 1} уровня)"
        
        text += armor_text
        text += weapon_text
        text += backpack_text
        
        if db_user.pet:
            pet_names = {
                'овчарка': '🐕 Овчарка', 'волк': '🐺 Волк',
                'рысь': '🐈 Рысь', 'пума': '🐆 Пума',
                'попугай': '🦜 Попугай', 'кайот': '🐕 Кайот'
            }
            text += f"\n🐾 *Питомец:* {pet_names.get(db_user.pet, db_user.pet)}"
        
        if db_user.clan_id:
            clan = session.query(Clan).filter_by(id=db_user.clan_id).first()
            if clan:
                safe_clan = escape_markdown(clan.name)
                text += f"\n🏰 *Клан:* {safe_clan}"
        
        await send_to_private(update, context, text)
    except Exception as e:
        logger.error(f"Error in profile: {e}")
        await update.message.reply_text("❌ Ошибка")
    finally:
        session.close()


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Статистика пользователя"""
    user = update.effective_user
    session = Session()
    try:
        db_user = session.query(User).filter_by(user_id=user.id).first()
        if not db_user:
            await update.message.reply_text("❌ /start")
            return
        
        safe_username = escape_markdown(db_user.username or "Игрок")
        text = (
            f"📊 *Статистика {safe_username}*\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🎲 *Сборов:* {db_user.total_collects}\n"
            f"☢️ *Всего RC:* {db_user.total_rc_earned:.0f}\n"
            f"🏆 *Лучший сбор:* {db_user.best_collect:.0f}\n"
            f"🧬 *Мутантов убито:* {db_user.mutants_killed}\n"
            f"👾 *Мутантов 3 ур:* {db_user.mutants_lvl3}\n"
            f"👑 *Боссов:* {db_user.bosses_killed}\n"
            f"💀 *Смертей:* {db_user.deaths}\n"
            f"📈 *Серия сборов:* {db_user.daily_streak} дней"
        )
        await send_to_private(update, context, text)
    except Exception as e:
        logger.error(f"Error in stats: {e}")
        await update.message.reply_text("❌ Ошибка")
    finally:
        session.close()


async def achievements(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Достижения пользователя"""
    user = update.effective_user
    session = Session()
    try:
        db_user = session.query(User).filter_by(user_id=user.id).first()
        if not db_user:
            await update.message.reply_text("❌ /start")
            return
        current = json.loads(db_user.achievements) if db_user.achievements else []
        text = "🏆 *Достижения*\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
        ach_names = ['добытчик', 'инвестор', 'терпила', 'кандидат', 'мастер', 'легенда', 'старатель', 'постоянный_клиент', 'миллионер']
        for ach in ach_names:
            text += f"✅ {ach}\n" if ach in current else f"⬜ {ach}\n"
        await send_to_private(update, context, text)
    except Exception as e:
        logger.error(f"Error in achievements: {e}")
        await update.message.reply_text("❌ Ошибка")
    finally:
        session.close()


async def announce(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Настройка уведомлений"""
    user_id = update.effective_user.id
    session = Session()
    try:
        user = session.query(User).filter_by(user_id=user_id).first()
        if not user:
            user = User(user_id=user_id, username=update.effective_user.username)
            session.add(user)
            session.commit()
        if not context.args:
            status = "включены ✅" if user.notifications_enabled else "выключены ❌"
            await update.message.reply_text(f"🔔 *Уведомления*\n\nСейчас уведомления {status}\n\n/announce on — включить\n/announce off — выключить", parse_mode='Markdown')
            return
        if context.args[0].lower() == 'on':
            user.notifications_enabled = True
            session.commit()
            await update.message.reply_text("✅ *Уведомления включены!*", parse_mode='Markdown')
        elif context.args[0].lower() == 'off':
            user.notifications_enabled = False
            session.commit()
            await update.message.reply_text("❌ *Уведомления выключены!*", parse_mode='Markdown')
        else:
            await update.message.reply_text("❌ /announce on или off")
    except Exception as e:
        logger.error(f"Error in announce: {e}")
        await update.message.reply_text("❌ Ошибка")
    finally:
        session.close()


async def phase_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Информация о фазе Пустоши"""
    phase = context.bot_data.get('phase', 1)
    phases = {
        1: {'name': '🟢 МИРНАЯ', 'desc': 'Нет мутантов, нет охоты', 'bonus': 'Безопасно'},
        2: {'name': '🟡 ОПАСНАЯ', 'desc': 'Мутанты, охота, питомцы', 'bonus': 'Риск 10%'},
        3: {'name': '🔴 АПОКАЛИПТИЧЕСКАЯ', 'desc': 'Аномалии, высокий риск', 'bonus': 'Аномалии 10%'}
    }
    p = phases.get(phase, phases[1])
    text = f"🌍 *Фаза Пустоши: {p['name']}*\n━━━━━━━━━━━━━━━━━━━━━━━━\n📖 {p['desc']}\n\n⚡ {p['bonus']}"
    await send_to_private(update, context, text)


# ==================== КОМАНДЫ КЛАССОВ ====================

async def class_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Смена класса"""
    if not context.args:
        await update.message.reply_text(
            "🎭 *Смена класса*\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Доступные классы:\n"
            "🟢 `/class сталкер` — базовый\n"
            "🔫 `/class военный` — +30% опыт, +20% RC, -30% RF\n"
            "🗡️ `/class бандит` — +40% RF, +15% RC, -25% опыт\n"
            "🔬 `/class ученый` — +50% опыт, +25% RF, -20% RC\n\n"
            "💰 Смена класса: 100 RF или 10000 RC\n"
            "🆓 Бесплатная смена раз в 7 дней (через /class upd)\n"
            "💳 Платная смена: /class pay [название]",
            parse_mode='Markdown'
        )
        return
    
    if len(context.args) >= 2:
        if context.args[0].lower() == 'pay':
            await class_pay(update, context, context.args[1].lower())
            return
        elif context.args[0].lower() == 'upd':
            await class_upd(update, context, context.args[1].lower())
            return
    
    class_name = context.args[0].lower()
    valid_classes = {'сталкер': 'stalker', 'военный': 'military', 'бандит': 'bandit', 'ученый': 'scientist'}
    
    if class_name not in valid_classes:
        await update.message.reply_text("❌ Доступные классы: сталкер, военный, бандит, ученый")
        return
    
    session = Session()
    try:
        user = session.query(User).filter_by(user_id=update.effective_user.id).first()
        if not user:
            await update.message.reply_text("❌ Сначала /start")
            return
        
        target_class = valid_classes[class_name]
        if user.user_class == target_class:
            await update.message.reply_text(f"❌ Вы уже {class_name}")
            return
        
        now = datetime.now()
        can_change_free = False
        if user.last_free_class_change:
            one_week_ago = now - timedelta(days=7)
            if user.last_free_class_change < one_week_ago:
                can_change_free = True
        else:
            can_change_free = True
        
        if can_change_free:
            user.last_free_class_change = now
            user.user_class = target_class
            session.commit()
            await update.message.reply_text(f"✅ *Класс изменён на {class_name} бесплатно!*\n\nСледующая бесплатная смена через 7 дней.", parse_mode='Markdown')
        else:
            await update.message.reply_text(
                f"❌ *Бесплатная смена ещё недоступна!*\n\n"
                f"💰 Сменить класс можно за:\n"
                f"• 100 ☣️ РадФрагментов\n"
                f"• 10000 ☢️ РадКоинов\n\n"
                f"Для платной смены:\n"
                f"`/class pay {class_name}`",
                parse_mode='Markdown'
            )
    except Exception as e:
        logger.error(f"Error in class_command: {e}")
        await update.message.reply_text("❌ Ошибка")
    finally:
        session.close()


async def class_pay(update: Update, context: ContextTypes.DEFAULT_TYPE, class_name: str):
    """Платная смена класса"""
    valid_classes = {'сталкер': 'stalker', 'военный': 'military', 'бандит': 'bandit', 'ученый': 'scientist'}
    
    if class_name not in valid_classes:
        await update.message.reply_text("❌ Доступные классы: сталкер, военный, бандит, ученый")
        return
    
    session = Session()
    try:
        user = session.query(User).filter_by(user_id=update.effective_user.id).first()
        if not user:
            await update.message.reply_text("❌ /start")
            return
        
        target_class = valid_classes[class_name]
        if user.user_class == target_class:
            await update.message.reply_text(f"❌ Вы уже {class_name}")
            return
        
        if user.radfragments >= 100:
            user.radfragments -= 100
        elif user.radcoins >= 10000:
            user.radcoins -= 10000
        else:
            await update.message.reply_text("❌ Не хватает ресурсов! Нужно 100 RF или 10000 RC")
            return
        
        user.user_class = target_class
        user.last_free_class_change = datetime.now()
        session.commit()
        
        await update.message.reply_text(f"✅ *Класс изменён на {class_name} за плату!*", parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error in class_pay: {e}")
        session.rollback()
        await update.message.reply_text("❌ Ошибка")
    finally:
        session.close()


async def class_upd(update: Update, context: ContextTypes.DEFAULT_TYPE, class_name: str):
    """Бесплатная смена класса (раз в 7 дней)"""
    valid_classes = {'сталкер': 'stalker', 'военный': 'military', 'бандит': 'bandit', 'ученый': 'scientist'}
    
    if class_name not in valid_classes:
        await update.message.reply_text("❌ Доступные классы: сталкер, военный, бандит, ученый")
        return
    
    session = Session()
    try:
        user = session.query(User).filter_by(user_id=update.effective_user.id).first()
        if not user:
            await update.message.reply_text("❌ /start")
            return
        
        target_class = valid_classes[class_name]
        if user.user_class == target_class:
            await update.message.reply_text(f"❌ Вы уже {class_name}")
            return
        
        now = datetime.now()
        if user.last_free_class_change:
            one_week_ago = now - timedelta(days=7)
            if user.last_free_class_change >= one_week_ago:
                remaining = user.last_free_class_change + timedelta(days=7) - now
                hours = remaining.seconds // 3600
                await update.message.reply_text(f"❌ Бесплатная смена будет доступна через {hours} часов!", parse_mode='Markdown')
                return
        
        user.user_class = target_class
        user.last_free_class_change = now
        session.commit()
        
        await update.message.reply_text(f"✅ *Класс изменён на {class_name} бесплатно!*\n\nСледующая бесплатная смена через 7 дней.", parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error in class_upd: {e}")
        session.rollback()
        await update.message.reply_text("❌ Ошибка")
    finally:
        session.close()


async def class_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Информация о текущем классе"""
    session = Session()
    try:
        user = session.query(User).filter_by(user_id=update.effective_user.id).first()
        if not user:
            await update.message.reply_text("❌ /start")
            return
        
        class_name = user.user_class if hasattr(user, 'user_class') else 'stalker'
        class_emoji = {'stalker': '🟢', 'military': '🔫', 'bandit': '🗡️', 'scientist': '🔬'}
        class_stats = {
            'stalker': '📊 Базовые значения',
            'military': '⚡ +30% опыт, +20% RC, -30% RF',
            'bandit': '⚡ +40% RF, +15% RC, -25% опыт',
            'scientist': '⚡ +50% опыт, +25% RF, -20% RC'
        }
        
        await update.message.reply_text(
            f"🎭 *Ваш класс*\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{class_emoji.get(class_name, '🟢')} *{class_name.capitalize()}*\n\n"
            f"{class_stats.get(class_name, '')}\n\n"
            f"💡 Сменить класс: `/class [название]`\n"
            f"💰 Платная смена: `/class pay [название]`\n"
            f"🆓 Бесплатная смена: `/class upd [название]` (раз в 7 дней)",
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Error in class_info: {e}")
        await update.message.reply_text("❌ Ошибка")
    finally:
        session.close()
