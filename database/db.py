"""
Модуль для работы с базой данных
✅ ОБНОВЛЕНО: Добавлена функция get_all_users для уведомлений о картах
✅ ОБНОВЛЕНО: Добавлена система ролей (user, operator, admin)
✅ ОБНОВЛЕНО: Добавлены настройки уведомлений per-аккаунт (notification_settings)
"""
import sqlite3
import logging
import json
from typing import Optional, List, Tuple, Dict
from datetime import datetime
from config.settings import DATABASE_NAME, ADMIN_CHAT_ID

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════
# РОЛИ ПОЛЬЗОВАТЕЛЕЙ
# ══════════════════════════════════════════════════════════════
ROLE_USER = 'user'
ROLE_OPERATOR = 'operator'
ROLE_ADMIN = 'admin'

VALID_ROLES = [ROLE_USER, ROLE_OPERATOR, ROLE_ADMIN]

# Ключ для основного аккаунта в notification_settings
NOTIF_KEY_MAIN = 'main'


def init_db():
    """Инициализирует базу данных и применяет миграции"""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()

    # Таблица пользователей
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            profile_url TEXT,
            profile_id TEXT,
            site_nickname TEXT,
            twinks TEXT,
            is_linked INTEGER DEFAULT 0,
            role TEXT DEFAULT 'user',
            notification_settings TEXT DEFAULT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Таблица черного списка
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS blacklist (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            reason TEXT,
            blocked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Таблица карт клуба
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS club_cards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            card_id TEXT UNIQUE,
            card_name TEXT,
            card_rank TEXT DEFAULT '?',
            card_image_url TEXT,
            card_progress TEXT,
            daily_donated TEXT,
            wants_count INTEGER DEFAULT 0,
            owners_count INTEGER DEFAULT 0,
            club_owners TEXT,
            discovered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

        # Таблица логов оператора
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS operator_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            operator_id INTEGER NOT NULL,
            action_type TEXT NOT NULL,
            target_user_id INTEGER,
            target_username TEXT,
            target_first_name TEXT,
            details TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # ✅ НОВАЯ ТАБЛИЦА: Таблица цен на карты
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS card_prices (
            card_id TEXT PRIMARY KEY,
            card_url TEXT UNIQUE NOT NULL,
            price REAL NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Таблица сообщений диалогов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS dialog_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dialog_id TEXT NOT NULL,
            sender_id INTEGER NOT NULL,
            sender_type TEXT NOT NULL,
            message_text TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Индексы
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_operator_logs_operator ON operator_logs(operator_id, created_at DESC)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_operator_logs_action ON operator_logs(action_type, created_at DESC)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_dialog_messages_dialog ON dialog_messages(dialog_id, created_at DESC)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_role ON users(role)')

    # ═══════════════════════════════════════════════════════════
    # МИГРАЦИИ
    # ═══════════════════════════════════════════════════════════

    for col, col_type in [
        ('card_rank',     "TEXT DEFAULT '?'"),
        ('card_progress', 'TEXT'),
        ('daily_donated', 'TEXT'),
    ]:
        try:
            cursor.execute(f'ALTER TABLE club_cards ADD COLUMN {col} {col_type}')
            logger.info(f"Миграция БД: добавлен столбец club_cards.{col}")
        except Exception:
            pass

    for col in ['site_nickname TEXT', 'twinks TEXT', "role TEXT DEFAULT 'user'", 'notification_settings TEXT DEFAULT NULL']:
        try:
            cursor.execute(f'ALTER TABLE users ADD COLUMN {col}')
            col_name = col.split()[0]
            logger.info(f"Миграция БД: добавлен столбец users.{col_name}")
        except Exception:
            pass

    # Назначение роли admin для ADMIN_CHAT_ID
    try:
        admin_id = int(ADMIN_CHAT_ID)
        cursor.execute('SELECT role FROM users WHERE user_id = ?', (admin_id,))
        result = cursor.fetchone()
        if result:
            if result[0] != ROLE_ADMIN:
                cursor.execute('UPDATE users SET role = ? WHERE user_id = ?', (ROLE_ADMIN, admin_id))
                logger.info(f"Миграция БД: пользователь {admin_id} назначен администратором")
        else:
            cursor.execute(
                'INSERT INTO users (user_id, role, username, first_name, last_name) VALUES (?, ?, ?, ?, ?)',
                (admin_id, ROLE_ADMIN, 'admin', 'Administrator', '')
            )
            logger.info(f"Миграция БД: создана запись администратора {admin_id}")
        conn.commit()
    except Exception as e:
        logger.debug(f"Миграция admin role: {e}")

    # Миграция старой таблицы twinks
    try:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='twinks'")
        if cursor.fetchone():
            logger.info("Обнаружена старая таблица twinks, выполняю миграцию...")
            cursor.execute('SELECT user_id, profile_url, profile_id, site_nickname FROM twinks')
            old_twinks = cursor.fetchall()
            user_twinks_map = {}
            for uid, profile_url, profile_id, site_nickname in old_twinks:
                if uid not in user_twinks_map:
                    user_twinks_map[uid] = []
                user_twinks_map[uid].append({'profile_url': profile_url, 'profile_id': profile_id, 'site_nickname': site_nickname})
            for uid, twinks_list in user_twinks_map.items():
                cursor.execute('UPDATE users SET twinks = ? WHERE user_id = ?', (json.dumps(twinks_list, ensure_ascii=False), uid))
            cursor.execute('DROP TABLE twinks')
            logger.info(f"Миграция twinks завершена: {len(old_twinks)} твинов")
    except Exception as e:
        logger.debug(f"Миграция twinks: {e}")

    conn.commit()
    conn.close()
    logger.info("База данных инициализирована")


# ══════════════════════════════════════════════════════════════
# УПРАВЛЕНИЕ РОЛЯМИ
# ══════════════════════════════════════════════════════════════

def get_user_role(user_id: int) -> str:
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT role FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    if not result:
        return ROLE_USER
    role = result[0]
    return role if role in VALID_ROLES else ROLE_USER


def set_user_role(user_id: int, role: str) -> bool:
    if role not in VALID_ROLES:
        logger.error(f"Попытка установить невалидную роль: {role}")
        return False
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT user_id FROM users WHERE user_id = ?', (user_id,))
    exists = cursor.fetchone()
    if exists:
        cursor.execute('UPDATE users SET role = ? WHERE user_id = ?', (role, user_id))
    else:
        cursor.execute('INSERT INTO users (user_id, role, username, first_name, last_name) VALUES (?, ?, ?, ?, ?)', (user_id, role, '', '', ''))
    conn.commit()
    conn.close()
    logger.info(f"Роль пользователя {user_id} изменена на '{role}'")
    return True


def is_user(user_id: int) -> bool:
    return get_user_role(user_id) == ROLE_USER

def is_operator(user_id: int) -> bool:
    return get_user_role(user_id) == ROLE_OPERATOR

def is_admin(user_id: int) -> bool:
    return get_user_role(user_id) == ROLE_ADMIN

def is_staff(user_id: int) -> bool:
    return get_user_role(user_id) in [ROLE_OPERATOR, ROLE_ADMIN]


def get_all_users_by_role(role: str = None) -> List[Tuple]:
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    if role:
        cursor.execute('SELECT user_id, username, first_name, role FROM users WHERE role = ? ORDER BY created_at DESC', (role,))
    else:
        cursor.execute('SELECT user_id, username, first_name, role FROM users ORDER BY created_at DESC')
    result = cursor.fetchall()
    conn.close()
    return result


def get_staff_list() -> List[Dict]:
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT user_id, username, first_name, last_name, role FROM users
        WHERE role IN ('operator', 'admin')
        ORDER BY CASE role WHEN 'admin' THEN 1 WHEN 'operator' THEN 2 END, created_at ASC
    ''')
    rows = cursor.fetchall()
    conn.close()
    return [{'user_id': r[0], 'username': r[1], 'first_name': r[2], 'last_name': r[3], 'role': r[4]} for r in rows]


# ══════════════════════════════════════════════════════════════
# ✅ НАСТРОЙКИ УВЕДОМЛЕНИЙ
# ══════════════════════════════════════════════════════════════

def _build_default_notification_settings(user_id: int) -> Dict[str, bool]:
    """
    Строит словарь настроек уведомлений по умолчанию (всё включено).
    
    Формат:
    {
        "main": True,          # основной аккаунт
        "123456": True,        # твин с profile_id=123456
        ...
    }
    """
    settings = {NOTIF_KEY_MAIN: True}

    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT twinks FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()

    if result and result[0]:
        try:
            twinks = json.loads(result[0])
            for t in twinks:
                pid = t.get('profile_id')
                if pid:
                    settings[str(pid)] = True
        except Exception as e:
            logger.error(f"Ошибка парсинга твинов при построении настроек: {e}")

    return settings


def get_notification_settings(user_id: int) -> Dict[str, bool]:
    """
    Возвращает настройки уведомлений пользователя.
    Если настроек нет — создаёт и сохраняет дефолтные (всё включено).
    Если в настройках отсутствуют ключи для новых твинов — добавляет их.
    """
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT notification_settings, twinks FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()

    if not result:
        return {NOTIF_KEY_MAIN: True}

    raw_settings, raw_twinks = result

    # Парсим сохранённые настройки
    settings: Dict[str, bool] = {}
    if raw_settings:
        try:
            settings = json.loads(raw_settings)
        except Exception:
            settings = {}

    # Убеждаемся что main всегда есть
    if NOTIF_KEY_MAIN not in settings:
        settings[NOTIF_KEY_MAIN] = True

    # Добавляем ключи для твинов, если их ещё нет (новые твины по умолчанию включены)
    if raw_twinks:
        try:
            twinks = json.loads(raw_twinks)
            changed = False
            for t in twinks:
                pid = str(t.get('profile_id', ''))
                if pid and pid not in settings:
                    settings[pid] = True
                    changed = True
            if changed:
                _save_notification_settings(user_id, settings)
        except Exception as e:
            logger.error(f"Ошибка синхронизации настроек уведомлений с твинами: {e}")

    return settings


def _save_notification_settings(user_id: int, settings: Dict[str, bool]):
    """Сохраняет настройки уведомлений в БД"""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute(
        'UPDATE users SET notification_settings = ? WHERE user_id = ?',
        (json.dumps(settings, ensure_ascii=False), user_id)
    )
    conn.commit()
    conn.close()


def toggle_notification(user_id: int, profile_key: str) -> bool:
    """
    Переключает настройку уведомления для конкретного аккаунта.
    
    Args:
        user_id: Telegram ID пользователя
        profile_key: 'main' для основного аккаунта или profile_id (строка) для твина
    
    Returns:
        bool: Новое значение настройки (True = включено, False = выключено)
    """
    settings = get_notification_settings(user_id)
    current_value = settings.get(str(profile_key), True)
    new_value = not current_value
    settings[str(profile_key)] = new_value
    _save_notification_settings(user_id, settings)
    logger.info(f"Пользователь {user_id}: уведомления для '{profile_key}' → {'вкл' if new_value else 'выкл'}")
    return new_value


def get_account_notification_enabled(user_id: int, profile_key: str) -> bool:
    """
    Проверяет, включены ли уведомления для конкретного аккаунта.
    По умолчанию True.
    """
    settings = get_notification_settings(user_id)
    return settings.get(str(profile_key), True)


def init_notification_settings_for_user(user_id: int):
    """
    Инициализирует настройки уведомлений для нового/обновлённого пользователя.
    Вызывается при сохранении пользователя и добавлении твина.
    """
    settings = get_notification_settings(user_id)
    _save_notification_settings(user_id, settings)


# ══════════════════════════════════════════════════════════════
# ПОЛЬЗОВАТЕЛИ
# ══════════════════════════════════════════════════════════════

def is_blacklisted(user_id: int) -> bool:
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT user_id FROM blacklist WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result is not None


def add_to_blacklist(user_id: int, username: str = "", first_name: str = "", reason: str = ""):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute('INSERT OR REPLACE INTO blacklist (user_id, username, first_name, reason) VALUES (?, ?, ?, ?)', (user_id, username, first_name, reason))
    conn.commit()
    conn.close()
    logger.info(f"Пользователь {user_id} добавлен в черный список")


def remove_from_blacklist(user_id: int):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM blacklist WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()
    logger.info(f"Пользователь {user_id} удален из черного списка")


def get_blacklist() -> List[Tuple]:
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT user_id, username, first_name, reason, blocked_at FROM blacklist ORDER BY blocked_at DESC')
    result = cursor.fetchall()
    conn.close()
    return result


def save_user(user_id: int, username: str, first_name: str, last_name: str,
              profile_url: str = None, profile_id: str = None,
              site_nickname: str = None, is_linked: bool = False):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()

    cursor.execute('SELECT twinks, role, notification_settings FROM users WHERE user_id = ?', (user_id,))
    existing = cursor.fetchone()
    existing_twinks = existing[0] if existing else None
    existing_role = existing[1] if existing else ROLE_USER
    existing_notif = existing[2] if existing else None

    cursor.execute('''
        INSERT OR REPLACE INTO users
        (user_id, username, first_name, last_name, profile_url, profile_id, site_nickname,
         twinks, is_linked, role, notification_settings)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (user_id, username, first_name, last_name, profile_url, profile_id, site_nickname,
          existing_twinks, 1 if is_linked else 0, existing_role, existing_notif))
    conn.commit()
    conn.close()

    # ✅ Инициализируем/синхронизируем настройки уведомлений
    if is_linked:
        init_notification_settings_for_user(user_id)

    logger.info(f"Данные пользователя {user_id} сохранены (ник: {site_nickname}, роль: {existing_role})")


def is_user_linked(user_id: int) -> bool:
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT is_linked FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result and result[0] == 1


def get_user_profile_url(user_id: int) -> Optional[str]:
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT profile_url FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None


def get_user_info(user_id: int) -> Optional[Tuple]:
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT user_id, username, first_name, last_name, site_nickname, role FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result


def get_all_users() -> List[Dict]:
    """
    Получает всех привязанных пользователей из БД.
    Используется для проверки владения картами клуба.
    """
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT user_id, username, first_name, last_name, profile_id, twinks, site_nickname, role, notification_settings
        FROM users WHERE is_linked = 1
    ''')
    rows = cursor.fetchall()
    conn.close()

    result = []
    for r in rows:
        notif_raw = r[8] if len(r) > 8 else None
        notif_settings = {}
        if notif_raw:
            try:
                notif_settings = json.loads(notif_raw)
            except Exception:
                notif_settings = {}

        result.append({
            'user_id': r[0],
            'username': r[1],
            'first_name': r[2],
            'last_name': r[3],
            'profile_id': r[4],
            'twinks': r[5],
            'site_nickname': r[6],
            'role': r[7] if len(r) > 7 else ROLE_USER,
            'notification_settings': notif_settings,
        })
    return result


# ══════════════════════════════════════════════════════════════
# ТВИНЫ (ХРАНЯТСЯ В СТОЛБЦЕ users.twinks КАК JSON)
# ══════════════════════════════════════════════════════════════

def add_twink(user_id: int, profile_url: str, profile_id: str, site_nickname: str = None) -> bool:
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT twinks FROM users WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        if not result:
            logger.warning(f"Пользователь {user_id} не найден в БД")
            conn.close()
            return False

        twinks_list = json.loads(result[0]) if result[0] else []

        for twink in twinks_list:
            if twink.get('profile_id') == profile_id:
                logger.warning(f"Твин {profile_id} уже существует для пользователя {user_id}")
                conn.close()
                return False

        twinks_list.append({'profile_url': profile_url, 'profile_id': profile_id, 'site_nickname': site_nickname})
        cursor.execute('UPDATE users SET twinks = ? WHERE user_id = ?', (json.dumps(twinks_list, ensure_ascii=False), user_id))
        conn.commit()
        logger.info(f"Твин добавлен для пользователя {user_id}: {profile_url} (ник: {site_nickname})")
        return True
    except Exception as e:
        logger.error(f"Ошибка добавления твина: {e}")
        return False
    finally:
        conn.close()
        # ✅ После добавления твина — синхронизируем настройки уведомлений
        # (новый твин автоматически получит значение True)
        try:
            init_notification_settings_for_user(user_id)
        except Exception as e:
            logger.error(f"Ошибка инициализации уведомлений после добавления твина: {e}")


def get_user_twinks(user_id: int) -> List[Dict]:
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT twinks FROM users WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        if not result or not result[0]:
            return []
        return json.loads(result[0])
    except Exception as e:
        logger.error(f"Ошибка получения твинов: {e}")
        return []
    finally:
        conn.close()


def remove_twink(user_id: int, profile_id: str) -> bool:
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT twinks FROM users WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        if not result or not result[0]:
            conn.close()
            return False

        twinks_list = json.loads(result[0])
        new_twinks = [t for t in twinks_list if t.get('profile_id') != profile_id]

        if len(new_twinks) == len(twinks_list):
            conn.close()
            return False

        cursor.execute(
            'UPDATE users SET twinks = ? WHERE user_id = ?',
            (json.dumps(new_twinks, ensure_ascii=False) if new_twinks else None, user_id)
        )

        # ✅ Убираем ключ удалённого твина из настроек уведомлений
        cursor.execute('SELECT notification_settings FROM users WHERE user_id = ?', (user_id,))
        notif_result = cursor.fetchone()
        if notif_result and notif_result[0]:
            try:
                notif_settings = json.loads(notif_result[0])
                notif_settings.pop(str(profile_id), None)
                cursor.execute(
                    'UPDATE users SET notification_settings = ? WHERE user_id = ?',
                    (json.dumps(notif_settings, ensure_ascii=False), user_id)
                )
            except Exception as e:
                logger.error(f"Ошибка очистки настроек уведомлений при удалении твина: {e}")

        conn.commit()
        logger.info(f"Твин {profile_id} удален для пользователя {user_id}")
        return True
    except Exception as e:
        logger.error(f"Ошибка удаления твина: {e}")
        return False
    finally:
        conn.close()


def get_twinks_count(user_id: int) -> int:
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT twinks FROM users WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        if not result or not result[0]:
            return 0
        return len(json.loads(result[0]))
    except Exception as e:
        logger.error(f"Ошибка подсчета твинов: {e}")
        return 0
    finally:
        conn.close()


# ══════════════════════════════════════════════════════════════
# УПРАВЛЕНИЕ ЦЕНАМИ КАРТ
# ══════════════════════════════════════════════════════════════

def clear_all_card_prices():
    """Удаляет все цены на карты из БД"""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM card_prices')
    conn.commit()
    conn.close()
    logger.info("Все цены на карты удалены из БД")


def save_card_price(card_url: str, price: float) -> bool:
    """
    Сохраняет цену карты в БД
    
    Args:
        card_url: URL карты (https://mangabuff.ru/cards/XXXXXX/users)
        price: Цена карты
    
    Returns:
        bool: True если успешно, False при ошибке
    """
    import re
    
    # Извлекаем card_id из URL
    match = re.search(r'/cards/(\d+)/', card_url)
    if not match:
        logger.error(f"Невалидный URL карты: {card_url}")
        return False
    
    card_id = match.group(1)
    
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            INSERT OR REPLACE INTO card_prices (card_id, card_url, price, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        ''', (card_id, card_url, price))
        conn.commit()
        logger.info(f"Цена на карту {card_id} сохранена: {price}")
        return True
    except Exception as e:
        logger.error(f"Ошибка сохранения цены карты: {e}")
        return False
    finally:
        conn.close()


def get_card_price(card_id: str) -> Optional[float]:
    """
    Получает цену карты по ID
    
    Args:
        card_id: ID карты (только цифры)
    
    Returns:
        float: Цена карты или None если не найдена
    """
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT price FROM card_prices WHERE card_id = ?', (card_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None


def get_all_card_prices() -> List[Tuple[str, str, float, str]]:
    """
    Получает все цены на карты
    
    Returns:
        List[Tuple]: [(card_id, card_url, price, updated_at), ...]
    """
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT card_id, card_url, price, updated_at FROM card_prices ORDER BY updated_at DESC')
    result = cursor.fetchall()
    conn.close()
    return result


def get_card_prices_count() -> int:
    """Возвращает количество цен в БД"""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM card_prices')
    result = cursor.fetchone()[0]
    conn.close()
    return result


# ══════════════════════════════════════════════════════════════
# КАРТЫ КЛУБА
# ══════════════════════════════════════════════════════════════

def save_club_card(card_data: dict):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO club_cards
        (card_id, card_name, card_rank, card_image_url, card_progress, daily_donated,
         wants_count, owners_count, club_owners)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        card_data.get('card_id'),
        card_data.get('card_name'),
        card_data.get('card_rank', '?'),
        card_data.get('card_image_url'),
        card_data.get('card_progress', '?/?'),
        card_data.get('daily_donated', '?/?'),
        card_data.get('wants_count', 0),
        card_data.get('owners_count', 0),
        json.dumps(card_data.get('club_owners', []), ensure_ascii=False),
    ))
    conn.commit()
    conn.close()
    logger.info(f"Карта {card_data.get('card_id')} ({card_data.get('card_name')}, ранг {card_data.get('card_rank', '?')}) сохранена в БД")


def is_club_card_saved(card_id: str) -> bool:
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT card_id FROM club_cards WHERE card_id = ?', (card_id,))
    result = cursor.fetchone()
    conn.close()
    return result is not None


def get_club_card(card_id: str) -> Optional[dict]:
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT card_id, card_name, card_rank, card_image_url, card_progress, daily_donated,
               wants_count, owners_count, club_owners, discovered_at
        FROM club_cards WHERE card_id = ?
    ''', (card_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    return {
        'card_id': row[0], 'card_name': row[1], 'card_rank': row[2] or '?',
        'card_image_url': row[3], 'card_progress': row[4], 'daily_donated': row[5],
        'wants_count': row[6], 'owners_count': row[7],
        'club_owners': json.loads(row[8]) if row[8] else [],
        'discovered_at': row[9],
    }


def get_all_club_cards() -> List[dict]:
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT card_id, card_name, card_rank, card_image_url, card_progress, daily_donated,
               wants_count, owners_count, club_owners, discovered_at
        FROM club_cards ORDER BY discovered_at DESC
    ''')
    rows = cursor.fetchall()
    conn.close()
    return [
        {
            'card_id': r[0], 'card_name': r[1], 'card_rank': r[2] or '?',
            'card_image_url': r[3], 'card_progress': r[4], 'daily_donated': r[5],
            'wants_count': r[6], 'owners_count': r[7],
            'club_owners': json.loads(r[8]) if r[8] else [],
            'discovered_at': r[9],
        }
        for r in rows
    ]


# ══════════════════════════════════════════════════════════════
# ЛОГИ ДЕЙСТВИЙ ОПЕРАТОРА
# ══════════════════════════════════════════════════════════════

def log_operator_action(operator_id: int, action_type: str, target_user_id: int = None,
                        target_username: str = None, target_first_name: str = None, details: str = None):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO operator_logs (operator_id, action_type, target_user_id, target_username, target_first_name, details)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (operator_id, action_type, target_user_id, target_username, target_first_name, details))
    conn.commit()
    conn.close()
    logger.debug(f"Лог оператора {operator_id}: {action_type}")


def get_operator_logs(operator_id: int = None, action_type: str = None, limit: int = 100, offset: int = 0) -> List[Tuple]:
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    query = 'SELECT * FROM operator_logs WHERE 1=1'
    params = []
    if operator_id:
        query += ' AND operator_id = ?'
        params.append(operator_id)
    if action_type:
        query += ' AND action_type = ?'
        params.append(action_type)
    query += ' ORDER BY created_at DESC LIMIT ? OFFSET ?'
    params.extend([limit, offset])
    cursor.execute(query, params)
    result = cursor.fetchall()
    conn.close()
    return result


def get_operator_stats(operator_id: int) -> dict:
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM operator_logs WHERE operator_id = ?', (operator_id,))
    total_actions = cursor.fetchone()[0]
    cursor.execute('SELECT action_type, COUNT(*) FROM operator_logs WHERE operator_id = ? GROUP BY action_type', (operator_id,))
    actions_by_type = dict(cursor.fetchall())
    cursor.execute('SELECT COUNT(*) FROM operator_logs WHERE operator_id = ? AND action_type = ?', (operator_id, 'dialog_start'))
    total_dialogs = cursor.fetchone()[0]
    cursor.execute('SELECT COUNT(*) FROM operator_logs WHERE operator_id = ? AND action_type = ?', (operator_id, 'user_blocked'))
    total_blocks = cursor.fetchone()[0]
    cursor.execute('SELECT MIN(created_at) FROM operator_logs WHERE operator_id = ?', (operator_id,))
    first_action = cursor.fetchone()[0]
    conn.close()
    return {'total_actions': total_actions, 'actions_by_type': actions_by_type, 'total_dialogs': total_dialogs, 'total_blocks': total_blocks, 'first_action': first_action}


# ══════════════════════════════════════════════════════════════
# СООБЩЕНИЯ ДИАЛОГОВ
# ══════════════════════════════════════════════════════════════

def save_dialog_message(dialog_id: str, sender_id: int, sender_type: str, message_text: str):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute('INSERT INTO dialog_messages (dialog_id, sender_id, sender_type, message_text) VALUES (?, ?, ?, ?)', (dialog_id, sender_id, sender_type, message_text))
    conn.commit()
    conn.close()


def get_dialog_messages(dialog_id: str, limit: int = 100) -> List[Tuple]:
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM dialog_messages WHERE dialog_id = ? ORDER BY created_at ASC LIMIT ?', (dialog_id, limit))
    result = cursor.fetchall()
    conn.close()
    return result


def get_dialog_stats(dialog_id: str) -> dict:
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM dialog_messages WHERE dialog_id = ?', (dialog_id,))
    total_messages = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM dialog_messages WHERE dialog_id = ? AND sender_type = 'operator'", (dialog_id,))
    operator_messages = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM dialog_messages WHERE dialog_id = ? AND sender_type = 'user'", (dialog_id,))
    user_messages = cursor.fetchone()[0]
    cursor.execute('SELECT MIN(created_at), MAX(created_at) FROM dialog_messages WHERE dialog_id = ?', (dialog_id,))
    first_msg, last_msg = cursor.fetchone()
    conn.close()
    return {'total_messages': total_messages, 'operator_messages': operator_messages, 'user_messages': user_messages, 'first_message': first_msg, 'last_message': last_msg}