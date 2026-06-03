# collect.py - Сбор, охота, локации, питомцы, метро
# Версия: 4.0.0 (ALPHA)

import random
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import ContextTypes

from config import (
    logger, MAX_LEVEL, get_random_interval, calculate_reward,
    calculate_experience, get_exp_for_level, ENERGY_DRINKS, REDUCERS, BACKPACKS,
    get_energy_bonus, get_reducer_bonus
)
from core import send_to_private
from database import Session, User, Clan
from utils import (
    get_equipped, get_item_count, add_item_to_inventory,
    remove_item_from_inventory, apply_class_bonus,
    calculate_survive_chance, check_achievements,
    log_user_action, save_equipped, get_backpack, get_medkits_in_backpack,
    add_medkits_to_backpack, remove_medkits_from_backpack
)

# Новые импорты для атмосферных сообщений
import messages
import battle
from messages import random_message, LOCATION_MESSAGES, METRO_ENCOUNTER_MESSAGES, HUNT_MUTANT_MESSAGES, HUNT_HUMAN_MESSAGES, BATTLE_RESULTS
from battle import get_battle_message, get_enemy_type


# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

def escape_markdown(text: str) -> str:
    """Экранирует спецсимволы для Markdown"""
    if not text:
        return ""
    chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for ch in chars:
        text = text.replace(ch, f'\\{ch}')
    return text


# ==================== СБОР РЕСУРСОВ ====================

async def collect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сбор ресурсов с учётом новых рюкзаков и энергетиков"""
    user_id = update.effective_user.id
    username = update.effective_user.username
    session = Session()
    try:
        user = session.query(User).filter_by(user_id=user_id).first()
        if not user:
            user = User(user_id=user_id, username=username)
            session.add(user)
            session.commit()

        equipped = get_equipped(user)
        now = datetime.now()

        if user.next_collection_time and now < user.next_collection_time:
            remaining = user.next_collection_time - now
            hours = remaining.seconds // 3600
            minutes = (remaining.seconds % 3600) // 60
            await update.message.reply_text(f"⏰ *Следующий сбор через {hours}ч {minutes}мин.*", parse_mode='Markdown')
            return

        actual_level = min(user.level, MAX_LEVEL)
        base_rc = calculate_reward(actual_level)
        exp_gain = calculate_experience()

        # Бонусы локации
        location = getattr(user, 'location', 'normal')
        rc_mult = rf_mult = exp_mult = pet_mult = chest_mult = 1
        location_msg = ""

        # Получаем атмосферное сообщение для локации
        if location in LOCATION_MESSAGES:
            location_msg = random_message(LOCATION_MESSAGES[location])
        else:
            location_msg = "🌍 Пустошь — вы отправляетесь в знакомые места"

        # Бонусы локации
        if location == 'military':
            chest_mult = 3
            rc_mult = rf_mult = 0
            exp_gain = random.randint(25, 50)
        elif location == 'city':
            rc_mult = 1.5
            rf_mult = 0.5
        elif location == 'wasteland':
            rf_mult = 1.5
            rc_mult = 0.7
        elif location == 'lab':
            exp_mult = 2
            rc_mult = 0.5
        elif location == 'forest':
            pet_mult = 2
            rc_mult = 0.8
            rf_mult = 0
            exp_gain = random.randint(30, 80)
        elif location == 'market':
            rc_mult = 1.2
            rf_mult = 0
            chest_mult = 2
            exp_gain = random.randint(10, 30)

        # Бонус от рюкзака (НОВОЕ!)
        backpack = get_backpack(user)
        if backpack and backpack in BACKPACKS:
            backpack_data = BACKPACKS[backpack]
            rc_mult += backpack_data['rc_bonus'] / 100
            rf_mult += backpack_data['rf_bonus'] / 100

        # Аномалии
        anomaly_msg = ""
        phase = context.bot_data.get('phase', 1)
        if phase >= 3:
            anomaly_roll = random.random()
            if anomaly_roll < 0.1:
                base_rc = int(base_rc * 1.3)
                anomaly_msg = "\n✨ *Аномалия ДОБЫТЧИК!* Добыча +30%! ✨"
            elif anomaly_roll < 0.2:
                anomaly_msg = "\n🕸️ *Аномалия ЛОВЕЦ!* Кто-то наблюдает... 🕸️"
            elif anomaly_roll < 0.2001:
                reduction = random.randint(1, 5)
                actual_level = max(1, actual_level - reduction)
                anomaly_msg = f"\n🧠 *Аномалия СКЛЕРОЗИК!* Потеряно {reduction} уровней! 🧠"

        # Клановый бонус
        clan = None
        if user.clan_id:
            clan = session.query(Clan).filter_by(id=user.clan_id).first()
            if clan:
                exp_gain = int(exp_gain * (1 + clan.exp_bonus * 0.05))

        rc_gain = int(base_rc * rc_mult)
        exp_gain = int(exp_gain * exp_mult)
        fragment_gain = 0

        # Питомцы
        if user.pet == 'рысь':
            rc_gain = int(rc_gain * 1.1)
        if user.pet == 'попугай':
            exp_gain = int(exp_gain * 1.4)

        # Множители
        multiplier = 1
        double_chance = 9
        if clan:
            double_chance += clan.double_bonus
        if random.random() < 0.01:
            multiplier = 5
            user.crit_collects += 1
        elif random.random() < double_chance / 100:
            multiplier = 2
            user.crit_collects += 1
        rc_gain *= multiplier

        # Фрагменты
        fragment_chance = 1
        if user.pet == 'овчарка':
            fragment_chance += 5
        if random.random() < fragment_chance / 100:
            fragment_gain = random.randint(1, 5)
        fragment_gain = int(fragment_gain * rf_mult)

        # Бонус класса
        rc_gain, fragment_gain, exp_gain = apply_class_bonus(user, rc_gain, fragment_gain, exp_gain)

        # Кристаллы
        crystal_gain = 0
        if clan:
            crystal_gain = random.randint(1, 5)
            if user.pet == 'пума':
                crystal_gain = int(crystal_gain * 1.5)
            clan.treasury_crystals += crystal_gain

        # Бонусы энергетиков
        energy_bonus = None
        if user.energy_drink_until and user.energy_drink_until > now:
            energy_level = getattr(user, 'energy_drink_level', 'strike')
            energy_data = get_energy_bonus(energy_level)
            rc_gain = int(rc_gain * energy_data['rc_bonus'])
            fragment_gain = int(fragment_gain * energy_data['rf_bonus'])
            crystal_gain = int(crystal_gain * energy_data['crystal_bonus'])
            energy_bonus = energy_data

        user.radcoins += rc_gain
        user.radfragments += fragment_gain
        user.experience += exp_gain
        user.total_collects += 1
        user.total_rc_earned += rc_gain
        if rc_gain > user.best_collect:
            user.best_collect = rc_gain

        level_up = False
        while user.level < MAX_LEVEL and user.experience >= get_exp_for_level(user.level + 1):
            user.level += 1
            level_up = True

        interval = get_random_interval(user)
        user.last_collection = now
        user.next_collection_time = now + timedelta(minutes=interval)

        last_date = user.last_collect_date.date() if user.last_collect_date else None
        today = now.date()
        if last_date == today - timedelta(days=1):
            user.daily_streak += 1
        elif last_date != today:
            user.daily_streak = 1
        user.last_collect_date = now

        # Питомец
        pet_encounter = None
        if phase >= 2 and user.level >= 2:
            if random.random() < 0.005 * pet_mult:
                pets = ['овчарка', 'волк', 'рысь', 'пума', 'попугай', 'кайот']
                pet_encounter = random.choice(pets)

        # Достижения
        new_achievements = check_achievements(user)

        # Сундуки
        chest_found = None
        if phase >= 2 and chest_mult > 0:
            chest_roll = random.random() * 100
            if chest_roll < 1 * chest_mult:
                user.chest_legendary += 1
                chest_found = "🟠 Легендарный сундук"
            elif chest_roll < 4 * chest_mult:
                user.chest_mythic += 1
                chest_found = "🟡 Мифический сундук"
            elif chest_roll < 8 * chest_mult:
                user.chest_epic += 1
                chest_found = "🟣 Эпический сундук"
            elif chest_roll < 15 * chest_mult:
                user.chest_rare += 1
                chest_found = "🔵 Редкий сундук"
            elif chest_roll < 25 * chest_mult:
                user.chest_common += 1
                chest_found = "🟢 Обычный сундук"

        session.commit()

        log_user_action(user.user_id, user.username, 'collect',
                        amount_rc=rc_gain, amount_rf=fragment_gain, amount_crystals=crystal_gain)

        # Формируем сообщение
        msg = f"{location_msg}\n\n🔍 Вы находите **{rc_gain}** ☢️ *РадКоинов* и получаете **{exp_gain}** ⚠️ *опыта*!"
        
        if multiplier > 1:
            msg += f"\n✨ *УДАЧА!* Множитель x{multiplier}! ✨"
        if fragment_gain > 0:
            msg += f"\n☣️ *Вам везёт!* +{fragment_gain} РадФрагментов!"
        if crystal_gain > 0:
            msg += f"\n💎 *Клановые кристаллы:* +{crystal_gain} RCr!"
        if level_up:
            msg += f"\n🎉 *УРОВЕНЬ ПОВЫШЕН!* Теперь вы {user.level} уровень! 🎉"
        if anomaly_msg:
            msg += anomaly_msg
        if new_achievements:
            msg += f"\n🏆 *Новые достижения:* {', '.join(new_achievements)}! 🏆"
        if energy_bonus:
            msg += f"\n⚡ *{energy_bonus['name']} активен!* Бонусы применены!"
        
        # Бонус от рюкзака в сообщении
        if backpack and backpack in BACKPACKS:
            backpack_data = BACKPACKS[backpack]
            msg += f"\n🎒 *{backpack_data['name']} активен!* +{backpack_data['rc_bonus']}% RC, +{backpack_data['rf_bonus']}% RF!"

        if user.pet:
            pet_msgs = {
                'овчарка': "🐕 *Овчарка помогает находить ценности!*",
                'волк': "🐺 *Волк предупреждает об опасности!*",
                'рысь': "🐈 *Рысь замечает добычу первой!*",
                'пума': "🐆 *Пума приносит удачу!*",
                'попугай': "🦜 *Попугай ускоряет обучение!*",
                'кайот': "🐕 *Кайот сокращает время до сбора вдвое!*"
            }
            msg += f"\n\n{pet_msgs.get(user.pet, '🐾 *Питомец рядом!*')}"

        if pet_encounter:
            msg += f"\n\n🐾 *Вы встречаете {pet_encounter}!*\nИспользуйте `/pet accept` чтобы приручить."
            context.user_data['pending_pet'] = pet_encounter

        next_hours = interval // 60
        next_minutes = interval % 60
        msg += f"\n\n⏰ *Следующий сбор через {next_hours}ч {next_minutes}мин.*"
        if chest_found:
            msg += f"\n\n🎁 *Вы нашли {chest_found}!* /chest open"

        await update.message.reply_text(msg, parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Error in collect: {e}")
        session.rollback()
        await update.message.reply_text("❌ Ошибка при сборе")
    finally:
        session.close()


# ==================== ОХОТА (ПЕРЕРАБОТАННАЯ) ====================

async def hunt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Охота с классовой войной и пошаговыми боями"""
    user_id = update.effective_user.id
    session = Session()
    try:
        user = session.query(User).filter_by(user_id=user_id).first()
        if not user:
            await update.message.reply_text("❌ Сначала /start")
            return
        if user.level < 2:
            await update.message.reply_text("❌ *Охота доступна со 2 уровня*", parse_mode='Markdown')
            return
        
        # Учёные не охотятся
        class_name = getattr(user, 'user_class', 'stalker')
        if class_name == 'scientist':
            await update.message.reply_text(
                "🔬 *Вы учёный!*\n\n"
                "Ваше место — лаборатория. Используйте `/lab` для проведения экспериментов.\n"
                "Охота — удел военных, бандитов и сталкеров.",
                parse_mode='Markdown'
            )
            return
        
        phase = context.bot_data.get('phase', 1)
        if phase < 2:
            await update.message.reply_text("❌ *Охота недоступна!* Фаза 2 или 3", parse_mode='Markdown')
            return

        now = datetime.now()
        
        # Кулдаун с учётом редуктора
        cooldown = timedelta(days=1)
        if user.cooldown_reducer_until and user.cooldown_reducer_until > now:
            reducer_level = getattr(user, 'reducer_level', 'basic')
            reducer_data = get_reducer_bonus(reducer_level)
            cooldown = timedelta(hours=int(24 * reducer_data['cooldown_reduction']))
        if user.pet == 'кайот':
            cooldown = timedelta(hours=12)
        if (user.cooldown_reducer_until and user.cooldown_reducer_until > now) and user.pet == 'кайот':
            cooldown = timedelta(hours=6)

        if user.last_hunt and now - user.last_hunt < cooldown:
            remaining = cooldown - (now - user.last_hunt)
            hours = remaining.seconds // 3600
            minutes = (remaining.seconds % 3600) // 60
            await update.message.reply_text(f"⏰ *Следующая охота через {hours}ч {minutes}мин.*", parse_mode='Markdown')
            return

        equipped = get_equipped(user)
        
        # Броня
        armor_name = "Нет брони"
        armor_aliases = {'броня1': '🟢 Лёгкая броня', 'броня2': '🔵 Утяжеленная броня',
                         'броня3': '🟣 Тактическая броня', 'броня4': '🟠 Тяжёлая броня',
                         'броня5': '🔴 Силовая броня'}
        if equipped.get('armor'):
            armor_name = armor_aliases.get(equipped['armor'], "Броня")

        # Оружие
        weapon_name = "🗡️ Обрез"
        weapon_aliases = {'ружье': '🔫 Ружьё', 'гарпун': '🎣 Гарпун',
                          'винтовка': '🔫 Винтовка', 'гаусс': '⚡ Винтовка Гаусса'}
        if equipped.get('weapon'):
            weapon_name = weapon_aliases.get(equipped['weapon'], "🗡️ Обрез")

        weapon = equipped.get('weapon')
        if weapon == 'гаусс':
            chances = [40, 25, 20, 15]
        elif weapon == 'винтовка':
            chances = [50, 30, 15, 5]
        elif weapon == 'гарпун':
            chances = [70, 20, 9, 1]
        elif weapon == 'ружье':
            chances = [75, 20, 4, 1]
        else:
            chances = [89, 10, 0.99, 0.01]

        # 50% на людей / 50% на мутантов
        encounter_type = random.choice(['human', 'mutant'])
        
        # Шаг 1: Отправка на охоту
        await update.message.reply_text(
            f"🏹 *Охота в Пустоши*\n\n"
            f"Вы крадётесь с {weapon_name}. {armor_name} защищает вас.\n\n"
            f"Ветер гоняет песок, вы всматриваетесь в горизонт...",
            parse_mode='Markdown'
        )
        
        # Шаг 2: Встреча с врагом
        target_level = 1
        reward_rf = 0
        reward_exp = 0
        target_name = ""
        target_desc = ""
        enemy_class_for_reward = None
        
        if encounter_type == 'mutant':
            roll = random.random() * 100
            if roll < chances[0]:
                reward_rf, reward_exp, target_level = 10, 50, 1
                target_name, target_desc = "🧬 *Мутант 1 уровня*", "неуклюжее создание с длинными когтями"
            elif roll < chances[0] + chances[1]:
                reward_rf, reward_exp, target_level = 30, 100, 2
                target_name, target_desc = "🧪 *Мутант 2 уровня*", "крепкий хищник с толстой шкурой"
            elif roll < chances[0] + chances[1] + chances[2]:
                reward_rf, reward_exp, target_level = 100, 250, 3
                target_name, target_desc = "👾 *Мутант 3 уровня*", "мощный зверь, покрытый костяными наростами"
                user.mutants_lvl3 += 1
            else:
                reward_rf, reward_exp, target_level = 1000, 500, 4
                target_name, target_desc = "👑 *БОСС ПУСТОШИ*", "легендарное чудовище, внушающее ужас"
                user.bosses_killed += 1
            
            # Атмосферное сообщение о мутанте
            if target_level in HUNT_MUTANT_MESSAGES:
                mutant_msg = random_message(HUNT_MUTANT_MESSAGES[target_level])
            else:
                mutant_msg = f"Из темноты выпрыгивает {target_name} — {target_desc}!"
            
            await update.message.reply_text(mutant_msg, parse_mode='Markdown')
            
        else:
            # Люди — классовая война
            if class_name == 'military':
                enemy_class = 'bandit'
                enemy_class_display = 'бандитов'
            elif class_name == 'bandit':
                enemy_class = 'stalker'
                enemy_class_display = 'сталкеров'
            else:  # stalker
                enemy_class = 'military'
                enemy_class_display = 'военных'
            
            # Шансы встретить толпу/караван зависят от оружия
            if weapon == 'гаусс':
                human_chances = [60, 30, 10]
            elif weapon == 'винтовка':
                human_chances = [70, 25, 5]
            elif weapon == 'гарпун':
                human_chances = [80, 17, 3]
            elif weapon == 'ружье':
                human_chances = [85, 13, 2]
            else:
                human_chances = [90, 9, 1]
            
            roll = random.random() * 100
            if roll < human_chances[0]:
                reward_rf, target_size = 10, 'одиночка'
                target_name = f"🗡️ *{enemy_class.capitalize()}-одиночка*"
                target_desc = "одинокий враг, патрулирующий территорию"
            elif roll < human_chances[0] + human_chances[1]:
                reward_rf, target_size = 100, 'толпа'
                target_name = f"⚔️ *Толпа {enemy_class_display}*"
                target_desc = "несколько врагов, застигнутых врасплох"
            else:
                reward_rf, target_size = 1000, 'караван'
                target_name = f"🚚 *Караван {enemy_class_display}*"
                target_desc = "хорошо вооружённый отряд с ценным грузом"
            
            reward_exp = 50 if target_size == 'одиночка' else 100 if target_size == 'толпа' else 500
            target_level = 1 if target_size == 'одиночка' else 2 if target_size == 'толпа' else 3
            enemy_class_for_reward = enemy_class
            
            # Атмосферное сообщение о людях
            if enemy_class in HUNT_HUMAN_MESSAGES and target_size in HUNT_HUMAN_MESSAGES[enemy_class]:
                human_msg = random_message(HUNT_HUMAN_MESSAGES[enemy_class][target_size])
            else:
                human_msg = f"Из-за укрытий выходят {target_name} — {target_desc}!"
            
            await update.message.reply_text(human_msg, parse_mode='Markdown')

        user.mutants_killed += 1
        
        # Бонус класса
        if class_name == 'military':
            reward_exp = int(reward_exp * 1.3)
            reward_rf = int(reward_rf * 0.7)
        elif class_name == 'bandit':
            reward_rf = int(reward_rf * 1.4)
            reward_exp = int(reward_exp * 0.75)
        elif class_name == 'scientist':
            reward_exp = int(reward_exp * 1.5)
            reward_rf = int(reward_rf * 1.25)
        
        # Расчёт шанса выживания
        survive_chance = calculate_survive_chance(user, target_level)
        
        # Бонус энергетика к выживанию
        if user.energy_drink_until and user.energy_drink_until > now:
            energy_level = getattr(user, 'energy_drink_level', 'strike')
            energy_data = get_energy_bonus(energy_level)
            survive_chance = min(100, survive_chance + energy_data['survive_bonus'])
        
        # Бой!
        survived = random.random() * 100 <= survive_chance
        
        if not survived:
            # Смерть — теряем оружие (НО не рюкзак!)
            user.deaths += 1
            old_weapon = equipped.get('weapon')
            if old_weapon:
                add_item_to_inventory(user, old_weapon, 1)
            equipped['weapon'] = None
            save_equipped(user, equipped)
            reward_rf = 0
            reward_exp = 0
            
            death_msg = random_message(BATTLE_RESULTS['death_mutant' if encounter_type == 'mutant' else 'death_human'])
            await update.message.reply_text(death_msg, parse_mode='Markdown')
            
        else:
            # Победа
            user.radfragments += reward_rf
            user.experience += reward_exp
            
            # Добавляем трофеи за людей
            if encounter_type == 'human' and enemy_class_for_reward:
                # Случайное оружие
                weapons = ['ружье', 'гарпун', 'винтовка', 'гаусс']
                weapon_drop = random.choice(weapons)
                add_item_to_inventory(user, weapon_drop, 1)
                
                # Случайная броня
                armors = ['броня1', 'броня2', 'броня3', 'броня4', 'броня5']
                armor_drop = random.choice(armors)
                add_item_to_inventory(user, armor_drop, 1)
                
                # Аптечки
                medkit_drop = random.randint(1, 3)
                add_item_to_inventory(user, 'аптечка', medkit_drop)
                
                # Энергетики
                energies = ['strike', 'tornado', 'adrenaline', 'redbull']
                energy_drop = random.choice(energies)
                add_item_to_inventory(user, f'энергетик_{energy_drop}', random.randint(1, 3))
                
                # Редукторы
                reducers = ['basic', 'advanced', 'quantum']
                reducer_drop = random.choice(reducers)
                add_item_to_inventory(user, f'редуктор_{reducer_drop}', random.randint(1, 2))
            
            win_msg = random_message(BATTLE_RESULTS['win_mutant' if encounter_type == 'mutant' else 'win_human'])
            await update.message.reply_text(
                f"{win_msg}\n\n"
                f"💰 *Награда:* +{reward_rf} ☣️ РадФрагментов!\n"
                f"⚠️ *Опыт:* +{reward_exp}!",
                parse_mode='Markdown'
            )
        
        user.last_hunt = now
        check_achievements(user)
        session.commit()

        hours = cooldown.seconds // 3600
        if survived:
            await update.message.reply_text(f"⏰ *Следующая охота через {hours} часов.*", parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Error in hunt: {e}")
        session.rollback()
        await update.message.reply_text("❌ Ошибка при охоте")
    finally:
        session.close()


# ==================== МЕТРО (НОВАЯ КОМАНДА) ====================

async def metro(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Хардкорное подземелье — пошаговые бои с аптечками из рюкзака"""
    user_id = update.effective_user.id
    session = Session()
    try:
        user = session.query(User).filter_by(user_id=user_id).first()
        if not user:
            await update.message.reply_text("❌ Сначала /start")
            return
        
        # Проверка уровня
        if user.level < 10:
            await update.message.reply_text("❌ *Метро доступно с 10 уровня!*", parse_mode='Markdown')
            return
        
        # Проверка фазы
        phase = context.bot_data.get('phase', 1)
        if phase < 2:
            await update.message.reply_text("❌ *Метро недоступно!* Нужна фаза 2 или 3", parse_mode='Markdown')
            return
        
        # Проверка кулдауна метро (отдельный? пока используем last_hunt)
        now = datetime.now()
        cooldown = timedelta(hours=6)  # Метро можно ходить чаще, чем на охоту
        
        if user.last_hunt and now - user.last_hunt < cooldown:
            remaining = cooldown - (now - user.last_hunt)
            hours = remaining.seconds // 3600
            minutes = (remaining.seconds % 3600) // 60
            await update.message.reply_text(f"⏰ *Метро восстановится через {hours}ч {minutes}мин.*", parse_mode='Markdown')
            return
        
        # Шаг 1: Спуск в метро
        metro_location_msg = random_message(LOCATION_MESSAGES.get('metro', LOCATION_MESSAGES['normal']))
        await update.message.reply_text(metro_location_msg, parse_mode='Markdown')
        
        # 40% шанс прохода без боя
        if random.random() < 0.4:
            await update.message.reply_text(
                "🍀 *Вам повезло!*\n\n"
                "Тоннели пусты, вы проходите без единой встречи.\n"
                "Но в следующий раз может не повезти...",
                parse_mode='Markdown'
            )
            user.last_hunt = now
            session.commit()
            return
        
        # 60% — встреча с врагом
        encounter_type = random.choice(['mutant', 'human'])
        
        # Определяем врага
        if encounter_type == 'mutant':
            enemy_name = "мутант 2 уровня"
            enemy_desc = "опасное создание, затаившееся в темноте"
            base_reward_rf = 100
            base_reward_exp = 150
        else:
            # Классовый враг для метро
            class_name = getattr(user, 'user_class', 'stalker')
            if class_name == 'military':
                enemy_class = 'бандит'
            elif class_name == 'bandit':
                enemy_class = 'сталкер'
            else:
                enemy_class = 'военный'
            enemy_name = f"отряд {enemy_class}ов"
            enemy_desc = "вооружённые люди, патрулирующие подземелье"
            base_reward_rf = 150
            base_reward_exp = 100
        
        # Атмосферное сообщение о встрече
        if encounter_type == 'mutant':
            encounter_msg = random_message(METRO_ENCOUNTER_MESSAGES['mutant'])
        else:
            encounter_msg = random_message(METRO_ENCOUNTER_MESSAGES['human'])
        
        await update.message.reply_text(encounter_msg, parse_mode='Markdown')
        
        # Получаем рюкзак и аптечки в нём
        backpack_type = get_backpack(user)
        medkits_in_backpack = get_medkits_in_backpack(user)
        
        if not backpack_type or medkits_in_backpack == 0:
            await update.message.reply_text(
                "💀 *У вас нет аптечек в рюкзаке!*\n\n"
                "Вы не готовы к бою в метро. Положите аптечки в рюкзак командой `/use аптечка [кол-во]`\n"
                "И не забудьте надеть рюкзак через `/equip рюкзак [тип]`",
                parse_mode='Markdown'
            )
            return
        
        # Пошаговый бой
        max_medkits = BACKPACKS.get(backpack_type, {}).get('medkit_slots', 0)
        medkits_used = 0
        battle_round = 0
        survived = False
        
        # Шаг 3: Начало боя
        await update.message.reply_text("⚔️ *БОЙ НАЧАЛСЯ!*\n\nВы готовитесь к схватке...", parse_mode='Markdown')
        
        # Цикл боя с аптечками
        while medkits_used < medkits_in_backpack and medkits_used < max_medkits:
            battle_round += 1
            
            # Используем аптечку
            if medkits_used == 0:
                await update.message.reply_text(
                    get_battle_message(0, encounter_type == 'mutant', medkits_used, None),
                    parse_mode='Markdown'
                )
            else:
                await update.message.reply_text(
                    get_battle_message(3, encounter_type == 'mutant', medkits_used - 1, None),
                    parse_mode='Markdown'
                )
            
            # Эффект аптечки (25% шанс на спасение за каждую)
            medkit_success = random.random() < 0.25
            
            if medkit_success:
                await update.message.reply_text(
                    get_battle_message(1, encounter_type == 'mutant', medkits_used, True),
                    parse_mode='Markdown'
                )
                medkits_used += 1
                
                # Проверка на победу после успешной аптечки
                if medkits_used >= medkits_in_backpack or medkits_used >= max_medkits:
                    # Последняя надежда
                    await update.message.reply_text(
                        get_battle_message(4, encounter_type == 'mutant', medkits_used - 1, None),
                        parse_mode='Markdown'
                    )
                    final_success = random.random() < 0.25
                    if final_success:
                        survived = True
                        await update.message.reply_text(
                            get_battle_message(7, encounter_type == 'mutant', medkits_used - 1, True),
                            parse_mode='Markdown'
                        )
                    else:
                        survived = False
                        await update.message.reply_text(
                            get_battle_message(7, encounter_type == 'mutant', medkits_used - 1, False),
                            parse_mode='Markdown'
                        )
                    break
                else:
                    # Бой продолжается
                    await update.message.reply_text(
                        get_battle_message(2, encounter_type == 'mutant', medkits_used - 1, None),
                        parse_mode='Markdown'
                    )
            else:
                await update.message.reply_text(
                    get_battle_message(1, encounter_type == 'mutant', medkits_used, False),
                    parse_mode='Markdown'
                )
                medkits_used += 1
                
                # Если аптечки кончились — смерть
                if medkits_used >= medkits_in_backpack or medkits_used >= max_medkits:
                    survived = False
                    await update.message.reply_text(
                        get_battle_message(7, encounter_type == 'mutant', medkits_used - 1, False),
                        parse_mode='Markdown'
                    )
                    break
        
        # Обработка результата боя
        if survived:
            # Победа
            reward_rf = base_reward_rf
            reward_exp = base_reward_exp
            
            # Бонус от энергетика
            if user.energy_drink_until and user.energy_drink_until > now:
                energy_level = getattr(user, 'energy_drink_level', 'strike')
                energy_data = get_energy_bonus(energy_level)
                reward_rf = int(reward_rf * energy_data['rf_bonus'])
                reward_exp = int(reward_exp * 1.1)
            
            user.radfragments += reward_rf
            user.experience += reward_exp
            
            # Трофеи для людей в метро
            if encounter_type == 'human':
                weapons = ['ружье', 'гарпун', 'винтовка', 'гаусс']
                weapon_drop = random.choice(weapons)
                add_item_to_inventory(user, weapon_drop, 1)
                
                armors = ['броня1', 'броня2', 'броня3', 'броня4', 'броня5']
                armor_drop = random.choice(armors)
                add_item_to_inventory(user, armor_drop, 1)
                
                medkit_drop = random.randint(1, 3)
                add_item_to_inventory(user, 'аптечка', medkit_drop)
                
                energies = ['strike', 'tornado', 'adrenaline', 'redbull']
                energy_drop = random.choice(energies)
                add_item_to_inventory(user, f'энергетик_{energy_drop}', random.randint(1, 3))
                
                reducers = ['basic', 'advanced', 'quantum']
                reducer_drop = random.choice(reducers)
                add_item_to_inventory(user, f'редуктор_{reducer_drop}', random.randint(1, 2))
            
            # Снимаем использованные аптечки из рюкзака
            remove_medkits_from_backpack(user, medkits_used)
            
            user.last_hunt = now
            session.commit()
            
            await update.message.reply_text(
                f"🏆 *ПОБЕДА В МЕТРО!*\n\n"
                f"💰 *Награда:* +{reward_rf} ☣️ РадФрагментов!\n"
                f"⚠️ *Опыт:* +{reward_exp}!\n\n"
                f"💊 Использовано аптечек: {medkits_used}\n"
                f"🎒 В рюкзаке осталось: {get_medkits_in_backpack(user)}",
                parse_mode='Markdown'
            )
            
        else:
            # Смерть в метро — суровое наказание
            user.deaths += 1
            
            # Потеря оружия
            equipped = get_equipped(user)
            old_weapon = equipped.get('weapon')
            if old_weapon:
                add_item_to_inventory(user, old_weapon, 1)
            equipped['weapon'] = None
            
            # Потеря рюкзака и всех аптечек в нём
            old_backpack = get_backpack(user)
            if old_backpack:
                add_item_to_inventory(user, old_backpack, 1)
            equipped['backpack'] = None
            save_equipped(user, equipped)
            
            # Потеря 10% длительности активных эффектов
            if user.energy_drink_until and user.energy_drink_until > now:
                duration_left = (user.energy_drink_until - now).total_seconds()
                new_duration = duration_left * 0.9
                user.energy_drink_until = now + timedelta(seconds=new_duration)
            
            if user.cooldown_reducer_until and user.cooldown_reducer_until > now:
                duration_left = (user.cooldown_reducer_until - now).total_seconds()
                new_duration = duration_left * 0.9
                user.cooldown_reducer_until = now + timedelta(seconds=new_duration)
            
            # Увеличение кулдауна сбора на 200%
            if user.next_collection_time and user.next_collection_time > now:
                old_cd = (user.next_collection_time - now).total_seconds()
                new_cd = old_cd * 3  # +200% = ×3
                user.next_collection_time = now + timedelta(seconds=new_cd)
            
            session.commit()
            
            await update.message.reply_text(
                f"💀 *ВЫ ПОГИБЛИ В МЕТРО!*\n\n"
                f"📦 Потеряно: оружие, рюкзак с аптечками\n"
                f"⚡ Эффекты сокращены на 10%\n"
                f"⏰ Кулдаун сбора увеличен на 200%\n\n"
                f"Будьте осторожнее в следующий раз!",
                parse_mode='Markdown'
            )
        
    except Exception as e:
        logger.error(f"Error in metro: {e}")
        session.rollback()
        await update.message.reply_text("❌ Ошибка при походе в метро")
    finally:
        session.close()


# ==================== ЛОКАЦИИ ====================

async def locate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Смена локации (добавлено метро)"""
    if not context.args:
        session = Session()
        try:
            user = session.query(User).filter_by(user_id=update.effective_user.id).first()
            if not user:
                await update.message.reply_text("❌ /start")
                return
            loc = getattr(user, 'location', 'normal')
            loc_names = {'normal': '🌍 Обычная Пустошь', 'military': '🏚️ Военка',
                         'city': '🏙️ Город', 'wasteland': '🌄 Пустошь',
                         'lab': '🧪 Лаба', 'forest': '🌲 Лес', 'market': '🎪 Рынок',
                         'metro': '🚇 Метро'}
            await update.message.reply_text(
                f"🗺️ *Текущая локация:* {loc_names.get(loc, '🌍 Обычная Пустошь')}\n\n"
                f"📌 *Сменить:* `/locate [название]`\n\nДоступные локации:\n"
                f"🌍 `normal` — обычная\n🏚️ `military` — Военка (сундуки x3)\n"
                f"🏙️ `city` — Город (RC +50%)\n🌄 `wasteland` — Пустошь (RF +50%)\n"
                f"🧪 `lab` — Лаба (опыт x2)\n🌲 `forest` — Лес (питомцы x2)\n"
                f"🎪 `market` — Рынок (предметы 10%)\n"
                f"🚇 `metro` — Метро (хардкор, только бои, 10+ уровень)",
                parse_mode='Markdown'
            )
        finally:
            session.close()
        return

    loc = context.args[0].lower()
    valid = ['normal', 'military', 'city', 'wasteland', 'lab', 'forest', 'market', 'metro']
    if loc not in valid:
        await update.message.reply_text("❌ Локации: normal, military, city, wasteland, lab, forest, market, metro")
        return
    session = Session()
    try:
        user = session.query(User).filter_by(user_id=update.effective_user.id).first()
        if not user:
            await update.message.reply_text("❌ /start")
            return
        
        # Проверка уровня для метро
        if loc == 'metro' and user.level < 10:
            await update.message.reply_text("❌ *Метро доступно только с 10 уровня!*", parse_mode='Markdown')
            return
        
        user.location = loc
        session.commit()
        loc_names = {'normal': '🌍 Обычная Пустошь', 'military': '🏚️ Военка',
                     'city': '🏙️ Город', 'wasteland': '🌄 Пустошь',
                     'lab': '🧪 Лаба', 'forest': '🌲 Лес', 'market': '🎪 Рынок',
                     'metro': '🚇 Метро'}
        await update.message.reply_text(f"🗺️ *Локация изменена на {loc_names[loc]}!*", parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error in locate: {e}")
        await update.message.reply_text("❌ Ошибка")
    finally:
        session.close()


# ==================== ПИТОМЦЫ ====================

async def pet_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Управление питомцами"""
    if not context.args:
        await update.message.reply_text(
            "🐾 *Питомцы Пустоши*\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "При сборе есть 0.5% шанс встретить питомца.\n\n"
            "🐕 Овчарка — +5% RF\n🐺 Волк — +10% выживаемость\n"
            "🐈 Рысь — +10% RC\n🐆 Пума — +50% кристаллы\n"
            "🦜 Попугай — +40% опыт\n🐕 Кайот — кулдаун ÷2\n\n"
            "📝 /pet accept — приручить\n📝 /pet deny — отказаться\n📝 /pet bye — отпустить",
            parse_mode='Markdown'
        )
        return
    action = context.args[0].lower()
    if action == "accept":
        await pet_accept(update, context)
    elif action == "deny":
        await pet_deny(update, context)
    elif action == "bye":
        await pet_bye(update, context)
    else:
        await update.message.reply_text("❌ accept, deny, bye")


async def pet_accept(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pending = context.user_data.get('pending_pet')
    if not pending:
        await update.message.reply_text("🐾 *Нет найденного питомца*", parse_mode='Markdown')
        return
    session = Session()
    try:
        user = session.query(User).filter_by(user_id=update.effective_user.id).first()
        if user:
            if user.pet:
                await update.message.reply_text("❌ *У вас уже есть питомец!*", parse_mode='Markdown')
                return
            user.pet = pending
            session.commit()
            log_user_action(user.user_id, user.username, 'pet_accept', item=pending)
            await update.message.reply_text(f"🐾 *Питомец приручён!*\n\n✨ {pending} теперь ваш спутник! ✨", parse_mode='Markdown')
        context.user_data.pop('pending_pet')
    except Exception as e:
        logger.error(f"Error in pet_accept: {e}")
        session.rollback()
        await update.message.reply_text("❌ Ошибка")
    finally:
        session.close()


async def pet_deny(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('pending_pet'):
        context.user_data.pop('pending_pet')
        await update.message.reply_text("🐾 *Питомец убежал*", parse_mode='Markdown')
    else:
        await update.message.reply_text("Нет питомца")


async def pet_bye(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = Session()
    try:
        user = session.query(User).filter_by(user_id=update.effective_user.id).first()
        if not user or not user.pet:
            await update.message.reply_text("❌ *У вас нет питомца*", parse_mode='Markdown')
            return
        if not context.user_data.get('confirm_bye'):
            context.user_data['confirm_bye'] = True
            await update.message.reply_text(f"⚠️ *Отпустить {user.pet}?* /pet bye ещё раз", parse_mode='Markdown')
            return
        context.user_data.pop('confirm_bye')
        pet_name = user.pet
        user.pet = None
        session.commit()
        log_user_action(user.user_id, user.username, 'pet_bye', item=pet_name)
        await update.message.reply_text(f"🐾 *{pet_name} отпущен*", parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error in pet_bye: {e}")
        session.rollback()
        await update.message.reply_text("❌ Ошибка")
    finally:
        session.close()
