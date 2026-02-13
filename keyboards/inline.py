"""
Модуль клавиатур для бота
✅ ОБНОВЛЕНО: Добавлена кнопка "💎 Твины"
✅ ОБНОВЛЕНО: Кнопка "Отмена" при добавлении твинов
✅ ОБНОВЛЕНО: Клавиатура и текст настроек уведомлений per-аккаунт
"""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton

BTN_PROFILE       = "👤 Профиль"
BTN_NOTIFICATIONS = "🔔 Уведомления"
BTN_WISHLIST      = "💝 Хотелки"
BTN_CONTRACT      = "📋 Договор за ОК"
BTN_CARD_PRICE    = "💳 Узнать цену Карты"
BTN_TWINKS        = "💎 Твины"
BTN_OPERATOR      = "💬 Связь с оператором"
BTN_OPERATOR_COMMANDS = "⚙️ Команды оператора"

REPLY_KEYBOARD_BUTTONS = {
    BTN_PROFILE, BTN_NOTIFICATIONS, BTN_WISHLIST,
    BTN_CONTRACT, BTN_CARD_PRICE, BTN_TWINKS, BTN_OPERATOR, BTN_OPERATOR_COMMANDS
}

ARCANAS = [
    "Шут", "Маг", "Влюбленные", "Справедливость", "Повешенный",
    "Солнце", "Верховный жрец", "Башня", "Луна", "Мир",
    "Императрица", "Колесница", "Звезда", "Смерть", "Сила",
    "Суд", "Император", "Дьявол", "Воздержание", "Отшельник",
    "Верховная жрица", "Колесо Фортуны"
]


def get_reply_keyboard_for_linked_user(is_operator: bool = False):
    keyboard = [
        [KeyboardButton(BTN_PROFILE), KeyboardButton(BTN_NOTIFICATIONS)],
        [KeyboardButton(BTN_WISHLIST), KeyboardButton(BTN_CONTRACT)],
        [KeyboardButton(BTN_CARD_PRICE), KeyboardButton(BTN_TWINKS)],
    ]
    if is_operator:
        keyboard.append([KeyboardButton(BTN_OPERATOR_COMMANDS)])
    else:
        keyboard.append([KeyboardButton(BTN_OPERATOR)])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)


def get_main_menu_keyboard(is_linked: bool = False):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔗 Привязать аккаунт", callback_data='link_account')],
        [InlineKeyboardButton("📝 Подать заявку",      callback_data='submit_application')],
        [InlineKeyboardButton("💬 Связь с оператором", callback_data='contact_operator')],
    ])


def get_back_button():
    return InlineKeyboardMarkup([[InlineKeyboardButton("◀️ В главное меню", callback_data='back_to_menu')]])


# ══════════════════════════════════════════════
# ✅ УВЕДОМЛЕНИЯ
# ══════════════════════════════════════════════

def get_notifications_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """
    Клавиатура настроек уведомлений.
    Каждая строка: [название аккаунта (не кликабельно)] [✅ Вкл / 🔕 Выкл]
    callback_data переключателей:
      toggle_notif_main          — основной аккаунт
      toggle_notif_{profile_id}  — твин
    """
    from database.db import get_notification_settings, get_user_twinks, get_user_info, NOTIF_KEY_MAIN

    settings = get_notification_settings(user_id)
    keyboard = []

    # Основной аккаунт
    user_info = get_user_info(user_id)
    main_nick = (user_info[4] if user_info and len(user_info) > 4 and user_info[4] else "Основной аккаунт")
    main_on = settings.get(NOTIF_KEY_MAIN, True)
    keyboard.append([
        InlineKeyboardButton(f"👤 {main_nick}", callback_data='notif_noop'),
        InlineKeyboardButton("✅ Вкл" if main_on else "🔕 Выкл",
                             callback_data=f'toggle_notif_{NOTIF_KEY_MAIN}'),
    ])

    # Твины
    for twink in get_user_twinks(user_id):
        pid = str(twink.get('profile_id', ''))
        nick = twink.get('site_nickname') or f"User {pid}"
        on = settings.get(pid, True)
        keyboard.append([
            InlineKeyboardButton(f"💎 {nick}", callback_data='notif_noop'),
            InlineKeyboardButton("✅ Вкл" if on else "🔕 Выкл",
                                 callback_data=f'toggle_notif_{pid}'),
        ])

    keyboard.append([InlineKeyboardButton("◀️ Закрыть", callback_data='close_menu')])
    return InlineKeyboardMarkup(keyboard)


def notifications_text(user_id: int) -> str:
    """Текст экрана настроек уведомлений"""
    from database.db import get_notification_settings, get_user_twinks, get_user_info, NOTIF_KEY_MAIN

    settings = get_notification_settings(user_id)
    user_info = get_user_info(user_id)
    main_nick = (user_info[4] if user_info and len(user_info) > 4 and user_info[4] else "Основной аккаунт")
    main_on = settings.get(NOTIF_KEY_MAIN, True)

    lines = [
        "🔔 <b>Настройки уведомлений</b>",
        "",
        "Уведомления приходят, когда у вашего аккаунта есть карта для вклада в клуб.",
        "Вы можете включить или выключить уведомления для каждого аккаунта отдельно.",
        "",
        "<b>Ваши аккаунты:</b>",
        f"{'✅' if main_on else '🔕'} 👤 {main_nick} <i>(основной)</i>",
    ]
    for twink in get_user_twinks(user_id):
        pid = str(twink.get('profile_id', ''))
        nick = twink.get('site_nickname') or f"User {pid}"
        on = settings.get(pid, True)
        lines.append(f"{'✅' if on else '🔕'} 💎 {nick} <i>(твин)</i>")

    lines += ["", "Нажмите кнопку справа от аккаунта, чтобы переключить."]
    return "\n".join(lines)


# ══════════════════════════════════════════════
# ТВИНЫ
# ══════════════════════════════════════════════

def get_twink_question_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Да, хочу привязать", callback_data='twink_yes'),
            InlineKeyboardButton("⏭️ Нет, пропустить",    callback_data='twink_no'),
        ]
    ])


def get_twink_done_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Готово",  callback_data='twink_done')],
        [InlineKeyboardButton("◀️ Отмена", callback_data='cancel_twink_add')]
    ])


def get_twink_manage_keyboard(user_id: int):
    from database.db import get_user_twinks
    twinks = get_user_twinks(user_id)
    if not twinks:
        return InlineKeyboardMarkup([[InlineKeyboardButton("➕ Добавить твин", callback_data='add_twink')]])
    keyboard = []
    for twink in twinks:
        nick = twink.get('site_nickname', f"User {twink.get('profile_id')}")
        keyboard.append([InlineKeyboardButton(f"🗑 Удалить: {nick}", callback_data=f"delete_twink_{twink.get('profile_id')}")])
    keyboard.append([InlineKeyboardButton("➕ Добавить твин", callback_data='add_twink')])
    return InlineKeyboardMarkup(keyboard)


# ══════════════════════════════════════════════
# АНКЕТА НА ВСТУПЛЕНИЕ
# ══════════════════════════════════════════════

def get_app_q1_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отменить анкету", callback_data='back_to_menu')]])

def get_app_back_keyboard(back_step):
    return InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data=f'app_back_{back_step}')]])

def get_fan_question_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Да, я фанат!", callback_data='app_fan_yes'),
         InlineKeyboardButton("❌ Нет",           callback_data='app_fan_no')],
        [InlineKeyboardButton("◀️ Назад",         callback_data='app_back_2')]
    ])

def get_arcana_keyboard():
    rows = []
    for i in range(0, len(ARCANAS), 2):
        row = [InlineKeyboardButton(ARCANAS[i], callback_data=f'app_arcana_{ARCANAS[i]}')]
        if i + 1 < len(ARCANAS):
            row.append(InlineKeyboardButton(ARCANAS[i+1], callback_data=f'app_arcana_{ARCANAS[i+1]}'))
        rows.append(row)
    rows.append([InlineKeyboardButton("◀️ Назад", callback_data='app_back_3')])
    return InlineKeyboardMarkup(rows)

def get_q5_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⏭️ Пропустить", callback_data='app_skip_5')],
        [InlineKeyboardButton("◀️ Назад",       callback_data='app_back_4')],
    ])

def get_app_review_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ Вопрос 1", callback_data='app_edit_1'),
         InlineKeyboardButton("✏️ Вопрос 2", callback_data='app_edit_2')],
        [InlineKeyboardButton("✏️ Вопрос 3", callback_data='app_edit_3'),
         InlineKeyboardButton("✏️ Вопрос 4", callback_data='app_edit_4')],
        [InlineKeyboardButton("✏️ Вопрос 5",              callback_data='app_edit_5')],
        [InlineKeyboardButton("✅ Отправить оператору 🚀", callback_data='app_send')],
    ])


def app_q1_text():
    return "📝 <b>Анкета на вступление</b>\n┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n<b>Вопрос 1 / 5</b>\n\n❓ Почему вы выбрали наш клуб?"

def app_q2_text():
    return "📝 <b>Анкета на вступление</b>\n┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n<b>Вопрос 2 / 5</b>\n\n❓ Отправьте ссылку на ваш аккаунт на MangaBuff\n\n<i>Формат: https://mangabuff.ru/users/XXXXXX</i>"

def app_q3_text():
    return "📝 <b>Анкета на вступление</b>\n┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n<b>Вопрос 3 / 5</b>\n\n❓ Являетесь ли вы фанатом <b>Повелителя тайн</b>?"

def app_q3_arcana_text():
    return "📝 <b>Анкета на вступление</b>\n┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n<b>Вопрос 3.1</b>\n\n❓ Выберите свою <b>путь</b> из списка ниже:"

def app_q4_text():
    return "📝 <b>Анкета на вступление</b>\n┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n<b>Вопрос 4 / 5</b>\n\n❓ Как к вам обращаться?\n\n<i>Введите имя / прозвище / ник  или  местоимения (он/его, она/её)</i>"

def app_q5_text():
    return "📝 <b>Анкета на вступление</b>\n┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n<b>Вопрос 5 / 5</b> <i>(по желанию)</i>\n\n❓ Дополнительное сообщение для оператора\n\n<i>Напишите что-нибудь или нажмите «Пропустить»</i>"

def app_review_text(answers: dict) -> str:
    q3_display = answers.get('q3', '—')
    if q3_display == 'Да':
        q3_display = f"Да  ➜  аркана: <b>{answers.get('q3_arcana', '—')}</b>"
    q5 = answers.get('q5') or "<i>не указано</i>"
    return (
        "📋 <b>Проверьте вашу анкету</b>\n┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n\n"
        f"<b>1. Почему наш клуб?</b>\n{answers.get('q1', '—')}\n\n"
        f"<b>2. Аккаунт MangaBuff:</b>\n{answers.get('q2', '—')}\n\n"
        f"<b>3. Фанат Повелителя тайн:</b> {q3_display}\n\n"
        f"<b>4. Как обращаться:</b> {answers.get('q4', '—')}\n\n"
        f"<b>5. Доп. сообщение:</b>\n{q5}\n\n"
        "┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n"
        "Всё верно? Нажмите <b>«Отправить оператору»</b> или отредактируйте нужный ответ."
    )


# ══════════════════════════════════════════════
# ОПЕРАТОРСКИЕ КЛАВИАТУРЫ
# ══════════════════════════════════════════════

def get_operator_commands_keyboard():
    """Клавиатура команд оператора (ОБНОВЛЕНО: добавлена кнопка загрузки цен)"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Чёрный список",  callback_data='view_blacklist')],
        [InlineKeyboardButton("💬 Список диалогов", callback_data='view_dialogs')],
        [InlineKeyboardButton("💳 Загрузить цены",  callback_data='upload_prices')],  # ← НОВАЯ КНОПКА
        [InlineKeyboardButton("◀️ Закрыть",         callback_data='close_menu')]
    ])


def get_operator_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Черный список", callback_data='view_blacklist')],
        [InlineKeyboardButton("◀️ Назад",         callback_data='back_to_menu')]
    ])

def get_user_action_keyboard(user_id: int, is_blocked: bool = False):
    keyboard = [[InlineKeyboardButton("💬 Ответить", callback_data=f'reply_{user_id}')]]
    if is_blocked:
        keyboard.append([InlineKeyboardButton("✅ Разблокировать", callback_data=f'unblock_{user_id}')])
    else:
        keyboard.append([InlineKeyboardButton("🚫 Заблокировать", callback_data=f'block_{user_id}')])
    return InlineKeyboardMarkup(keyboard)

def get_block_confirmation_keyboard(user_id: int):
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отменить", callback_data=f'cancel_block_{user_id}')]])

def get_blacklist_user_keyboard(user_id: int):
    return InlineKeyboardMarkup([[InlineKeyboardButton("✅ Разблокировать", callback_data=f'unblock_{user_id}')]])

def get_application_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📝 Подать заявку на вступление", callback_data='submit_application')],
        [InlineKeyboardButton("◀️ Назад", callback_data='back_to_menu')]
    ])