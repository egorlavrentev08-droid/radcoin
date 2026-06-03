# dop.py - Дополнительные механики (лаборатория, эффекты, металлоискатель)
# Версия: 4.0.0 (ALPHA)

import random
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import ContextTypes

from config import logger, MAX_LEVEL, get_exp_for_level, get_energy_bonus, get_reducer_bonus, METAL_DETECTOR
from core import send_to_private
from database import Session, User
from utils import escape_markdown, safe_log_user_action, get_item_count, add_item_to_inventory, remove_item_from_inventory, get_backpack, get_medkits_in_backpack, add_medkits_to_backpack, remove_medkits_from_backpack


# ==================== ЛАБОРАТОРИЯ ДЛЯ УЧЁНЫХ ====================

def get_lab_cooldown(user, now):
    """Рассчитать кулдаун лаборатории с учётом редуктора и питомца"""
    cooldown = timedelta(days=1)
    
    if user.cooldown_reducer_until and user.cooldown_reducer_until > now:
        reducer_level = getattr(user, 'reducer_level', 'basic')
        reducer_data = get_reducer_bonus(reducer_level)
        cooldown = timedelta(hours=int(24 * reducer_data['cooldown_reduction']))
    
    if user.pet == 'кайот':
        if cooldown == timedelta(days=1):
            cooldown = timedelta(hours=12)
        else:
            cooldown = timedelta(hours=int(cooldown.seconds / 3600 / 2))
    
    return cooldown


async def lab(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Лаборатория для учёных (вместо охоты)"""
    session = Session()
    try:
        user = session.query(User).filter_by(user_id=update.effective_user.id).first()
        if not user:
            await update.message.reply_text("❌ /start")
            return
        
        # Проверка класса
        class_name = getattr(user, 'user_class', 'stalker')
        if class_name != 'scientist':
            await update.message.reply_text(
                "🔬 *Только для учёных!*\n\n"
                "Ваш класс не позволяет использовать лабораторию.\n"
                "Смените класс на учёного командой `/class ученый`",
                parse_mode='Markdown'
            )
            return
        
        # Проверка уровня
        if user.level < 2:
            await update.message.reply_text("❌ *Лаборатория доступна со 2 уровня*", parse_mode='Markdown')
            return
        
        phase = context.bot_data.get('phase', 1)
        if phase < 2:
            await update.message.reply_text("❌ *Лаборатория недоступна!* Фаза 2 или 3", parse_mode='Markdown')
            return
        
        now = datetime.now()
        cooldown = get_lab_cooldown(user, now)
        
        if user.last_lab and now - user.last_lab < cooldown:
            remaining = cooldown - (now - user.last_lab)
            hours = remaining.seconds // 3600
            minutes = (remaining.seconds % 3600) // 60
            await update.message.reply_text(f"⏰ *Лаборатория восстановится через {hours}ч {minutes}мин.*", parse_mode='Markdown')
            return
        
        # Расчёт шансов от уровня
        level = min(user.level, MAX_LEVEL)
        
        fail_chance = max(5, 75 - (level * 0.9))
        success_chance = min(60, 20 + (level * 0.7))
        great_success_chance = min(35, 5 + (level * 0.2))
        
        total = fail_chance + success_chance + great_success_chance
        if total != 100:
            fail_chance = int(fail_chance / total * 100)
            success_chance = int(success_chance / total * 100)
            great_success_chance = 100 - fail_chance - success_chance
        
        roll = random.random() * 100
        
        if roll < fail_chance:
            reward_rf = 10
            reward_exp = 25
            result_name = "💥 *ПРОВАЛ!*"
            result_desc = "Реактор перегрелся, эксперимент пошёл не по плану."
            action_name = 'lab_fail'
        elif roll < fail_chance + success_chance:
            reward_rf = 100
            reward_exp = 100
            result_name = "✅ *УСПЕХ!*"
            result_desc = "Эксперимент удался! Вы получили ценные данные."
            action_name = 'lab_success'
        else:
            reward_rf = 1000
            reward_exp = 500
            result_name = "🎉 *УСПЕШНЫЙ УСПЕХ!*"
            result_desc = "Невероятно! Вы совершили научное открытие!"
            action_name = 'lab_great_success'
        
        # Бонус класса учёного
        if class_name == 'scientist':
            reward_exp = int(reward_exp * 1.5)
            reward_rf = int(reward_rf * 1.25)
        
        # Бонус энергетика
        if user.energy_drink_until and user.energy_drink_until > now:
            energy_level = getattr(user, 'energy_drink_level', 'strike')
            energy_data = get_energy_bonus(energy_level)
            reward_rf = int(reward_rf * energy_data['rf_bonus'])
            reward_exp = int(reward_exp * 1.1)
        
        user.radfragments += reward_rf
        user.experience += reward_exp
        user.last_lab = now
        
        level_up = False
        while user.level < MAX_LEVEL and user.experience >= get_exp_for_level(user.level + 1):
            user.level += 1
            level_up = True
        
        session.commit()
        
        safe_log_user_action(
            user.user_id, user.username, action_name,
            amount_rf=reward_rf, amount_rc=reward_exp
        )
        
        hours = cooldown.seconds // 3600
        safe_username = escape_markdown(user.username or "Игрок")
        
        msg = (
            f"🔬 *Лаборатория*\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Учёный {safe_username} проводит эксперимент в лаборатории.\n\n"
            f"{result_name}\n"
            f"📖 {result_desc}\n\n"
            f"💰 *Награда:* +{reward_rf} ☣️ РадФрагментов!\n"
            f"⚠️ *Опыт:* +{reward_exp}!\n"
        )
        
        if level_up:
            msg += f"\n🎉 *УРОВЕНЬ ПОВЫШЕН!* Теперь вы {user.level} уровень! 🎉"
        
        msg += f"\n\n⏰ *Лаборатория восстановится через {hours} часов.*"
        
        await update.message.reply_text(msg, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Error in lab: {e}")
        session.rollback()
        await update.message.reply_text("❌ Ошибка в лаборатории")
    finally:
        session.close()


# ==================== УПРАВЛЕНИЕ ЭФФЕКТАМИ ====================

async def effect_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать активные эффекты"""
    session = Session()
    try:
        user = session.query(User).filter_by(user_id=update.effective_user.id).first()
        if not user:
            await update.message.reply_text("❌ /start")
            return
        
        now = datetime.now()
        text = "⚡ *Активные эффекты*\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        # Энергетик
        if user.energy_drink_until and user.energy_drink_until > now:
            remaining = user.energy_drink_until - now
            hours = remaining.seconds // 3600
            minutes = (remaining.seconds % 3600) // 60
            energy_level = getattr(user, 'energy_drink_level', 'strike')
            energy_data = get_energy_bonus(energy_level)
            safe_name = escape_markdown(energy_data['name'])
            text += f"⚡ *{safe_name}*\n"
            text += f"   • Осталось: {hours}ч {minutes}мин\n"
            text += f"   • Стеков: {user.energy_drink_stacks}\n"
            text += f"   • Бонусы: +{(energy_data['rc_bonus']-1)*100:.0f}% RC, +{(energy_data['rf_bonus']-1)*100:.0f}% RF\n"
            text += f"   • +{(energy_data['crystal_bonus']-1)*100:.0f}% кристаллы, +{energy_data['survive_bonus']}% выживание\n\n"
        else:
            text += "⚡ *Энергетик:* не активен\n\n"
        
        # Редуктор
        if user.cooldown_reducer_until and user.cooldown_reducer_until > now:
            remaining = user.cooldown_reducer_until - now
            days = remaining.days
            hours = remaining.seconds // 3600
            reducer_level = getattr(user, 'reducer_level', 'basic')
            reducer_data = get_reducer_bonus(reducer_level)
            safe_name = escape_markdown(reducer_data['name'])
            text += f"⏱️ *{safe_name}*\n"
            text += f"   • Осталось: {days}д {hours}ч\n"
            text += f"   • Стеков: {user.reducer_stacks}\n"
            text += f"   • Ускорение: {int((1-reducer_data['cooldown_reduction'])*100)}%\n"
        else:
            text += "⏱️ *Редуктор:* не активен"
        
        text += "\n\n💡 /effect clear — очистить все эффекты"
        
        await update.message.reply_text(text, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Error in effect_command: {e}")
        await update.message.reply_text("❌ Ошибка")
    finally:
        session.close()


async def effect_clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Очистить все активные эффекты"""
    session = Session()
    try:
        user = session.query(User).filter_by(user_id=update.effective_user.id).first()
        if not user:
            await update.message.reply_text("❌ /start")
            return
        
        now = datetime.now()
        has_effects = False
        
        if user.energy_drink_until and user.energy_drink_until > now:
            has_effects = True
        if user.cooldown_reducer_until and user.cooldown_reducer_until > now:
            has_effects = True
        
        if not has_effects:
            await update.message.reply_text("❌ *У вас нет активных эффектов*", parse_mode='Markdown')
            return
        
        if not context.user_data.get('confirm_effect_clear'):
            context.user_data['confirm_effect_clear'] = True
            await update.message.reply_text(
                "⚠️ *Внимание!*\n\n"
                "Вы действительно хотите очистить все активные эффекты?\n"
                "Энергетики и редукторы, потраченные на активацию, НЕ ВОЗВРАЩАЮТСЯ.\n\n"
                "Отправьте `/effect clear` ещё раз для подтверждения.",
                parse_mode='Markdown'
            )
            return
        
        context.user_data.pop('confirm_effect_clear')
        
        user.energy_drink_until = None
        user.energy_drink_stacks = 0
        user.energy_drink_level = 'strike'
        user.cooldown_reducer_until = None
        user.reducer_stacks = 0
        user.reducer_level = 'basic'
        
        session.commit()
        
        safe_log_user_action(
            user.user_id, user.username, 'effect_clear'
        )
        
        await update.message.reply_text(
            "✅ *Все активные эффекты очищены!*\n\n"
            "Вы можете активировать новые энергетики и редукторы.",
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Error in effect_clear: {e}")
        session.rollback()
        await update.message.reply_text("❌ Ошибка")
    finally:
        session.close()


# ==================== МЕТАЛЛОИСКАТЕЛЬ ====================

def get_metal_detector_cooldown(user, now):
    """Получить оставшееся время кулдауна металлоискателя"""
    if not user.last_metal_detector:
        return 0
    
    duration = getattr(user, 'last_metal_detector_duration', 3)
    elapsed = now - user.last_metal_detector
    
    if elapsed >= timedelta(hours=duration):
        return 0
    
    remaining = timedelta(hours=duration) - elapsed
    return remaining


async def use_metal_detector(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Использовать металлоискатель (10% шанс найти сундук, кулдаун 3-18 часов)"""
    session = Session()
    try:
        user = session.query(User).filter_by(user_id=update.effective_user.id).first()
        if not user:
            await update.message.reply_text("❌ /start")
            return
        
        # Проверка наличия металлоискателя
        available = get_item_count(user, 'metal_detector')
        if available == 0:
            await update.message.reply_text(
                "🔍 *У вас нет металлоискателя!*\n\n"
                "Купить можно в магазине: `/buy metal_detector`\n"
                "Или найти в легендарных сундуках.",
                parse_mode='Markdown'
            )
            return
        
        # Проверка кулдауна
        remaining = get_metal_detector_cooldown(user, datetime.now())
        if remaining.total_seconds() > 0:
            hours = remaining.seconds // 3600
            minutes = (remaining.seconds % 3600) // 60
            await update.message.reply_text(
                f"🔋 *Металлоискатель разряжен!*\n\n"
                f"⏰ Следующее использование через {hours}ч {minutes}мин.",
                parse_mode='Markdown'
            )
            return
        
        # Бонус от локации
        location = getattr(user, 'location', 'normal')
        chest_mult = 1
        if location == 'military':
            chest_mult = 3
        elif location == 'market':
            chest_mult = 2
        
        # Шанс найти сундук (базовый 10% + бонус локации)
        base_chance = METAL_DETECTOR['chest_chance']
        chance = min(25, base_chance * chest_mult)
        
        # Случайный кулдаун (3-18 часов)
        cooldown_hours = random.randint(METAL_DETECTOR['cooldown_min'], METAL_DETECTOR['cooldown_max'])
        
        user.last_metal_detector = datetime.now()
        user.last_metal_detector_duration = cooldown_hours
        
        # Проверяем, нашёл ли сундук
        if random.random() < chance / 100:
            # Равные шансы на все типы сундуков
            chest_type = random.choice(METAL_DETECTOR['chest_types'])
            chest_names = {
                'common': '🟢 Обычный',
                'rare': '🔵 Редкий',
                'epic': '🟣 Эпический',
                'mythic': '🟡 Мифический',
                'legendary': '🟠 Легендарный'
            }
            
            # Добавляем сундук игроку
            if chest_type == 'common':
                user.chest_common += 1
            elif chest_type == 'rare':
                user.chest_rare += 1
            elif chest_type == 'epic':
                user.chest_epic += 1
            elif chest_type == 'mythic':
                user.chest_mythic += 1
            elif chest_type == 'legendary':
                user.chest_legendary += 1
            
            session.commit()
            
            safe_log_user_action(
                user.user_id, user.username, 'metal_detector_found',
                item=chest_type
            )
            
            await update.message.reply_text(
                f"🔍 *Металлоискатель пискнул!*\n\n"
                f"✨ Вы нашли {chest_names[chest_type]} сундук! ✨\n\n"
                f"📦 Сундук добавлен в инвентарь. Используйте `/chest open {chest_type}` чтобы открыть.\n\n"
                f"🔋 Металлоискатель разрядился на {cooldown_hours} часов.",
                parse_mode='Markdown'
            )
        else:
            session.commit()
            
            await update.message.reply_text(
                f"🔍 *Металлоискатель молчит...*\n\n"
                f"😔 Ничего не найдено.\n\n"
                f"🔋 Металлоискатель разрядился на {cooldown_hours} часов.",
                parse_mode='Markdown'
            )
        
    except Exception as e:
        logger.error(f"Error in use_metal_detector: {e}")
        session.rollback()
        await update.message.reply_text("❌ Ошибка")
    finally:
        session.close()
