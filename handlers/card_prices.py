"""
Обработчики для функционала цен на карты
✅ ИСПРАВЛЕНО: Валидация URL теперь принимает двойные слеши
"""
import logging
import re
import openpyxl
from io import BytesIO
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from database.db import (
    clear_all_card_prices, save_card_price, get_card_price,
    get_card_prices_count, is_staff, log_operator_action
)

logger = logging.getLogger(__name__)

# ID топика для оценки карт
CARD_EVALUATION_CHAT_ID = -1002234810541  # https://t.me/c/2234810541/423804
CARD_EVALUATION_THREAD_ID = 423804


def validate_card_url(url: str) -> str:
    """
    Проверяет формат URL карты и возвращает card_id
    
    ✅ ИСПРАВЛЕНО: Теперь принимает URL с одинарным или двойным слешем:
    - https://mangabuff.ru/cards/123456/users ✅
    - https://mangabuff.ru//cards/123456/users ✅
    
    Args:
        url: URL карты
    
    Returns:
        str: card_id или None если формат неверный
    """
    # Убираем лишние слеши из URL перед валидацией
    cleaned_url = re.sub(r'(?<!:)//+', '/', url.strip())
    
    # Валидируем очищенный URL
    pattern = r'https://mangabuff\.ru/cards/(\d{1,7})/users'
    match = re.match(pattern, cleaned_url)
    return match.group(1) if match else None


async def handle_card_price_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатия на кнопку 💳 Узнать цену Карты"""
    user_id = update.effective_user.id
    
    context.user_data['state'] = 'requesting_card_price'
    
    keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data='back_to_menu')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "💳 <b>Узнать цену карты</b>\n\n"
        "Отправьте ссылку на карту в формате:\n"
        "<code>https://mangabuff.ru/cards/XXXXXX/users</code>\n\n"
        "Где XXXXXX - это от 1 до 7 цифр (ID карты)\n\n"
        "<i>Пример: https://mangabuff.ru/cards/290263/users</i>",
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML
    )
    
    logger.info(f"Пользователь {user_id} запросил цену карты")


async def handle_card_url_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обработчик ссылки на карту от пользователя
    
    Вызывается когда user_state == 'requesting_card_price'
    """
    user = update.effective_user
    user_id = user.id
    card_url = update.message.text.strip()
    
    # Валидация URL
    card_id = validate_card_url(card_url)
    
    if not card_id:
        await update.message.reply_text(
            "❌ <b>Неверный формат ссылки!</b>\n\n"
            "Формат должен быть:\n"
            "<code>https://mangabuff.ru/cards/XXXXXX/users</code>\n\n"
            "Где XXXXXX - от 1 до 7 цифр",
            parse_mode=ParseMode.HTML
        )
        return
    
    # Проверяем наличие цены в БД
    price = get_card_price(card_id)
    
    if price is not None:
        # Цена найдена
        context.user_data['state'] = None
        
        # Нормализуем URL для отображения (убираем двойные слеши)
        display_url = re.sub(r'(?<!:)//+', '/', card_url)
        
        await update.message.reply_text(
            f"💰 <b>Цена на карту</b>\n\n"
            f"Карта: <code>{card_id}</code>\n"
            f"Цена: <b>{price} ОК</b>\n\n"
            f"<a href='{display_url}'>Ссылка на карту</a>",
            parse_mode=ParseMode.HTML
        )
        
        logger.info(f"Пользователь {user_id} получил цену карты {card_id}: {price} ОК")
    else:
        # Цена не найдена - предлагаем отправить на оценку
        context.user_data['card_url_for_evaluation'] = card_url
        context.user_data['card_id_for_evaluation'] = card_id
        context.user_data['state'] = 'card_evaluation_offer'
        
        keyboard = [
            [
                InlineKeyboardButton("✅ Да", callback_data='send_card_for_evaluation'),
                InlineKeyboardButton("❌ Нет", callback_data='cancel_card_evaluation')
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"ℹ️ <b>Цена на карту не найдена</b>\n\n"
            f"Карта: <code>{card_id}</code>\n"
            f"Ссылка: {card_url}\n\n"
            f"Хотите отправить карту на оценку?",
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML
        )
        
        logger.info(f"Пользователь {user_id} запросил несуществующую цену карты {card_id}")


async def handle_send_card_for_evaluation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопки "Да" для отправки карты на оценку"""
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    user_id = user.id
    
    card_url = context.user_data.get('card_url_for_evaluation')
    card_id = context.user_data.get('card_id_for_evaluation')
    
    if not card_url or not card_id:
        await query.edit_message_text(
            "❌ Ошибка: данные карты потеряны",
            parse_mode=ParseMode.HTML
        )
        return
    
    # Очищаем состояние
    context.user_data['state'] = None
    context.user_data['card_url_for_evaluation'] = None
    context.user_data['card_id_for_evaluation'] = None
    
    # Отправляем в топик для оценки
    try:
        from utils.helpers import get_user_link
        user_link = get_user_link(user_id, user.first_name or user.username or f"User {user_id}")
        
        message_text = (
            f"💳 <b>Запрос на оценку карты:</b>\n"
            f"{card_url}"
        )
        
        await context.bot.send_message(
            chat_id=CARD_EVALUATION_CHAT_ID,
            message_thread_id=CARD_EVALUATION_THREAD_ID,
            text=message_text,
            parse_mode=ParseMode.HTML
        )
        
        await query.edit_message_text(
            f"✅ <b>Карта отправлена на оценку!</b>\n\n"
            f"Карта: <code>{card_id}</code>\n"
            f"Ваш запрос будет рассмотрен Оценщиками.\n\n"
            f"Цена будет добавлена в базу данных после оценки.",
            parse_mode=ParseMode.HTML
        )
        
        logger.info(f"Пользователь {user_id} отправил карту {card_id} на оценку")
        
    except Exception as e:
        logger.error(f"Ошибка отправки карты на оценку: {e}")
        await query.edit_message_text(
            "❌ Ошибка при отправке карты на оценку.\n"
            "Попробуйте позже или обратитесь к оператору.",
            parse_mode=ParseMode.HTML
        )


async def handle_cancel_card_evaluation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопки "Нет" для отказа от оценки"""
    query = update.callback_query
    await query.answer("Операция отменена")
    
    # Очищаем состояние
    context.user_data['state'] = None
    context.user_data['card_url_for_evaluation'] = None
    context.user_data['card_id_for_evaluation'] = None
    
    await query.edit_message_text(
        "✅ Операция завершена",
        parse_mode=ParseMode.HTML
    )
    
    logger.info(f"Пользователь {query.from_user.id} отказался от оценки карты")


async def handle_upload_prices(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обработчик кнопки "Загрузить цены" для операторов
    
    Вызывается из команд оператора
    """
    user_id = update.effective_user.id
    
    if not is_staff(user_id):
        await update.callback_query.answer("❌ Недостаточно прав", show_alert=True)
        return
    
    query = update.callback_query
    await query.answer()
    
    context.user_data['state'] = 'uploading_prices'
    
    keyboard = [[InlineKeyboardButton("❌ Отмена", callback_data='cancel_upload_prices')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "📁 <b>Загрузка цен на карты</b>\n\n"
        "Отправьте Excel файл (.xlsx) со следующей структурой:\n\n"
        "• <b>Столбец A:</b> Ссылка на карту\n"
        "  (https://mangabuff.ru/cards/XXXXXX/users)\n"
        "• <b>Столбец B:</b> Цена (число)\n\n"
        "⚠️ <b>Внимание:</b> Все старые цены будут удалены!\n\n"
        "💡 <i>URL могут содержать двойные слеши - это нормально</i>",
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML
    )
    
    logger.info(f"Оператор {user_id} начал загрузку цен")


async def handle_cancel_upload_prices(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена загрузки цен"""
    query = update.callback_query
    await query.answer("Загрузка отменена")
    
    context.user_data['state'] = None
    
    await query.edit_message_text(
        "✅ Загрузка цен отменена",
        parse_mode=ParseMode.HTML
    )


async def handle_prices_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обработчик загрузки Excel файла с ценами
    
    ✅ ИСПРАВЛЕНО: Автоматически убирает двойные слеши из URL
    
    Вызывается когда user_state == 'uploading_prices'
    """
    user_id = update.effective_user.id
    
    if not is_staff(user_id):
        return
    
    document = update.message.document
    
    if not document:
        await update.message.reply_text("❌ Пожалуйста, отправьте файл")
        return
    
    # Проверяем расширение файла
    if not document.file_name.endswith(('.xlsx', '.xls')):
        await update.message.reply_text(
            "❌ Неверный формат файла!\n\n"
            "Отправьте Excel файл (.xlsx или .xls)",
            parse_mode=ParseMode.HTML
        )
        return
    
    try:
        # Скачиваем файл
        loading_msg = await update.message.reply_text("⏳ Загрузка файла...")
        
        file = await context.bot.get_file(document.file_id)
        file_bytes = await file.download_as_bytearray()
        
        await loading_msg.edit_text("📊 Обработка данных...")
        
        # Открываем Excel
        workbook = openpyxl.load_workbook(BytesIO(file_bytes))
        sheet = workbook.active
        
        # Удаляем все старые цены
        clear_all_card_prices()
        
        # Обрабатываем строки
        added_count = 0
        error_count = 0
        errors = []
        
        for row_idx, row in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=2):
            if not row or len(row) < 2:
                continue
            
            card_url = str(row[0]).strip() if row[0] else ""
            price_str = str(row[1]).strip() if row[1] else ""
            
            if not card_url or not price_str:
                continue
            
            # ✅ ИСПРАВЛЕНИЕ: Убираем двойные слеши из URL
            card_url = re.sub(r'(?<!:)//+', '/', card_url)
            
            # Валидация URL (уже очищенного)
            if not validate_card_url(card_url):
                error_count += 1
                errors.append(f"Строка {row_idx}: неверный URL '{card_url[:50]}'")
                if len(errors) >= 5000:
                    break
                continue
            
            # Валидация цены
            try:
                # Убираем запятые из чисел (если есть)
                price = float(price_str.replace(',', ''))
            except ValueError:
                error_count += 1
                errors.append(f"Строка {row_idx}: неверная цена '{price_str}'")
                if len(errors) >= 5000:
                    break
                continue
            
            # Сохраняем
            if save_card_price(card_url, price):
                added_count += 1
            else:
                error_count += 1
                errors.append(f"Строка {row_idx}: ошибка сохранения")
                if len(errors) >= 5000:
                    break
        
        # Очищаем состояние
        context.user_data['state'] = None
        
        # Формируем отчет
        report = (
            f"✅ <b>Цены успешно загружены!</b>\n\n"
            f"📥 Добавлено: <b>{added_count}</b>\n"
        )
        
        if error_count > 0:
            report += f"⚠️ Ошибок: <b>{error_count}</b>\n\n"
            
            if errors:
                error_list = "\n".join(errors[:5])  # Показываем первые 5 ошибок
                report += f"<b>Примеры ошибок:</b>\n<code>{error_list}</code>"
                
                if len(errors) > 5:
                    report += f"\n\n<i>... и ещё {len(errors) - 5} ошибок</i>"
        
        report += f"\n\n💾 Всего цен в БД: <b>{get_card_prices_count()}</b>"
        
        await loading_msg.edit_text(report, parse_mode=ParseMode.HTML)
        
        # Логируем действие
        log_operator_action(
            user_id,
            'prices_uploaded',
            details=f"Добавлено: {added_count}, Ошибок: {error_count}"
        )
        
        logger.info(f"Оператор {user_id} загрузил цены: {added_count} успешно, {error_count} ошибок")
        
    except Exception as e:
        logger.error(f"Ошибка обработки файла с ценами: {e}", exc_info=True)
        await update.message.reply_text(
            f"❌ Ошибка обработки файла:\n\n<code>{str(e)}</code>",
            parse_mode=ParseMode.HTML
        )
        context.user_data['state'] = None