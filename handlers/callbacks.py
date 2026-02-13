"""
Обработчики нажатий на inline-кнопки
✅ ИСПРАВЛЕНО: Правильная проверка ролей (оператор vs администратор)
✅ ИСПРАВЛЕНО: Нельзя привязать пустой твин
✅ ДОБАВЛЕНО: Переключение настроек уведомлений per-аккаунт
"""
import logging
from telegram import Update, LinkPreviewOptions
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from telegram.error import BadRequest, TimedOut, NetworkError
from config.settings import ADMIN_CHAT_ID, WELCOME_TEXT
from database.db import (
    add_to_blacklist, remove_from_blacklist, get_blacklist,
    is_user_linked, get_user_profile_url, log_operator_action,
    get_twinks_count, remove_twink,
    is_staff, is_admin,
    toggle_notification, get_notification_settings,
)
from keyboards.inline import (
    get_main_menu_keyboard, get_back_button,
    get_user_action_keyboard, get_blacklist_user_keyboard,
    get_reply_keyboard_for_linked_user, get_block_confirmation_keyboard,
    get_app_q1_keyboard, get_app_back_keyboard, get_operator_commands_keyboard,
    get_fan_question_keyboard, get_arcana_keyboard,
    get_q5_keyboard, get_app_review_keyboard,
    get_twink_question_keyboard, get_twink_done_keyboard, get_twink_manage_keyboard,
    get_notifications_keyboard, notifications_text,
    app_q1_text, app_q2_text, app_q3_text, app_q3_arcana_text,
    app_q4_text, app_q5_text, app_review_text,
)
from utils.helpers import get_user_link
from utils.dialog_manager import DialogManager

logger = logging.getLogger(__name__)


# ═════════════════════════════════════════════════════════════
# БЕЗОПАСНЫЕ ОБЁРТКИ
# ═════════════════════════════════════════════════════════════

async def safe_answer_callback(query):
    try:
        await query.answer()
        return True
    except (TimedOut, NetworkError, Exception) as e:
        logger.warning(f"Ошибка ответа на callback: {e}")
        return False


async def safe_edit_message(query, text, **kwargs):
    try:
        await query.edit_message_text(text, **kwargs)
        return True
    except BadRequest as e:
        if "message is not modified" in str(e).lower():
            return False
        logger.error(f"BadRequest при редактировании: {e}")
        return False
    except (TimedOut, NetworkError, Exception) as e:
        logger.error(f"Ошибка редактирования сообщения: {e}")
        return False


async def safe_edit_reply_markup(query, **kwargs):
    try:
        await query.edit_message_reply_markup(**kwargs)
        return True
    except BadRequest as e:
        if "message is not modified" in str(e).lower():
            return False
        logger.error(f"BadRequest при редактировании markup: {e}")
        return False
    except Exception as e:
        logger.error(f"Ошибка редактирования markup: {e}")
        return False


def _store_msg(context, message):
    context.user_data['app_msg_id']  = message.message_id
    context.user_data['app_chat_id'] = message.chat_id


# ═════════════════════════════════════════════════════════════
# ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ: завершение привязки аккаунта
# ═════════════════════════════════════════════════════════════

async def _finish_account_linking(query, context, user, user_id: int, twinks_count: int):
    context.user_data['state'] = None
    context.user_data['twink_source'] = None
    context.user_data['twinks_added_this_session'] = 0

    is_operator = is_staff(user_id)
    main_profile_url = context.user_data.get('main_profile_url', 'не указан')
    twinks_info = f"\n💎 Привязано твинов: {twinks_count}" if twinks_count > 0 else ""

    try:
        await query.message.delete()
    except Exception:
        pass

    await context.bot.send_message(
        chat_id=user_id,
        text=(
            f"✅ <b>Аккаунт успешно привязан!</b>\n\n"
            f"Профиль: {main_profile_url}{twinks_info}\n\n"
            f"Теперь вам доступны все функции бота.\n"
            f"Нажмите на иконку с квадратами рядом с полем ввода, чтобы открыть меню команд 👇"
        ),
        reply_markup=get_reply_keyboard_for_linked_user(is_operator=is_operator),
        parse_mode=ParseMode.HTML,
        link_preview_options=LinkPreviewOptions(is_disabled=True)
    )

    user_link = get_user_link(user_id, user.first_name or user.username or "Пользователь")
    try:
        await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=(
                f"🔗 <b>Новая привязка аккаунта</b>\n\n"
                f"Пользователь: {user_link}\n"
                f"ID: <code>{user_id}</code>\n"
                f"Профиль: {main_profile_url}{twinks_info}"
                + (f"\n\n⚙️ <i>Это персонал</i>" if is_operator else "")
            ),
            parse_mode=ParseMode.HTML,
            link_preview_options=LinkPreviewOptions(is_disabled=True)
        )
    except Exception as e:
        logger.error(f"Ошибка уведомления оператора: {e}")

    logger.info(f"Пользователь {user_id} завершил привязку (твинов: {twinks_count})")


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатий на inline-кнопки"""
    query = update.callback_query
    await safe_answer_callback(query)

    user    = query.from_user
    user_id = user.id
    data    = query.data

    # ══════════════════════════════════════════
    # ✅ НАСТРОЙКИ УВЕДОМЛЕНИЙ
    # ══════════════════════════════════════════

    if data == 'notif_noop':
        # Кнопка с названием аккаунта — не делаем ничего
        return

    if data.startswith('toggle_notif_'):
        profile_key = data[len('toggle_notif_'):]
        new_value = toggle_notification(user_id, profile_key)

        status_word = "включены ✅" if new_value else "выключены 🔕"
        await query.answer(f"Уведомления {status_word}", show_alert=False)

        # Обновляем текст и клавиатуру на месте
        await safe_edit_message(
            query,
            notifications_text(user_id),
            reply_markup=get_notifications_keyboard(user_id),
            parse_mode=ParseMode.HTML
        )
        return

    # ══════════════════════════════════════════
    # УПРАВЛЕНИЕ ТВИНАМИ
    # ══════════════════════════════════════════

    if data == 'add_twink':
        context.user_data['state'] = 'adding_twinks'
        context.user_data['twink_source'] = 'menu'
        context.user_data['twinks_added_this_session'] = 0
        await safe_edit_message(
            query,
            "💎 <b>Добавление твина</b>\n\n"
            "Отправьте ссылку на ваш дополнительный аккаунт на MangaBuff.\n\n"
            "Формат: <code>https://mangabuff.ru/users/XXXXXX</code>\n\n"
            "❗️ Твины могут не состоять в клубе.\n\n"
            "Когда закончите добавлять, нажмите «Готово».\nДля отмены нажмите «Отмена».",
            reply_markup=get_twink_done_keyboard(),
            parse_mode=ParseMode.HTML
        )
        return

    if data.startswith('delete_twink_'):
        profile_id = data.replace('delete_twink_', '')
        success = remove_twink(user_id, profile_id)
        if success:
            await query.answer("✅ Твин удалён", show_alert=False)
            from database.db import get_user_twinks
            twinks = get_user_twinks(user_id)
            if not twinks:
                text_msg = "💎 <b>Дополнительные аккаунты (твины)</b>\n\nУ вас больше нет привязанных твинов.\n\nХотите добавить твин?"
            else:
                twinks_list = "\n".join(f"{i+1}. {t.get('site_nickname','Без ника')} - {t.get('profile_url')}" for i, t in enumerate(twinks))
                text_msg = f"💎 <b>Ваши твины ({len(twinks)})</b>\n\n{twinks_list}\n\nВы можете добавить новый или удалить существующий."
            await safe_edit_message(query, text_msg, reply_markup=get_twink_manage_keyboard(user_id),
                                    parse_mode=ParseMode.HTML, link_preview_options=LinkPreviewOptions(is_disabled=True))
        else:
            await query.answer("❌ Ошибка удаления", show_alert=True)
        return

    if data == 'twink_yes':
        context.user_data['state'] = 'adding_twinks'
        context.user_data['twink_source'] = 'linking'
        context.user_data['twinks_added_this_session'] = 0
        await safe_edit_message(
            query,
            "💎 <b>Привязка дополнительных аккаунтов (твинов)</b>\n\n"
            "Отправьте ссылку на ваш дополнительный аккаунт на MangaBuff.\n\n"
            "Формат: <code>https://mangabuff.ru/users/XXXXXX</code>\n\n"
            "❗️ Твины могут не состоять в клубе.\n\n"
            "Когда закончите добавлять, нажмите «Готово».\nДля отмены нажмите «Отмена».",
            reply_markup=get_twink_done_keyboard(),
            parse_mode=ParseMode.HTML
        )
        return

    if data == 'cancel_twink_add':
        context.user_data['state'] = None
        source = context.user_data.get('twink_source', 'menu')
        added_count = context.user_data.get('twinks_added_this_session', 0)

        if source == 'linking':
            twinks_count = get_twinks_count(user_id)
            await _finish_account_linking(query, context, user, user_id, twinks_count)
        else:
            context.user_data['twink_source'] = None
            context.user_data['twinks_added_this_session'] = 0
            from database.db import get_user_twinks
            twinks = get_user_twinks(user_id)
            if not twinks:
                text_msg = "💎 <b>Дополнительные аккаунты (твины)</b>\n\nУ вас пока нет привязанных твинов.\n\nХотите добавить твин?"
            else:
                twinks_list = "\n".join(f"{i+1}. {t.get('site_nickname','Без ника')} - {t.get('profile_url')}" for i, t in enumerate(twinks))
                text_msg = f"💎 <b>Ваши твины ({len(twinks)})</b>\n\n{twinks_list}\n\nВы можете добавить новый или удалить существующий."
            await safe_edit_message(query, text_msg, reply_markup=get_twink_manage_keyboard(user_id),
                                    parse_mode=ParseMode.HTML, link_preview_options=LinkPreviewOptions(is_disabled=True))
        logger.info(f"Пользователь {user_id} отменил добавление твина (источник: {source}, добавлено: {added_count})")
        return

    if data == 'twink_no':
        twinks_count = get_twinks_count(user_id)
        await _finish_account_linking(query, context, user, user_id, twinks_count)
        return

    if data == 'twink_done':
        context.user_data['state'] = None
        source = context.user_data.get('twink_source', 'menu')
        added_count = context.user_data.get('twinks_added_this_session', 0)

        if source == 'linking':
            twinks_count = get_twinks_count(user_id)
            await _finish_account_linking(query, context, user, user_id, twinks_count)
        else:
            context.user_data['twink_source'] = None
            context.user_data['twinks_added_this_session'] = 0
            from database.db import get_user_twinks
            twinks = get_user_twinks(user_id)
            if added_count == 0:
                if not twinks:
                    text_msg = "💎 <b>Дополнительные аккаунты (твины)</b>\n\nВы не добавили ни одного твина.\n\nХотите попробовать ещё раз?"
                else:
                    twinks_list = "\n".join(f"{i+1}. {t.get('site_nickname','Без ника')} - {t.get('profile_url')}" for i, t in enumerate(twinks))
                    text_msg = f"💎 <b>Ваши твины ({len(twinks)})</b>\n\n{twinks_list}\n\nВы можете добавить новый или удалить существующий."
            else:
                twinks_list = "\n".join(f"{i+1}. {t.get('site_nickname','Без ника')} - {t.get('profile_url')}" for i, t in enumerate(twinks))
                text_msg = f"✅ <b>Твины успешно добавлены!</b>\n\n💎 <b>Ваши твины ({len(twinks)})</b>\n\n{twinks_list}\n\nУправляйте твинами через кнопки ниже."
            await safe_edit_message(query, text_msg, reply_markup=get_twink_manage_keyboard(user_id),
                                    parse_mode=ParseMode.HTML, link_preview_options=LinkPreviewOptions(is_disabled=True))
        return

    # ══════════════════════════════════════════
    # ВОЗВРАТ В ГЛАВНОЕ МЕНЮ
    # ══════════════════════════════════════════
    if data == 'back_to_menu':
        context.user_data['state'] = None
        context.user_data['app_answers'] = {}
        context.user_data['blocking_user_id'] = None
        context.user_data['twink_source'] = None
        context.user_data['twinks_added_this_session'] = 0
        linked = is_user_linked(user_id)
        is_operator = is_staff(user_id)
        if linked:
            try:
                await query.message.delete()
            except Exception:
                pass
            await context.bot.send_message(
                chat_id=user_id,
                text=WELCOME_TEXT + "\n\n✅ Используйте кнопки внизу.",
                reply_markup=get_reply_keyboard_for_linked_user(is_operator=is_operator),
                parse_mode=ParseMode.HTML
            )
        else:
            await safe_edit_message(query, WELCOME_TEXT, reply_markup=get_main_menu_keyboard(), parse_mode=ParseMode.HTML)
        return

    if data == 'close_menu':
        try:
            await query.message.delete()
        except Exception as e:
            logger.error(f"Ошибка удаления сообщения: {e}")
        return

    if data == 'view_dialogs':
        try:
            await query.message.delete()
        except Exception:
            pass
        from handlers.commands import dialogs_command_impl
        await dialogs_command_impl(context.bot_data, context.bot, user_id, query.message.chat_id)
        return

    # ══════════════════════════════════════════
    # ПРОФИЛЬ / ХОТЕЛКИ / …
    # ══════════════════════════════════════════
    if data == 'profile':
        profile_url = get_user_profile_url(user_id)
        await safe_edit_message(
            query,
            f"👤 <b>Ваш профиль</b>\n\nИмя: {user.first_name}\n"
            f"Username: @{user.username if user.username else 'не указан'}\n"
            f"Профиль на сайте: {profile_url if profile_url else 'не привязан'}",
            reply_markup=get_back_button(), parse_mode=ParseMode.HTML,
            link_preview_options=LinkPreviewOptions(is_disabled=True)
        )
        return

    if data == 'notifications':
        await safe_edit_message(
            query,
            notifications_text(user_id),
            reply_markup=get_notifications_keyboard(user_id),
            parse_mode=ParseMode.HTML
        )
        return

    if data == 'wishlist':
        await safe_edit_message(query, "💝 <b>Хотелки</b>\n\nФункция в разработке.", reply_markup=get_back_button(), parse_mode=ParseMode.HTML)
        return

    if data == 'contract_ok':
        await safe_edit_message(query, "📋 <b>Договор за ОК</b>\n\nФункция в разработке.", reply_markup=get_back_button(), parse_mode=ParseMode.HTML)
        return

    if data == 'card_price':
        await safe_edit_message(query, "💳 <b>Узнать цену Карты</b>\n\nФункция в разработке.", reply_markup=get_back_button(), parse_mode=ParseMode.HTML)
        return

    if data == 'link_account':
        await safe_edit_message(
            query,
            "🔗 <b>Привязка аккаунта</b>\n\nОтправьте ссылку на ваш профиль на сайте mangabuff.ru\n\n"
            "Формат: <code>https://mangabuff.ru/users/XXXXXX</code>\n",
            reply_markup=get_back_button(), parse_mode=ParseMode.HTML
        )
        context.user_data['state'] = 'linking_account'
        return

    if data == 'contact_operator':
        await safe_edit_message(
            query,
            "💬 <b>Связь с оператором</b>\n\nНапишите ваш вопрос, и оператор ответит в течение 5-15 минут.",
            reply_markup=get_back_button(), parse_mode=ParseMode.HTML
        )
        context.user_data['state'] = 'contacting_operator'
        return

    # ══════════════════════════════════════════
    # ПОДАЧА ЗАЯВКИ — АНКЕТА
    # ══════════════════════════════════════════
    if data == 'submit_application':
        context.user_data['state']       = 'app_q1'
        context.user_data['app_answers'] = {}
        _store_msg(context, query.message)
        await safe_edit_message(query, app_q1_text(), reply_markup=get_app_q1_keyboard(), parse_mode=ParseMode.HTML)
        return

    if data.startswith('app_back_'):
        if data == 'app_back_3_arcana':
            context.user_data['state'] = 'app_q3_arcana'
            await safe_edit_message(query, app_q3_arcana_text(), reply_markup=get_arcana_keyboard(), parse_mode=ParseMode.HTML)
            return
        back_to = int(data.split('_')[-1])
        if back_to == 1:
            context.user_data['state'] = 'app_q1'
            await safe_edit_message(query, app_q1_text(), reply_markup=get_app_q1_keyboard(), parse_mode=ParseMode.HTML)
        elif back_to == 2:
            context.user_data['state'] = 'app_q2'
            await safe_edit_message(query, app_q2_text(), reply_markup=get_app_back_keyboard(1), parse_mode=ParseMode.HTML)
        elif back_to == 3:
            context.user_data['state'] = 'app_q3'
            await safe_edit_message(query, app_q3_text(), reply_markup=get_fan_question_keyboard(), parse_mode=ParseMode.HTML)
        elif back_to == 4:
            q3_was_yes = context.user_data.get('app_answers', {}).get('q3') == 'Да'
            context.user_data['state'] = 'app_q4'
            await safe_edit_message(query, app_q4_text(), reply_markup=get_app_back_keyboard('3_arcana' if q3_was_yes else 3), parse_mode=ParseMode.HTML)
        return

    if data == 'app_fan_yes':
        context.user_data['app_answers']['q3'] = 'Да'
        context.user_data['state'] = 'app_q3_arcana'
        await safe_edit_message(query, app_q3_arcana_text(), reply_markup=get_arcana_keyboard(), parse_mode=ParseMode.HTML)
        return

    if data == 'app_fan_no':
        context.user_data['app_answers']['q3'] = 'Нет'
        context.user_data['app_answers']['q3_arcana'] = None
        context.user_data['state'] = 'app_q4'
        await safe_edit_message(query, app_q4_text(), reply_markup=get_app_back_keyboard(3), parse_mode=ParseMode.HTML)
        return

    if data.startswith('app_arcana_'):
        context.user_data['app_answers']['q3_arcana'] = data[len('app_arcana_'):]
        context.user_data['state'] = 'app_q4'
        await safe_edit_message(query, app_q4_text(), reply_markup=get_app_back_keyboard('3_arcana'), parse_mode=ParseMode.HTML)
        return

    if data == 'app_skip_5':
        context.user_data['app_answers']['q5'] = None
        context.user_data['state'] = 'app_review'
        answers = context.user_data.get('app_answers', {})
        await safe_edit_message(query, app_review_text(answers), reply_markup=get_app_review_keyboard(),
                                parse_mode=ParseMode.HTML, link_preview_options=LinkPreviewOptions(is_disabled=True))
        return

    if data.startswith('app_edit_'):
        step = int(data.split('_')[-1])
        state_map = {1: 'app_q1', 2: 'app_q2', 3: 'app_q3', 4: 'app_q4', 5: 'app_q5'}
        text_map  = {
            1: (app_q1_text, get_app_q1_keyboard),
            2: (app_q2_text, lambda: get_app_back_keyboard(1)),
            3: (app_q3_text, get_fan_question_keyboard),
            4: (app_q4_text, lambda: get_app_back_keyboard(3)),
            5: (app_q5_text, get_q5_keyboard),
        }
        context.user_data['state'] = state_map[step]
        txt_fn, kb_fn = text_map[step]
        await safe_edit_message(query, txt_fn(), reply_markup=kb_fn(), parse_mode=ParseMode.HTML)
        return

    if data == 'app_send':
        answers = context.user_data.get('app_answers', {})
        user_link = get_user_link(user_id, user.first_name or user.username or f"User {user_id}")
        q3_display = answers.get('q3', '—')
        if q3_display == 'Да':
            q3_display = f"Да  ➜  аркана: {answers.get('q3_arcana', '—')}"
        admin_text = (
            f"📝 <b>Новая заявка на вступление</b>\n┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n"
            f"От: {user_link}\nID: <code>{user_id}</code>\nUsername: @{user.username or '—'}\n\n"
            f"<b>1. Почему наш клуб?</b>\n{answers.get('q1','—')}\n\n"
            f"<b>2. MangaBuff:</b>\n{answers.get('q2','—')}\n\n"
            f"<b>3. Фанат Повелителя тайн:</b> {q3_display}\n\n"
            f"<b>4. Обращение:</b> {answers.get('q4','—')}\n\n"
            f"<b>5. Доп. сообщение:</b>\n{answers.get('q5') or '—'}"
        )
        try:
            await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=admin_text,
                                           reply_markup=get_user_action_keyboard(user_id),
                                           parse_mode=ParseMode.HTML, link_preview_options=LinkPreviewOptions(is_disabled=True))
        except Exception as e:
            logger.error(f"Ошибка отправки заявки: {e}")
        context.user_data['state'] = None
        context.user_data['app_answers'] = {}
        await safe_edit_message(query, "✅ <b>Заявка отправлена!</b>\n\nСпасибо за интерес к Club Taro. Оператор рассмотрит заявку и свяжется с вами.", parse_mode=ParseMode.HTML)
        return

        # ══════════════════════════════════════════════════════════════
    # ✅ НОВЫЕ ОБРАБОТЧИКИ ДЛЯ ЦЕН НА КАРТЫ
    # ══════════════════════════════════════════════════════════════
    
    if data == 'upload_prices':
        from handlers.card_prices import handle_upload_prices
        await handle_upload_prices(update, context)
        return
    
    if data == 'cancel_upload_prices':
        from handlers.card_prices import handle_cancel_upload_prices
        await handle_cancel_upload_prices(update, context)
        return
    
    if data == 'send_card_for_evaluation':
        from handlers.card_prices import handle_send_card_for_evaluation
        await handle_send_card_for_evaluation(update, context)
        return
    
    if data == 'cancel_card_evaluation':
        from handlers.card_prices import handle_cancel_card_evaluation
        await handle_cancel_card_evaluation(update, context)
        return
    

    # ══════════════════════════════════════════
    # ОПЕРАТОРСКИЕ ФУНКЦИИ
    # ══════════════════════════════════════════

    if data == 'view_blacklist':
        if not is_staff(user_id):
            await query.answer("❌ Недостаточно прав", show_alert=True)
            return
        blacklist = get_blacklist()
        if not blacklist:
            await safe_edit_message(query, "📋 <b>Черный список</b>\n\nЧерный список пуст.", reply_markup=get_back_button(), parse_mode=ParseMode.HTML)
            return
        text = "📋 <b>Черный список</b>\n\n"
        for bl_uid, username, first_name, reason, blocked_at in blacklist:
            ul = get_user_link(bl_uid, first_name or username or f"User {bl_uid}")
            text += (f"👤 {ul}\nID: <code>{bl_uid}</code>\n"
                     + (f"Username: @{username}\n" if username else "")
                     + (f"Причина: {reason}\n" if reason else "")
                     + f"Заблокирован: {blocked_at}\nРазблокировать: /unblock {bl_uid}\n" + "─"*30 + "\n\n")
        await safe_edit_message(query, text, reply_markup=get_back_button(), parse_mode=ParseMode.HTML)
        return

    if data.startswith('reply_'):
        if not is_staff(user_id):
            await query.answer("❌ Недостаточно прав", show_alert=True)
            return
        reply_user_id = int(data.split('_')[1])
        dm = DialogManager(context.bot_data)
        try:
            user_info = await context.bot.get_chat(reply_user_id)
            user_name = user_info.first_name or user_info.username or f"User {reply_user_id}"
        except Exception:
            user_name = f"User {reply_user_id}"
        log_operator_action(user_id, 'dialog_start', target_user_id=reply_user_id, target_first_name=user_name)
        dm.start_dialog(user_id, reply_user_id, user_name)
        try:
            await query.message.reply_text(
                f"💬 <b>Диалог начат с {user_name} (ID: {reply_user_id})</b>\n\n"
                f"• /dialogs - список диалогов\n• /end_dialog - завершить\n• /end_all - завершить все",
                parse_mode=ParseMode.HTML)
            await context.bot.send_message(chat_id=reply_user_id,
                text="💬 <b>Оператор начал с вами диалог!</b>\n\nПросто напишите ваше сообщение.\n\n💡 /end_dialog — завершить диалог",
                parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.error(f"Ошибка при начале диалога: {e}")
        return

    if data.startswith('block_'):
        if not is_staff(user_id):
            await query.answer("❌ Недостаточно прав", show_alert=True)
            return
        blocked_uid = int(data.split('_')[1])
        context.user_data['blocking_user_id'] = blocked_uid
        context.user_data['state'] = 'blocking_user'
        await query.message.reply_text(
            f"🚫 <b>Блокировка пользователя</b>\n\nID: <code>{blocked_uid}</code>\n\nНапишите причину блокировки или /cancel для отмены:",
            reply_markup=get_block_confirmation_keyboard(blocked_uid), parse_mode=ParseMode.HTML)
        return

    if data.startswith('cancel_block_'):
        context.user_data['blocking_user_id'] = None
        context.user_data['state'] = None
        await query.message.edit_text("✅ Блокировка отменена", parse_mode=ParseMode.HTML)
        return

    if data.startswith('unblock_'):
        if not is_staff(user_id):
            await query.answer("❌ Недостаточно прав", show_alert=True)
            return
        unblocked_uid = int(data.split('_')[1])
        from database.db import get_user_info
        user_info = get_user_info(unblocked_uid)
        remove_from_blacklist(unblocked_uid)
        log_operator_action(user_id, 'user_unblocked', target_user_id=unblocked_uid,
                            target_username=user_info[1] if user_info else None,
                            target_first_name=user_info[2] if user_info else None)
        try:
            await query.answer("✅ Пользователь разблокирован", show_alert=True)
        except Exception:
            pass
        await safe_edit_reply_markup(query, reply_markup=get_user_action_keyboard(unblocked_uid, is_blocked=False))
        return

    if data.startswith('switch_dialog_'):
        if not is_staff(user_id):
            await query.answer("❌ Недостаточно прав", show_alert=True)
            return
        dialog_id = data.replace('switch_dialog_', '')
        dm = DialogManager(context.bot_data)
        if dm.switch_dialog(user_id, dialog_id):
            dialog_info = dm.get_dialog_info(dialog_id)
            log_operator_action(user_id, 'dialog_switch', target_user_id=dialog_info['user_id'],
                                target_first_name=dialog_info['user_name'], details=f"dialog_id: {dialog_id}")
            await query.answer(f"✅ Переключено на {dialog_info['user_name']}", show_alert=False)
            await query.message.edit_text(
                f"✅ <b>Активный диалог изменён</b>\n\nТеперь вы в диалоге с {dialog_info['user_name']}\n\n/dialogs — все диалоги",
                parse_mode=ParseMode.HTML)
        else:
            await query.answer("❌ Ошибка переключения диалога", show_alert=True)
        return

    if data == 'end_all_dialogs':
        if not is_staff(user_id):
            await query.answer("❌ Недостаточно прав", show_alert=True)
            return
        dm = DialogManager(context.bot_data)
        dialogs = dm.get_all_operator_dialogs(user_id)
        user_ids = [info['user_id'] for _, info in dialogs]
        count = dm.end_all_operator_dialogs(user_id)
        log_operator_action(user_id, 'dialog_end', details=f"Завершено диалогов: {count}")
        await query.answer(f"✅ Завершено диалогов: {count}", show_alert=True)
        await query.message.edit_text(f"✅ <b>Завершено диалогов: {count}</b>\n\nВсе активные диалоги закрыты.", parse_mode=ParseMode.HTML)
        for other_user_id in user_ids:
            try:
                await context.bot.send_message(chat_id=other_user_id,
                    text="✅ <b>Диалог завершен</b>\n\nОператор завершил диалог с вами.", parse_mode=ParseMode.HTML)
            except Exception as e:
                logger.error(f"Ошибка уведомления {other_user_id}: {e}")
        return