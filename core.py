# core.py - Ядро бота (без шедулера и циклических зависимостей)
# Версия: 4.0.0 (ALPHA)

import os
import sys
import glob
import shutil
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import ContextTypes

from config import logger, BACKUP_DIR, BACKUP_RETENTION_DAYS
from database import Session, User


# ==================== ПРОВЕРКА АДМИНА ====================

async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Проверить, является ли пользователь администратором"""
    user_id = update.effective_user.id
    session = Session()
    try:
        user = session.query(User).filter_by(user_id=user_id).first()
        if not user:
            return False
        return user.is_admin and not user.is_blocked
    except Exception as e:
        logger.error(f"Error checking admin: {e}")
        return False
    finally:
        session.close()


# ==================== ОТПРАВКА В ЛИЧКУ ====================

async def send_to_private(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    """Отправляет сообщение в личку, если команда вызвана в группе"""
    try:
        if update.effective_chat.type != 'private':
            await update.message.reply_text("📩 Информация отправлена в личные сообщения.")
            await context.bot.send_message(chat_id=update.effective_user.id, text=text, parse_mode='Markdown')
        else:
            await update.message.reply_text(text, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error sending to private: {e}")


# ==================== СИСТЕМА БЭКАПОВ ====================

def get_latest_backup():
    """Найти самый свежий бэкап"""
    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        return None
    backups = glob.glob(os.path.join(BACKUP_DIR, "radcoin_bot.db.backup_*.db"))
    if not backups:
        return None
    return max(backups, key=os.path.getctime)


def restore_from_backup(backup_path):
    """Восстановить базу из бэкапа"""
    try:
        if not os.path.exists(backup_path):
            return False
        shutil.copy2(backup_path, 'radcoin_bot.db')
        logger.info(f"✅ База данных восстановлена из бэкапа: {backup_path}")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка восстановления: {e}")
        return False


def check_and_restore_db():
    """Проверить базу при запуске и восстановить при необходимости"""
    os.makedirs(BACKUP_DIR, exist_ok=True)
    
    if os.path.exists('radcoin_bot.db'):
        if os.path.getsize('radcoin_bot.db') > 0:
            logger.info("✅ База данных найдена, проверка пройдена")
            return True
        else:
            logger.warning("⚠️ База данных повреждена (0 байт)!")
    
    logger.warning("⚠️ База данных отсутствует или повреждена! Пытаюсь восстановить из бэкапа...")
    
    latest = get_latest_backup()
    if latest and restore_from_backup(latest):
        logger.info("✅ База данных успешно восстановлена из последнего бэкапа")
        return True
    
    logger.warning("⚠️ Бэкапов не найдено. Будет создана новая база данных.")
    return True


def auto_backup():
    """Автоматическое создание бэкапа базы данных (каждые 15 минут)"""
    try:
        os.makedirs(BACKUP_DIR, exist_ok=True)
        
        db_path = 'radcoin_bot.db'
        if not os.path.exists(db_path):
            logger.warning(f"⚠️ База данных не найдена по пути {db_path}, бэкап не создан")
            return
        
        if os.path.getsize(db_path) == 0:
            logger.warning("⚠️ База данных пуста, бэкап не создан")
            return
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_name = f"radcoin_bot.db.backup_{timestamp}.db"
        backup_path = os.path.join(BACKUP_DIR, backup_name)
        shutil.copy2(db_path, backup_path)
        
        # Удаляем старые бэкапы (кроме последнего)
        backups = sorted(glob.glob(os.path.join(BACKUP_DIR, "radcoin_bot.db.backup_*.db")))
        cutoff = datetime.now() - timedelta(days=BACKUP_RETENTION_DAYS)
        
        # Оставляем последний бэкап всегда, даже если он старый
        for i, backup in enumerate(backups[:-1]):  # не трогаем самый новый
            try:
                date_str = backup.split('_')[-1].replace('.db', '')
                backup_date = datetime.strptime(date_str, '%Y%m%d_%H%M%S')
                if backup_date < cutoff:
                    os.remove(backup)
                    logger.info(f"🗑️ Удалён старый бэкап: {os.path.basename(backup)}")
            except (ValueError, IndexError) as e:
                logger.warning(f"⚠️ Не удалось разобрать имя бэкапа: {backup}")
                continue
            except Exception as e:
                logger.error(f"❌ Ошибка при удалении старого бэкапа: {e}")
        
        size = os.path.getsize(backup_path) / 1024
        logger.info(f"💾 Автобэкап создан: {backup_name} ({size:.1f} КБ)")
        
    except Exception as e:
        logger.error(f"❌ Ошибка автобэкапа: {e}")


# ==================== КОМАНДЫ БЭКАПОВ ====================

def escape_markdown(text: str) -> str:
    """Экранирует спецсимволы для Markdown"""
    if not text:
        return ""
    chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for ch in chars:
        text = text.replace(ch, f'\\{ch}')
    return text


async def backups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Список бэкапов (админ)"""
    if not await is_admin(update, context):
        await update.message.reply_text("❌ Нет прав!")
        return
    
    try:
        if not os.path.exists(BACKUP_DIR):
            os.makedirs(BACKUP_DIR, exist_ok=True)
            await update.message.reply_text("📋 *Нет бэкапов*", parse_mode='Markdown')
            return
        
        backups_list = sorted(glob.glob(os.path.join(BACKUP_DIR, "radcoin_bot.db.backup_*.db")))
        if not backups_list:
            await update.message.reply_text("📋 *Нет бэкапов*", parse_mode='Markdown')
            return
        
        text = "💾 *Список бэкапов*\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        for i, backup in enumerate(backups_list[-10:], 1):
            backup_name = os.path.basename(backup)
            size = os.path.getsize(backup) / 1024
            safe_name = escape_markdown(backup_name)
            text += f"{i}. `{safe_name}` — {size:.1f} КБ\n"
        
        text += "\n📌 /restore [имя] — восстановить\n📌 /restore_last — восстановить последний\n📌 /backup_now — создать бэкап"
        await update.message.reply_text(text, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Error in backups: {e}")
        await update.message.reply_text("❌ Ошибка")


async def restore_backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Восстановить конкретный бэкап (админ)"""
    if not await is_admin(update, context):
        await update.message.reply_text("❌ Нет прав!")
        return
    
    if not context.args:
        await update.message.reply_text("❌ /restore [имя_бэкапа]")
        return
    
    backup_name = context.args[0]
    backup_name = os.path.basename(backup_name)
    backup_path = os.path.join(BACKUP_DIR, backup_name)
    
    if not os.path.exists(backup_path):
        await update.message.reply_text(f"❌ Бэкап `{escape_markdown(backup_name)}` не найден!", parse_mode='Markdown')
        return
    
    # Создаём бэкап текущей базы перед восстановлением
    auto_backup()
    
    if restore_from_backup(backup_path):
        await update.message.reply_text(f"✅ *База данных восстановлена из бэкапа!*\n🔄 Бот будет перезапущен...", parse_mode='Markdown')
        # Принудительно завершаем процесс для перезапуска
        os._exit(0)
    else:
        await update.message.reply_text("❌ *Ошибка восстановления!*", parse_mode='Markdown')


async def restore_last(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Восстановить последний бэкап (админ)"""
    if not await is_admin(update, context):
        await update.message.reply_text("❌ Нет прав!")
        return
    
    latest = get_latest_backup()
    if not latest:
        await update.message.reply_text("❌ Нет доступных бэкапов!")
        return
    
    # Создаём бэкап текущей базы перед восстановлением
    auto_backup()
    
    if restore_from_backup(latest):
        await update.message.reply_text(f"✅ *База данных восстановлена из последнего бэкапа!*\n🔄 Бот будет перезапущен...", parse_mode='Markdown')
        # Принудительно завершаем процесс для перезапуска
        os._exit(0)
    else:
        await update.message.reply_text("❌ *Ошибка восстановления!*", parse_mode='Markdown')


async def backup_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Создать бэкап сейчас (админ)"""
    if not await is_admin(update, context):
        await update.message.reply_text("❌ Нет прав!")
        return
    
    try:
        db_path = 'radcoin_bot.db'
        if not os.path.exists(db_path):
            await update.message.reply_text("❌ База данных не найдена!")
            return
        
        os.makedirs(BACKUP_DIR, exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_name = f"radcoin_bot.db.backup_{timestamp}.db"
        backup_path = os.path.join(BACKUP_DIR, backup_name)
        shutil.copy2(db_path, backup_path)
        
        size = os.path.getsize(backup_path) / 1024
        safe_name = escape_markdown(backup_name)
        await update.message.reply_text(f"✅ *Бэкап создан:* `{safe_name}` ({size:.1f} КБ)", parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Error in backup_now: {e}")
        await update.message.reply_text("❌ Ошибка")
