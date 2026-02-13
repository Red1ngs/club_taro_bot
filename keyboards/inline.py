"""
Модуль клавиатур для бота
✅ ОБНОВЛЕНО: Добавлена кнопка "💎 Твины"
✅ ОБНОВЛЕНО: Кнопка "Отмена" при добавлении твинов
"""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton

# ──────────────────────────────────────────────
# Тексты кнопок постоянной нижней клавиатуры
# ──────────────────────────────────────────────
BTN_PROFILE      = "👤 Профиль"
BTN_NOTIFICATIONS = "🔔 Уведомления"
BTN_WISHLIST     = "💝 Хотелки"
BTN_CONTRACT     = "📋 Договор за ОК"
BTN_CARD_PRICE   = "💳 Узнать цену Карты"
BTN_TWINKS       = "💎 Твины"
BTN_OPERATOR     = "💬 Связь с оператором"
BTN_OPERATOR_COMMANDS = "⚙️ Команды оператора"

REPLY_KEYBOARD_BUTTONS = {
    BTN_PROFILE, BTN_NOTIFICATIONS, BTN_WISHLIST,
    BTN_CONTRACT, BTN_CARD_PRICE, BTN_TWINKS, BTN_OPERATOR, BTN_OPERATOR_COMMANDS
}

# ──────────────────────────────────────────────
# Список аркан / путей Повелителя тайн
# ──────────────────────────────────────────────
ARCANAS = [
    "Шут", "Маг", "Влюбленные", "Справедливость", "Повешенный",
    "Солнце", "Верховный жрец", "Башня", "Луна", "Мир",
    "Императрица", "Колесница", "Звезда", "Смерть", "Сила",
    "Суд", "Император", "Дьявол", "Воздержание", "Отшельник",
    "Верховная жрица", "Колесо Фортуны"
]


# ══════════════════════════════════════════════
# ПОСТОЯННАЯ НИЖНЯЯ КЛАВИАТУРА (linked-users)
# ══════════════════════════════════════════════

def get_reply_keyboard_for_linked_user(is_operator: bool = False):
    """
    Нижняя клавиатура для привязанных пользователей
    НЕ постоянная - скрывается после использования
    """
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


# ══════════════════════════════════════════════
# ГЛАВНОЕ МЕНЮ (для НЕ привязанных)
# ══════════════════════════════════════════════

def get_main_menu_keyboard(is_linked: bool = False):
    """Возвращает главное меню для непривязанных пользователей (inline)"""
    keyboard = [
        [InlineKeyboardButton("🔗 Привязать аккаунт", callback_data='link_account')],
        [InlineKeyboardButton("📝 Подать заявку",      callback_data='submit_application')],
        [InlineKeyboardButton("💬 Связь с оператором", callback_data='contact_operator')],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_back_button():
    """Кнопка возврата в главное меню"""
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("◀️ В главное меню", callback_data='back_to_menu')]]
    )


# ══════════════════════════════════════════════
# ✅ КНОПКИ ДЛЯ ПРИВЯЗКИ ТВИНОВ
# ══════════════════════════════════════════════

def get_twink_question_keyboard():
    """
    Клавиатура для вопроса о привязке твинов
    "Да" - начинаем привязку
    "Нет" - пропускаем
    """
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Да, хочу привязать", callback_data='twink_yes'),
            InlineKeyboardButton("⏭️ Нет, пропустить", callback_data='twink_no'),
        ]
    ])


def get_twink_done_keyboard():
    """
    ✅ ОБНОВЛЕНО: Кнопки "Готово" и "Отмена" при добавлении твинов.
    "Готово" - завершить добавление (только если хоть один твин был добавлен, иначе = отмена).
    "Отмена" - отменить добавление и вернуться назад.
    """
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Готово", callback_data='twink_done')],
        [InlineKeyboardButton("◀️ Отмена", callback_data='cancel_twink_add')]
    ])


def get_twink_manage_keyboard(user_id: int):
    """
    Клавиатура управления твинами с кнопками для удаления
    """
    from database.db import get_user_twinks
    
    twinks = get_user_twinks(user_id)
    
    if not twinks:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Добавить твин", callback_data='add_twink')]
        ])
    
    keyboard = []
    
    for idx, twink in enumerate(twinks):
        nickname = twink.get('site_nickname', f"User {twink.get('profile_id')}")
        keyboard.append([
            InlineKeyboardButton(
                f"🗑 Удалить: {nickname}",
                callback_data=f"delete_twink_{twink.get('profile_id')}"
            )
        ])
    
    keyboard.append([InlineKeyboardButton("➕ Добавить твин", callback_data='add_twink')])
    
    return InlineKeyboardMarkup(keyboard)


# ══════════════════════════════════════════════
# АНКЕТА НА ВСТУПЛЕНИЕ
# ══════════════════════════════════════════════

def get_app_q1_keyboard():
    """Q1 — кнопка отмены (возврат в меню)"""
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("❌ Отменить анкету", callback_data='back_to_menu')]]
    )


def get_app_back_keyboard(back_step: int):
    """Клавиатура только с кнопкой «Назад» для текстовых вопросов"""
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("◀️ Назад", callback_data=f'app_back_{back_step}')]]
    )


def get_fan_question_keyboard():
    """Q3 — выбор Да/Нет + Назад"""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Да, я фанат!", callback_data='app_fan_yes'),
            InlineKeyboardButton("❌ Нет",           callback_data='app_fan_no'),
        ],
        [InlineKeyboardButton("◀️ Назад", callback_data='app_back_2')]
    ])


def get_arcana_keyboard():
    """Q3.1 — список аркан 2 в ряд + Назад"""
    rows = []
    for i in range(0, len(ARCANAS), 2):
        row = [InlineKeyboardButton(ARCANAS[i], callback_data=f'app_arcana_{ARCANAS[i]}')]
        if i + 1 < len(ARCANAS):
            row.append(InlineKeyboardButton(ARCANAS[i + 1], callback_data=f'app_arcana_{ARCANAS[i + 1]}'))
        rows.append(row)
    rows.append([InlineKeyboardButton("◀️ Назад", callback_data='app_back_3')])
    return InlineKeyboardMarkup(rows)


def get_q5_keyboard():
    """Q5 — пропустить / назад"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⏭️ Пропустить", callback_data='app_skip_5')],
        [InlineKeyboardButton("◀️ Назад",       callback_data='app_back_4')],
    ])


def get_app_review_keyboard():
    """Финальный просмотр анкеты"""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✏️ Вопрос 1", callback_data='app_edit_1'),
            InlineKeyboardButton("✏️ Вопрос 2", callback_data='app_edit_2'),
        ],
        [
            InlineKeyboardButton("✏️ Вопрос 3", callback_data='app_edit_3'),
            InlineKeyboardButton("✏️ Вопрос 4", callback_data='app_edit_4'),
        ],
        [InlineKeyboardButton("✏️ Вопрос 5",                callback_data='app_edit_5')],
        [InlineKeyboardButton("✅ Отправить оператору 🚀",   callback_data='app_send')],
    ])


# ══════════════════════════════════════════════
# ТЕКСТЫ ВОПРОСОВ АНКЕТЫ
# ══════════════════════════════════════════════

def app_q1_text():
    return (
        "📝 <b>Анкета на вступление</b>\n"
        "┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n"
        "<b>Вопрос 1 / 5</b>\n\n"
        "❓ Почему вы выбрали наш клуб?"
    )


def app_q2_text():
    return (
        "📝 <b>Анкета на вступление</b>\n"
        "┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n"
        "<b>Вопрос 2 / 5</b>\n\n"
        "❓ Отправьте ссылку на ваш аккаунт на MangaBuff\n\n"
        "<i>Формат: https://mangabuff.ru/users/XXXXXX</i>"
    )


def app_q3_text():
    return (
        "📝 <b>Анкета на вступление</b>\n"
        "┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n"
        "<b>Вопрос 3 / 5</b>\n\n"
        "❓ Являетесь ли вы фанатом <b>Повелителя тайн</b>?"
    )


def app_q3_arcana_text():
    return (
        "📝 <b>Анкета на вступление</b>\n"
        "┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n"
        "<b>Вопрос 3.1</b>\n\n"
        "❓ Выберите свою <b>путь</b> из списка ниже:"
    )


def app_q4_text():
    return (
        "📝 <b>Анкета на вступление</b>\n"
        "┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n"
        "<b>Вопрос 4 / 5</b>\n\n"
        "❓ Как к вам обращаться?\n\n"
        "<i>Введите имя / прозвище / ник  или  местоимения (он/его, она/её)</i>"
    )


def app_q5_text():
    return (
        "📝 <b>Анкета на вступление</b>\n"
        "┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n"
        "<b>Вопрос 5 / 5</b> <i>(по желанию)</i>\n\n"
        "❓ Дополнительное сообщение для оператора\n\n"
        "<i>Напишите что-нибудь или нажмите «Пропустить»</i>"
    )


def app_review_text(answers: dict) -> str:
    q3_display = answers.get('q3', '—')
    if q3_display == 'Да':
        arcana = answers.get('q3_arcana', '—')
        q3_display = f"Да  ➜  аркана: <b>{arcana}</b>"

    q5 = answers.get('q5') or "<i>не указано</i>"

    return (
        "📋 <b>Проверьте вашу анкету</b>\n"
        "┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n\n"
        f"<b>1. Почему наш клуб?</b>\n{answers.get('q1', '—')}\n\n"
        f"<b>2. Аккаунт MangaBuff:</b>\n{answers.get('q2', '—')}\n\n"
        f"<b>3. Фанат Повелителя тайн:</b> {q3_display}\n\n"
        f"<b>4. Как обращаться:</b> {answers.get('q4', '—')}\n\n"
        f"<b>5. Доп. сообщение:</b>\n{q5}\n\n"
        "┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n"
        "Всё верно? Нажмите <b>«Отправить оператору»</b> или"
        " отредактируйте нужный ответ кнопками ниже."
    )


# ══════════════════════════════════════════════
# ОПЕРАТОРСКИЕ КЛАВИАТУРЫ
# ══════════════════════════════════════════════

def get_operator_commands_keyboard():
    """Inline-меню команд для оператора"""
    keyboard = [
        [InlineKeyboardButton("📋 Чёрный список", callback_data='view_blacklist')],
        [InlineKeyboardButton("💬 Список диалогов", callback_data='view_dialogs')],
        [InlineKeyboardButton("◀️ Закрыть", callback_data='close_menu')]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_operator_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton("📋 Черный список", callback_data='view_blacklist')],
        [InlineKeyboardButton("◀️ Назад",         callback_data='back_to_menu')]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_user_action_keyboard(user_id: int, is_blocked: bool = False):
    keyboard = [
        [InlineKeyboardButton("💬 Ответить", callback_data=f'reply_{user_id}')]
    ]
    if is_blocked:
        keyboard.append(
            [InlineKeyboardButton("✅ Разблокировать", callback_data=f'unblock_{user_id}')]
        )
    else:
        keyboard.append(
            [InlineKeyboardButton("🚫 Заблокировать", callback_data=f'block_{user_id}')]
        )
    return InlineKeyboardMarkup(keyboard)


def get_block_confirmation_keyboard(user_id: int):
    """Клавиатура для подтверждения блокировки с причиной"""
    keyboard = [
        [InlineKeyboardButton("❌ Отменить", callback_data=f'cancel_block_{user_id}')]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_blacklist_user_keyboard(user_id: int):
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("✅ Разблокировать", callback_data=f'unblock_{user_id}')]]
    )


def get_application_keyboard():
    keyboard = [
        [InlineKeyboardButton("📝 Подать заявку на вступление", callback_data='submit_application')],
        [InlineKeyboardButton("◀️ Назад", callback_data='back_to_menu')]
    ]
    return InlineKeyboardMarkup(keyboard)