# main.py - Запуск и регистрация команд
# Версия: 4.0.0 (ALPHA)

import os
import sys
import glob
import shutil
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram.ext import CommandHandler, MessageHandler, filters
from telegram import Update
from telegram.ext import ContextTypes

from config import logger, TOKEN, CASINO_PUBLIC_CHANCE, CASINO_PUBLIC_CASH_MULT, SHOP_LIMITS, BACKUP_DIR, BACKUP_RETENTION_DAYS
from core import backups, restore_backup, backup_now, auto_backup, is_admin, send_to_private, check_and_restore_db, get_latest_backup, restore_from_backup

# Основные команды
from user import start, help_command, profile, stats, achievements, announce, phase_info, class_command, class_info
from collect import collect, hunt, locate, pet_command, metro
from money import shop, buy, sell, equip, casino, exchange, craft, inv, use_item
from clan import clan_command, radion, radio, radio_register_group, aradio, load_radio_groups
from chest import chest_command
from factory import factory, afactory
from admin import (
    admin_giveme, admin_phase, admin_give, admin_take, admin_setlevel,
    admin_cd, admin_resethunt, admin_item, admin_pets, admin_manage, admins,
    admin_classes, call, lscall, admin_hide, top_command, acasino,
    advice_handler, gchest, admin_players, sale, check_user, admin_reset,
    admin_backpack, admin_effect_clear
)

# Дополнительные механики из dop.py
from dop import lab, effect_command, effect_clear, use_metal_detector

# Создаём шедулер
scheduler = AsyncIOScheduler()


# ==================== КОМАНДА ВОССТАНОВЛЕНИЯ ====================

async def restore_last(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Восстановить последний бэкап (админ)"""
    if not await is_admin(update, context):
        await update.message.reply_text("❌ Нет прав!")
        return
    
    latest = get_latest_backup()
    if not latest:
        await update.message.reply_text("❌ Нет доступных бэкапов!")
        return
    
    auto_backup()
    
    if restore_from_backup(latest):
        await update.message.reply_text("✅ *База восстановлена из бэкапа!*\n🔄 Бот будет перезапущен...", parse_mode='Markdown')
        os._exit(0)
    else:
        await update.message.reply_text("❌ *Ошибка восстановления!*", parse_mode='Markdown')


# ==================== РЕГИСТРАЦИЯ КОМАНД ====================

def register_handlers(app):
    """Регистрация всех обработчиков команд"""
    
    # Основные команды пользователя
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("profile", profile))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("achievements", achievements))
    app.add_handler(CommandHandler("announce", announce))
    app.add_handler(CommandHandler("phase_info", phase_info))
    
    # Ресурсы и охота
    app.add_handler(CommandHandler("collect", collect))
    app.add_handler(CommandHandler("hunt", hunt))
    app.add_handler(CommandHandler("locate", locate))
    app.add_handler(CommandHandler("pet", pet_command))
    app.add_handler(CommandHandler("metro", metro))  # НОВАЯ КОМАНДА!
    
    # Экономика
    app.add_handler(CommandHandler("shop", shop))
    app.add_handler(CommandHandler("buy", buy))
    app.add_handler(CommandHandler("sell", sell))
    app.add_handler(CommandHandler("equip", equip))
    app.add_handler(CommandHandler("casino", casino))
    app.add_handler(CommandHandler("exchange", exchange))
    app.add_handler(CommandHandler("craft", craft))
    app.add_handler(CommandHandler("inv", inv))
    app.add_handler(CommandHandler("use", use_item))
    
    # Классы
    app.add_handler(CommandHandler("class", class_command))
    app.add_handler(CommandHandler("class_info", class_info))
    
    # Кланы и радио
    app.add_handler(CommandHandler("clan", clan_command))
    app.add_handler(CommandHandler("radion", radion))
    app.add_handler(CommandHandler("radio", radio))
    app.add_handler(CommandHandler("aradio", aradio))
    
    # Сундуки и фабрики
    app.add_handler(CommandHandler("chest", chest_command))
    app.add_handler(CommandHandler("factory", factory))
    app.add_handler(CommandHandler("afactory", afactory))
    
    # Таблица лидеров
    app.add_handler(CommandHandler("top", top_command))
    app.add_handler(CommandHandler("hide", admin_hide))
    
    # Советы
    app.add_handler(CommandHandler("advice", advice_handler))
    
    # Бэкапы
    app.add_handler(CommandHandler("backups", backups))
    app.add_handler(CommandHandler("restore", restore_backup))
    app.add_handler(CommandHandler("backup_now", backup_now))
    app.add_handler(CommandHandler("restore_last", restore_last))
    
    # Распродажи
    app.add_handler(CommandHandler("sale", sale))
    
    # Дополнительные механики (dop.py) — НОВЫЕ КОМАНДЫ!
    app.add_handler(CommandHandler("lab", lab))
    app.add_handler(CommandHandler("effect", effect_command))
    app.add_handler(CommandHandler("effect_clear", effect_clear))
    app.add_handler(CommandHandler("use_metal_detector", use_metal_detector))
    
    # Админские команды
    app.add_handler(CommandHandler("givemeplsadmin", admin_giveme))
    app.add_handler(CommandHandler("phase", admin_phase))
    app.add_handler(CommandHandler("give", admin_give))
    app.add_handler(CommandHandler("take", admin_take))
    app.add_handler(CommandHandler("setlevel", admin_setlevel))
    app.add_handler(CommandHandler("cd", admin_cd))
    app.add_handler(CommandHandler("resethunt", admin_resethunt))
    app.add_handler(CommandHandler("item", admin_item))
    app.add_handler(CommandHandler("pets", admin_pets))
    app.add_handler(CommandHandler("players", admin_players))
    app.add_handler(CommandHandler("admins", admins))
    app.add_handler(CommandHandler("admin", admin_manage))
    app.add_handler(CommandHandler("classes", admin_classes))
    app.add_handler(CommandHandler("call", call))
    app.add_handler(CommandHandler("lscall", lscall))
    app.add_handler(CommandHandler("gchest", gchest))
    app.add_handler(CommandHandler("acasino", acasino))
    app.add_handler(CommandHandler("check", check_user))
    app.add_handler(CommandHandler("reset", admin_reset))
    app.add_handler(CommandHandler("backpack", admin_backpack))  # НОВАЯ АДМИН-КОМАНДА!
    app.add_handler(CommandHandler("effect_clear", admin_effect_clear))  # НОВАЯ АДМИН-КОМАНДА! (для других игроков)
    
    # Обработчик для регистрации групп в радио
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, radio_register_group))


# ==================== ИНИЦИАЛИЗАЦИЯ ====================

def init_bot_data(app):
    """Инициализация данных бота"""
    app.bot_data['phase'] = 1
    app.bot_data['casino_public_chance'] = CASINO_PUBLIC_CHANCE
    app.bot_data['casino_public_cash_mult'] = CASINO_PUBLIC_CASH_MULT
    app.bot_data['radio_groups'] = set()
    app.bot_data['shop_limits'] = SHOP_LIMITS.copy()
    app.bot_data['last_shop_reset'] = datetime.now()
    app.bot_data['sale_discount'] = 0
    app.bot_data['sale_until'] = None
    
    # Загружаем радио-группы из БД
    load_radio_groups(app)
    
    logger.info("📦 Данные бота инициализированы")


# ==================== ЗАПУСК ====================

def main():
    """Запуск бота"""
    from telegram.ext import Application
    
    # Проверка базы данных при запуске
    if not check_and_restore_db():
        logger.critical("❌ Не удалось восстановить базу данных! Бот не может запуститься.")
        return
    
    app = Application.builder().token(TOKEN).build()
    
    init_bot_data(app)
    register_handlers(app)
    
    # Запускаем планировщик для автобэкапов (каждые 15 минут)
    scheduler.add_job(auto_backup, 'interval', minutes=15)
    scheduler.start()
    
    logger.info("🌟 RadCoin Bot 4.0 (ALPHA) запущен! Пустошь ждёт своих героев!")
    logger.info(f"🎰 Настройки казино: шанс {CASINO_PUBLIC_CHANCE}%, множитель x{CASINO_PUBLIC_CASH_MULT}")
    logger.info(f"💾 Автобэкапы каждые 15 минут, хранение {BACKUP_RETENTION_DAYS} дней")
    logger.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    logger.info("✨ НОВОВВЕДЕНИЯ ALPHA 4.0:")
    logger.info("  • 4 уровня энергетиков (Strike/Tornado/Adrenaline/RedBull)")
    logger.info("  • 3 уровня редукторов (Базовый/Продвинутый/Квантовый)")
    logger.info("  • 3 уровня рюкзаков (Маленький/Тактический/Профессиональный)")
    logger.info("  • Металлоискатель (10% шанс найти сундук)")
    logger.info("  • Лаборатория для учёных (/lab)")
    logger.info("  • Метро — хардкорное подземелье (/metro)")
    logger.info("  • Пошаговые бои с аптечками из рюкзака")
    logger.info("  • Классовая война в охоте")
    logger.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    
    app.run_polling()


if __name__ == '__main__':
    main()
