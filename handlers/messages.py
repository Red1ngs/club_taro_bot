"""
Обработчик текстовых сообщений
✅ ОБНОВЛЕНО: Добавлена кнопка "💎 Твины" в постоянном меню
✅ ИСПРАВЛЕНО: Сообщения "связь с оператором" идут оператору из БД, остальное - админу
✅ ИСПРАВЛЕНО: Счётчик twinks_added_this_session для защиты от пустых привязок
"""
import logging
from telegram import Update, LinkPreviewOptions
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from config.settings import ADMIN_CHAT_ID
from database.db import (
    is_blacklisted, save_user, is_user_linked, 
    get_user_profile_url, add_to_blacklist,
    log_operator_action, save_dialog_message,
    add_twink, get_twinks_count, get_user_twinks,
    is_staff, get_all_users_by_role
)
from keyboards.inline import (
    get_back_button, get_user_action_keyboard, get_application_keyboard,
    get_reply_keyboard_for_linked_user, get_operator_commands_keyboard,
    get_app_back_keyboard, get_fan_question_keyboard,
    get_q5_keyboard, get_app_review_keyboard,
    get_twink_done_keyboard, get_twink_manage_keyboard, get_twink_question_keyboard,
    app_q2_text, app_q3_text, app_q4_text, app_q5_text, app_review_text,
    BTN_PROFILE, BTN_NOTIFICATIONS, BTN_WISHLIST,
    BTN_CONTRACT, BTN_CARD_PRICE, BTN_TWINKS, BTN_OPERATOR, BTN_OPERATOR_COMMANDS,
    REPLY_KEYBOARD_BUTTONS,
)
from utils.helpers import (
    get_user_link, check_club_membership,
    is_user_in_group, validate_profile_url,
    get_site_nickname
)
from utils.dialog_manager import DialogManager
from config.settings import WELCOME_TEXT

logger = logging.getLogger(__name__)


async def _send_to_operators(context, text, reply_markup=None, **kwargs):
    """
    Отправляет сообщение всем операторам из БД.
    Используется только для сообщений через кнопку "Связь с оператором".
    """
    operators = get_all_users_by_role('operator')
    if not operators:
        logger.warning("Операторов в БД нет, отправляем администратору")
        await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=text,
            reply_markup=reply_markup,
            **kwargs
        )
        return

    for op_id, _, _, _ in operators:
        try:
            await context.bot.send_message(
                chat_id=op_id,
                text=text,
                reply_markup=reply_markup,
                **kwargs
            )
        except Exception as e:
            logger.error(f"Ошибка отправки оператору {op_id}: {e}")


async def _edit_app_message(context, chat_id, msg_id, text, keyboard):
    try:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=msg_id,
            text=text,
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML,
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )
    except Exception as e:
        logger.error(f"Ошибка редактирования анкетного сообщения: {e}")


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Главный обработчик текстовых сообщений"""
    user    = update.message.from_user
    user_id = user.id

    # Чёрный список
    if is_blacklisted(user_id):
        logger.warning(f"Заблокированный {user_id} пытается отправить сообщение")
        return

    user_state   = context.user_data.get('state')
    user_message = update.message.text

    # ══════════════════════════════════════════
    # ПРОВЕРКА: СООБЩЕНИЕ ОТ ПЕРСОНАЛА
    # ══════════════════════════════════════════
    dm = DialogManager(context.bot_data)
    
    if is_staff(user_id):
        if user_state == 'blocking_user':
            blocked_uid = context.user_data.get('blocking_user_id')
            if blocked_uid:
                reason = user_message.strip()
                
                try:
                    chat = await context.bot.get_chat(blocked_uid)
                    add_to_blacklist(
                        blocked_uid, 
                        chat.username or "", 
                        chat.first_name or "", 
                        reason
                    )
                    
                    log_operator_action(
                        user_id,
                        'user_blocked',
                        target_user_id=blocked_uid,
                        target_username=chat.username or "",
                        target_first_name=chat.first_name or "",
                        details=f"Причина: {reason}"
                    )
                    
                except Exception:
                    add_to_blacklist(blocked_uid, "", "", reason)
                    log_operator_action(
                        user_id,
                        'user_blocked',
                        target_user_id=blocked_uid,
                        details=f"Причина: {reason}"
                    )
                
                context.user_data['blocking_user_id'] = None
                context.user_data['state'] = None
                
                await update.message.reply_text(
                    f"✅ <b>Пользователь заблокирован</b>\n\n"
                    f"ID: <code>{blocked_uid}</code>\n"
                    f"Причина: {reason}",
                    parse_mode=ParseMode.HTML
                )
                
                logger.info(f"Персонал {user_id} заблокировал пользователя {blocked_uid} с причиной: {reason}")
                return
        
        active_dialog_id = dm.get_active_dialog_for_operator(user_id)
        
        if active_dialog_id:
            dialog_info = dm.get_dialog_info(active_dialog_id)
            target_user_id = dialog_info['user_id']
            user_name = dialog_info['user_name']
            
            try:
                save_dialog_message(
                    dialog_id=active_dialog_id,
                    sender_id=user_id,
                    sender_type='operator',
                    message_text=user_message
                )
                
                await context.bot.send_message(
                    chat_id=target_user_id,
                    text=f"💬 <b>Оператор:</b>\n\n{user_message}",
                    parse_mode=ParseMode.HTML
                )
                
                await update.message.reply_text(
                    f"✅ Сообщение отправлено пользователю {user_name}",
                    disable_notification=True
                )
                
                dm.increment_message_count(active_dialog_id)
                
                return
                
            except Exception as e:
                logger.error(f"Ошибка отправки сообщения пользователю: {e}")
                await update.message.reply_text(
                    "❌ Ошибка отправки сообщения. Возможно, пользователь заблокировал бота."
                )
                return

    # ══════════════════════════════════════════
    # ПРОВЕРКА АКТИВНОГО ДИАЛОГА ПОЛЬЗОВАТЕЛЯ
    # ══════════════════════════════════════════
    dialog_id, dialog_info = dm.find_user_dialog(user_id)
    
    if dialog_id and dialog_info:
        if user_message in REPLY_KEYBOARD_BUTTONS:
            await update.message.reply_text(
                "⚠️ <b>Команды меню недоступны в режиме диалога</b>\n\n"
                "Сейчас вы общаетесь с оператором напрямую.\n"
                "Просто напишите ваше сообщение.\n\n"
                "💡 Для завершения диалога используйте команду /end_dialog",
                parse_mode=ParseMode.HTML
            )
            return
        
        operator_id = dialog_info['operator_id']
        
        try:
            save_dialog_message(
                dialog_id=dialog_id,
                sender_id=user_id,
                sender_type='user',
                message_text=user_message
            )
            
            sender_name = user.first_name or user.username or f"User {user_id}"
            user_link = get_user_link(user_id, sender_name)
            
            await context.bot.send_message(
                chat_id=operator_id,
                text=f"💬 <b>Сообщение от {user_link}:</b>\n\n{user_message}",
                parse_mode=ParseMode.HTML
            )
            
            dm.increment_message_count(dialog_id)
            
            return
            
        except Exception as e:
            logger.error(f"Ошибка пересылки сообщения в диалоге: {e}")
            await update.message.reply_text(
                "❌ Ошибка отправки сообщения. Диалог завершен."
            )
            dm.end_dialog(dialog_id)
            return

    # ══════════════════════════════════════════
    # ПОСТОЯННАЯ НИЖНЯЯ КЛАВИАТУРА
    # ══════════════════════════════════════════
    if user_message in REPLY_KEYBOARD_BUTTONS and is_user_linked(user_id):
        await _handle_reply_button(update, context, user, user_id, user_message)
        return

    # ══════════════════════════════════════════
    # ПРИВЯЗКА АККАУНТА
    # ══════════════════════════════════════════
    if user_state == 'linking_account':
        await _handle_linking(update, context, user, user_id, user_message)
        return

    # ══════════════════════════════════════════
    # ✅ ПРИВЯЗКА ТВИНОВ
    # ══════════════════════════════════════════
    if user_state == 'adding_twinks':
        await _handle_twink_linking(update, context, user, user_id, user_message)
        return

    # ══════════════════════════════════════════
    # АНКЕТА — ТЕКСТОВЫЕ ОТВЕТЫ
    # ══════════════════════════════════════════
    if user_state == 'app_q1':
        context.user_data['app_answers']['q1'] = user_message
        context.user_data['state'] = 'app_q2'
        await _edit_app_message(
            context,
            context.user_data.get('app_chat_id'),
            context.user_data.get('app_msg_id'),
            app_q2_text(),
            get_app_back_keyboard(1)
        )
        return

    if user_state == 'app_q2':
        profile_id = validate_profile_url(user_message)
        
        if not profile_id:
            await update.message.reply_text(
                "❌ <b>Неверный формат ссылки!</b>\n\n"
                "Пожалуйста, отправьте ссылку в формате:\n"
                "<code>https://mangabuff.ru/users/XXXXXX</code>\n\n"
                "где XXXXXX - от 1 до 7 цифр\n\n"
                "Примеры:\n"
                "• https://mangabuff.ru/users/123\n"
                "• https://mangabuff.ru/users/943\n"
                "• https://mangabuff.ru/users/1234567",
                parse_mode=ParseMode.HTML
            )
            return
        
        context.user_data['app_answers']['q2'] = user_message
        context.user_data['state'] = 'app_q3'
        await _edit_app_message(
            context,
            context.user_data.get('app_chat_id'),
            context.user_data.get('app_msg_id'),
            app_q3_text(),
            get_fan_question_keyboard()
        )
        return

    if user_state == 'app_q4':
        context.user_data['app_answers']['q4'] = user_message
        context.user_data['state'] = 'app_q5'
        await _edit_app_message(
            context,
            context.user_data.get('app_chat_id'),
            context.user_data.get('app_msg_id'),
            app_q5_text(),
            get_q5_keyboard()
        )
        return

    if user_state == 'app_q5':
        context.user_data['app_answers']['q5'] = user_message
        context.user_data['state'] = 'app_review'
        answers = context.user_data.get('app_answers', {})
        await _edit_app_message(
            context,
            context.user_data.get('app_chat_id'),
            context.user_data.get('app_msg_id'),
            app_review_text(answers),
            get_app_review_keyboard()
        )
        return

    # ══════════════════════════════════════════
    # СВЯЗЬ С ОПЕРАТОРОМ (state)
    # ══════════════════════════════════════════
    if user_state == 'contacting_operator':
        await update.message.reply_text(
            "✅ Ваше сообщение отправлено оператору!\n"
            "Оператор ответит в течение 5-15 минут.",
            reply_markup=get_back_button() if not is_user_linked(user_id) else None
        )
        user_link = get_user_link(user_id, user.first_name or user.username or "Пользователь")

        await _send_to_operators(
            context,
            text=(
                f"💬 <b>Новое сообщение от пользователя</b>\n\n"
                f"От: {user_link}\n"
                f"ID: <code>{user_id}</code>\n\n"
                f"<b>Сообщение:</b>\n{user_message}"
            ),
            reply_markup=get_user_action_keyboard(user_id),
            parse_mode=ParseMode.HTML
        )
        context.user_data['state'] = None
        return


async def _handle_reply_button(update, context, user, user_id, text):
    dm = DialogManager(context.bot_data)
    
    if text == BTN_PROFILE:
        loading_msg = await update.message.reply_text(
            "🔄 Загружаю данные профиля..."
        )
        
        try:
            from database.db import get_user_info
            user_info = get_user_info(user_id)
            
            if not user_info:
                await loading_msg.edit_text(
                    "❌ Ошибка: данные пользователя не найдены в БД"
                )
                return
            
            user_data = {
                'user_id': user_info[0],
                'username': user_info[1],
                'first_name': user_info[2],
                'last_name': user_info[3],
                'profile_url': get_user_profile_url(user_id),
                'profile_id': None,
                'site_nickname': user_info[4] if len(user_info) > 4 else None,
            }
            
            profile_url = user_data['profile_url']
            if profile_url:
                import re
                match = re.search(r'/users/(\d+)', profile_url)
                if match:
                    user_data['profile_id'] = match.group(1)
            
            if not profile_url or not user_data['profile_id']:
                twinks_count = get_twinks_count(user_id)
                twinks_info = f"\n💎 Твинов привязано: {twinks_count}" if twinks_count > 0 else ""
                
                await loading_msg.edit_text(
                    f"👤 <b>Базовый профиль</b>\n\n"
                    f"Имя: {user.first_name}\n"
                    f"Username: @{user.username or 'не указан'}\n"
                    f"Профиль на сайте: не привязан"
                    f"{twinks_info}\n\n"
                    f"ℹ️ Привяжите аккаунт для доступа к расширенному профилю",
                    parse_mode=ParseMode.HTML
                )
                return
            
            from utils.profile_builder import build_user_profile, format_profile_message
            
            profile = build_user_profile(user_data)
            
            if not profile:
                await loading_msg.edit_text(
                    "❌ Ошибка при построении профиля. Попробуйте позже."
                )
                return
            
            twinks_count = get_twinks_count(user_id)
            twinks_suffix = f"\n\n💎 <b>Твинов привязано:</b> {twinks_count}" if twinks_count > 0 else ""
            
            message = format_profile_message(profile) + twinks_suffix
            
            await loading_msg.edit_text(
                message,
                parse_mode=ParseMode.HTML,
                link_preview_options=LinkPreviewOptions(is_disabled=True)
            )
            
        except Exception as e:
            logger.error(f"Ошибка показа профиля: {e}", exc_info=True)
            await loading_msg.edit_text(
                f"❌ Ошибка при загрузке профиля: {str(e)}\n\n"
                f"Попробуйте позже или обратитесь к администратору."
            )

    elif text == BTN_NOTIFICATIONS:
        await update.message.reply_text(
            "🔔 <b>Уведомления</b>\n\nФункция частично разработана, вам придет уведомление в лс.",
            parse_mode=ParseMode.HTML
        )

    elif text == BTN_WISHLIST:
        await update.message.reply_text(
            "💝 <b>Хотелки</b>\n\nФункция в разработке.",
            parse_mode=ParseMode.HTML
        )

    elif text == BTN_CONTRACT:
        await update.message.reply_text(
            "📋 <b>Договор за ОК</b>\n\nФункция в разработке.",
            parse_mode=ParseMode.HTML
        )

    elif text == BTN_CARD_PRICE:
        await update.message.reply_text(
            "💳 <b>Узнать цену Карты</b>\n\nФункция в разработке.",
            parse_mode=ParseMode.HTML
        )

    elif text == BTN_TWINKS:
        twinks = get_user_twinks(user_id)
        
        if not twinks:
            text_msg = (
                "💎 <b>Дополнительные аккаунты (твины)</b>\n\n"
                "У вас пока нет привязанных твинов.\n\n"
                "Твины — это дополнительные аккаунты MangaBuff, которые вы можете привязать к боту.\n"
                "Они могут не состоять в клубе.\n\n"
                "Хотите добавить твин?"
            )
        else:
            twinks_list = "\n".join(
                f"{idx+1}. {t.get('site_nickname', 'Без ника')} - {t.get('profile_url')}"
                for idx, t in enumerate(twinks)
            )
            text_msg = (
                f"💎 <b>Ваши твины ({len(twinks)})</b>\n\n"
                f"{twinks_list}\n\n"
                "Вы можете добавить новый или удалить существующий."
            )
        
        await update.message.reply_text(
            text_msg,
            reply_markup=get_twink_manage_keyboard(user_id),
            parse_mode=ParseMode.HTML,
            link_preview_options=LinkPreviewOptions(is_disabled=True)
        )

    elif text == BTN_OPERATOR_COMMANDS:
        await update.message.reply_text(
            "⚙️ <b>Команды оператора</b>\n\n"
            "Выберите действие:",
            reply_markup=get_operator_commands_keyboard(),
            parse_mode=ParseMode.HTML
        )

    elif text == BTN_OPERATOR:
        dialog_id, _ = dm.find_user_dialog(user_id)
        
        if dialog_id:
            await update.message.reply_text(
                "💬 Вы уже в активном диалоге с оператором!\n\n"
                "Просто напишите ваше сообщение, и оно будет отправлено.\n\n"
                "💡 Для завершения диалога используйте команду /end_dialog",
                parse_mode=ParseMode.HTML
            )
        else:
            await update.message.reply_text(
                "💬 <b>Связь с оператором</b>\n\n"
                "Напишите ваш вопрос, и оператор ответит в течение 5-15 минут.",
                parse_mode=ParseMode.HTML
            )
            context.user_data['state'] = 'contacting_operator'

async def _handle_linking(update, context, user, user_id, user_message):
    """Обработка основной привязки аккаунта"""
    profile_id = validate_profile_url(user_message)

    if not profile_id:
        await update.message.reply_text(
            "❌ <b>Неверный формат ссылки!</b>\n\n"
            "Пожалуйста, отправьте ссылку в формате:\n"
            "<code>https://mangabuff.ru/users/XXXXXX</code>\n\n"
            "где XXXXXX - от 1 до 7 цифр\n\n"
            "Примеры:\n"
            "• https://mangabuff.ru/users/123\n"
            "• https://mangabuff.ru/users/943\n"
            "• https://mangabuff.ru/users/1234567",
            reply_markup=get_back_button(),
            parse_mode=ParseMode.HTML
        )
        return

    checking_msg = await update.message.reply_text("🔍 Проверяем ваше членство в клубе...")

    is_member, message = check_club_membership(user_message.strip())

    if not is_member:
        user_link = get_user_link(user_id, user.first_name or user.username or "Пользователь")
        try:
            await context.bot.send_message(
                chat_id=ADMIN_CHAT_ID,
                text=(
                    f"⚠️ <b>Попытка привязки без членства</b>\n\n"
                    f"Пользователь: {user_link}\n"
                    f"ID: <code>{user_id}</code>\n"
                    f"Профиль: {user_message}"
                ),
                reply_markup=get_user_action_keyboard(user_id),
                parse_mode=ParseMode.HTML,
                link_preview_options=LinkPreviewOptions(is_disabled=True)
            )
        except Exception as e:
            logger.error(f"Ошибка уведомления администратора: {e}")

        await checking_msg.edit_text(
            f"❌ {message}\n\n"
            "Вы не состоите в Club Taro на сайте.\n"
            "Сначала вступите в клуб, затем привяжите аккаунт.",
            reply_markup=get_application_keyboard()
        )
        context.user_data['state'] = None
        return

    in_group = await is_user_in_group(context, user_id)
    if not in_group:
        await checking_msg.edit_text(
            "❌ Вы не состоите в группе Telegram Club Taro!\n\n"
            "Сначала вступите в группу, затем привяжите аккаунт.",
            reply_markup=get_back_button()
        )
        context.user_data['state'] = None
        return

    site_nickname = get_site_nickname(user_message.strip())
    if site_nickname:
        logger.info(f"Получен ник для пользователя {user_id}: {site_nickname}")
    else:
        logger.warning(f"Не удалось получить ник для пользователя {user_id}, используем username")
        site_nickname = user.username or user.first_name

    save_user(
        user_id, user.username, user.first_name, user.last_name,
        user_message.strip(), profile_id, site_nickname, is_linked=True
    )

    context.user_data['main_profile_url'] = user_message.strip()
    context.user_data['main_profile_id'] = profile_id

    try:
        await checking_msg.delete()
    except Exception:
        pass

    await update.message.reply_text(
        f"✅ <b>Основной аккаунт успешно привязан!</b>\n\n"
        f"Профиль: {user_message}\n"
        f"Ник на сайте: {site_nickname}\n\n"
        f"💎 <b>Желаете привязать дополнительные аккаунты (твины)?</b>\n\n"
        f"Это позволит управлять несколькими аккаунтами через одного бота.\n"
        f"Твины могут не состоять в клубе.",
        reply_markup=get_twink_question_keyboard(),
        parse_mode=ParseMode.HTML,
        link_preview_options=LinkPreviewOptions(is_disabled=True)
    )

    logger.info(f"Пользователь {user_id} успешно привязал основной аккаунт (ник: {site_nickname}), показан вопрос о твинах")


async def _handle_twink_linking(update, context, user, user_id, user_message):
    """Обработка привязки твинов"""
    profile_id = validate_profile_url(user_message)

    if not profile_id:
        await update.message.reply_text(
            "❌ <b>Неверный формат ссылки!</b>\n\n"
            "Пожалуйста, отправьте ссылку в формате:\n"
            "<code>https://mangabuff.ru/users/XXXXXX</code>\n\n"
            "где XXXXXX - от 1 до 7 цифр\n\n"
            "Или нажмите кнопку «Готово» для завершения, «Отмена» для отмены.",
            reply_markup=get_twink_done_keyboard(),
            parse_mode=ParseMode.HTML
        )
        return

    main_profile_id = context.user_data.get('main_profile_id')
    if profile_id == main_profile_id:
        await update.message.reply_text(
            "⚠️ <b>Это ваш основной аккаунт!</b>\n\n"
            "Отправьте ссылку на другой аккаунт (твин), нажмите «Готово» или «Отмена».",
            reply_markup=get_twink_done_keyboard(),
            parse_mode=ParseMode.HTML
        )
        return

    checking_msg = await update.message.reply_text("🔍 Проверяем профиль...")

    site_nickname = get_site_nickname(user_message.strip())
    if not site_nickname:
        site_nickname = f"User {profile_id}"
        logger.warning(f"Не удалось получить ник для твина {profile_id}")

    success = add_twink(user_id, user_message.strip(), profile_id, site_nickname)

    try:
        await checking_msg.delete()
    except Exception:
        pass

    if success:
        # ✅ Увеличиваем счётчик добавленных за сессию твинов
        current_count = context.user_data.get('twinks_added_this_session', 0)
        context.user_data['twinks_added_this_session'] = current_count + 1

        twinks_count = get_twinks_count(user_id)
        await update.message.reply_text(
            f"✅ <b>Твин успешно привязан!</b>\n\n"
            f"Профиль: {user_message}\n"
            f"Ник: {site_nickname}\n\n"
            f"💎 Всего твинов: {twinks_count}\n\n"
            f"Можете отправить ещё одну ссылку, нажать «Готово» или «Отмена».",
            reply_markup=get_twink_done_keyboard(),
            parse_mode=ParseMode.HTML,
            link_preview_options=LinkPreviewOptions(is_disabled=True)
        )
        logger.info(f"Пользователь {user_id} привязал твин {profile_id} (ник: {site_nickname})")
    else:
        await update.message.reply_text(
            "⚠️ <b>Этот твин уже привязан!</b>\n\n"
            "Отправьте ссылку на другой аккаунт, нажмите «Готово» или «Отмена».",
            reply_markup=get_twink_done_keyboard(),
            parse_mode=ParseMode.HTML
        )