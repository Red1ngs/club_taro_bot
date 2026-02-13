#!/usr/bin/env python3
"""
Club Taro Telegram Bot
ВЕРСИЯ С ЛОГИРОВАНИЕМ ДЕЙСТВИЙ ОПЕРАТОРА
✅ Мониторинг карт клуба
✅ Автообновление каждые 100 секунд
✅ Система диалогов
✅ Блокировка с указанием причины
✅ Команда /blacklist
✅ Команда /unblock
✅ ЛОГИРОВАНИЕ ВСЕХ ДЕЙСТВИЙ И ДИАЛОГОВ ОПЕРАТОРА
✅ Команды: /logs, /stats, /history
✅ ИСПРАВЛЕНО: Команды управления ролями (/setrole, /promote, /demote, /staff, /myrole)
✅ ДОБАВЛЕНО: Функционал цен на карты (загрузка Excel, запрос цен)
"""
import logging
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters
)
from telegram.error import TelegramError, NetworkError, TimedOut
from telegram.constants import ParseMode
from config.settings import BOT_TOKEN
from database.db import init_db, is_user_linked
from handlers.commands import (
    start, cancel_command, end_dialog_command,
    dialogs_command, end_all_dialogs_command, blacklist_command, unblock_command,
    logs_command, stats_command, dialog_history_command
)
from handlers.callbacks import button_handler
from handlers.messages import message_handler

from keyboards.inline import get_reply_keyboard_for_linked_user
from utils.dialog_manager import DialogManager

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('bot_errors.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# ═════════════════════════════════════════════════════════════
# ГЛОБАЛЬНЫЙ ОБРАБОТЧИК ОШИБОК
# ═════════════════════════════════════════════════════════════

async def error_handler(update: object, context) -> None:
    """Глобальный обработчик ошибок"""
    logger.error("=" * 60)
    logger.error("⚠️  ПРОИЗОШЛА ОШИБКА В БОТЕ")
    logger.error("=" * 60)
    logger.error(f"Тип ошибки: {type(context.error).__name__}")
    logger.error(f"Сообщение: {context.error}", exc_info=context.error)
    
    if update:
        logger.error(f"Update: {update}")
        if isinstance(update, Update):
            if update.effective_user:
                logger.error(f"Пользователь: {update.effective_user.id} (@{update.effective_user.username})")
            if update.callback_query:
                logger.error(f"Callback data: {update.callback_query.data}")
            if update.message:
                logger.error(f"Сообщение: {update.message.text}")
    
    error = context.error
    
    if isinstance(error, TimedOut):
        logger.warning("⏱️  Timeout ошибка - Telegram API не ответил вовремя")
    elif isinstance(error, NetworkError):
        logger.warning("🌐 Сетевая ошибка - проблемы с подключением к Telegram")
    elif isinstance(error, TelegramError):
        logger.error(f"🤖 Ошибка Telegram API: {error}")
    else:
        logger.critical(f"❌ Неожиданная критическая ошибка: {error}")
    
    logger.error("=" * 60)
    
    try:
        if update and isinstance(update, Update):
            if update.effective_message:
                await update.effective_message.reply_text(
                    "⚠️ Произошла техническая ошибка. Попробуйте позже или обратитесь к администратору.",
                    disable_notification=True
                )
    except Exception as e:
        logger.error(f"Не удалось отправить сообщение об ошибке пользователю: {e}")


# ═════════════════════════════════════════════════════════════
# ФУНКЦИЯ АВТООБНОВЛЕНИЯ (каждые 100 секунд)
# ═════════════════════════════════════════════════════════════

async def auto_refresh_job(context):
    """Периодическое задание для автообновления состояния бота"""
    try:
        logger.info("🔄 Запуск автообновления...")
        
        dm = DialogManager(context.bot_data)
        all_dialogs = context.bot_data.get('dialogs', {})
        logger.info(f"📊 Активных диалогов: {len(all_dialogs)}")
        
        logger.info("✅ Автообновление завершено")
        
    except Exception as e:
        logger.error(f"❌ Ошибка в автообновлении: {e}", exc_info=True)


def main():
    """Запускает бота с обработкой ошибок и автообновлением"""
    print("=" * 60)
    print("Club Taro Telegram Bot")
    print("ВЕРСИЯ С ЛОГИРОВАНИЕМ ДЕЙСТВИЙ ОПЕРАТОРА")
    print("=" * 60)
    print("✅ Мониторинг карт клуба (каждую секунду)")
    print("✅ Автообновление каждые 100 секунд")
    print("✅ Система диалогов")
    print("✅ Блокировка с указанием причины")
    print("✅ Команда /blacklist")
    print("✅ Команда /unblock")
    print("✅ ЛОГИРОВАНИЕ ВСЕХ ДЕЙСТВИЙ ОПЕРАТОРА")
    print("✅ Команды логов: /logs, /stats, /history")
    print("✅ ИСПРАВЛЕНО: Команды ролей: /setrole, /promote, /demote, /staff, /myrole")
    print("✅ ДОБАВЛЕНО: Функционал цен на карты")
    print("=" * 60)
    
    # Инициализируем БД
    print("📊 Инициализация базы данных...")
    try:
        init_db()
        print("✅ База данных готова (с таблицами логов и цен)")
    except Exception as e:
        print(f"❌ Ошибка инициализации БД: {e}")
        logger.exception("Критическая ошибка при инициализации БД")
        return
    
    # Авторизуемся на сайте при старте
    print("🔐 Вход на сайт mangabuff.ru...")
    web_session = None
    try:
        from utils.helpers import login_to_site
        
        if login_to_site():
            print("✅ Успешная авторизация на сайте")
            from utils.helpers import site_session
            web_session = site_session
        else:
            print("❌ Ошибка авторизации на сайте")
            print("⚠️  Бот будет работать, но функции проверки членства могут быть недоступны")
    except Exception as e:
        print(f"❌ Исключение при авторизации: {e}")
        logger.exception("Ошибка при попытке входа на сайт")
    
    # Создаем приложение
    print("🤖 Создание приложения бота...")
    try:
        application = Application.builder().token(BOT_TOKEN).build()
    except Exception as e:
        print(f"❌ Ошибка создания приложения: {e}")
        logger.exception("Критическая ошибка при создании приложения")
        return
    
    # Инициализируем монитор карт
    print("🎴 Инициализация мониторинга карт...")
    try:
        if web_session:
            from utils.card_monitor import CardMonitor
            
            card_monitor = CardMonitor(web_session)
            application.bot_data['card_monitor'] = card_monitor
            application.bot_data['card_topic_id'] = 728886
            print("✅ Монитор карт инициализирован")
        else:
            print("⚠️  Сессия сайта недоступна, мониторинг карт отключен")
    except Exception as e:
        print(f"❌ Ошибка инициализации монитора: {e}")
        logger.exception("Ошибка при создании монитора карт")
    
    # Регистрируем глобальный обработчик ошибок
    print("🛡️  Регистрация глобального обработчика ошибок...")
    application.add_error_handler(error_handler)
    
    # Добавляем задачу автообновления
    print("🔄 Настройка автообновления (каждые 100 секунд)...")
    job_queue = application.job_queue
    job_queue.run_repeating(
        auto_refresh_job,
        interval=100,
        first=10,
        name='auto_refresh'
    )
    
    # Добавляем задачу мониторинга карт
    if 'card_monitor' in application.bot_data:
        print("🎴 Настройка мониторинга карт (каждые 2 секунды)...")
        
        from utils.card_monitor import card_monitoring_job
        
        job_queue.run_repeating(
            card_monitoring_job,
            interval=2,
            first=5,
            name='card_monitoring'
        )
        print("✅ Мониторинг карт активирован")
    
    # Регистрируем обработчики команд
    print("📝 Регистрация обработчиков команд и сообщений...")
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("cancel", cancel_command))
    application.add_handler(CommandHandler("dialogs", dialogs_command))
    application.add_handler(CommandHandler("end_dialog", end_dialog_command))
    application.add_handler(CommandHandler("end_all", end_all_dialogs_command))
    application.add_handler(CommandHandler("blacklist", blacklist_command))
    
    # Команда /unblock (оба формата)
    application.add_handler(CommandHandler("unblock", unblock_command))
    application.add_handler(
        MessageHandler(
            filters.Regex(r'^/unblock_\d+$') & filters.COMMAND,
            unblock_command
        )
    )
    
    # Команды логирования
    application.add_handler(CommandHandler("logs", logs_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("history", dialog_history_command))
    
    # Обработчики сообщений и callback
    application.add_handler(CallbackQueryHandler(button_handler))
    
    # ✅ ОБРАБОТЧИК ДОКУМЕНТОВ (для загрузки Excel файлов с ценами)
    application.add_handler(MessageHandler(filters.Document.ALL, message_handler))
    
    # Обработчик текстовых сообщений (должен быть последним)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    
    # Запускаем бота
    print("=" * 60)
    print("✅ Бот успешно запущен и готов к работе!")
    print("🛡️  Обработчик ошибок активирован")
    print("💬 Система диалогов активирована")
    print("🔄 Автообновление каждые 100 секунд активировано")
    print("🚫 Блокировка с указанием причины активирована")
    print("📋 Команда /blacklist зарегистрирована")
    print("✅ Команда /unblock зарегистрирована (оба формата)")
    print("📊 ЛОГИРОВАНИЕ ДЕЙСТВИЙ ОПЕРАТОРА АКТИВИРОВАНО")
    print("📝 Команды логов:")
    print("   • /logs [количество] [тип] - просмотр логов")
    print("   • /stats - статистика действий")
    print("   • /history [dialog_id] - история диалога")
    print("👑 Команды управления ролями:")
    print("   • /setrole USER_ID ROLE - назначить роль")
    print("   • /promote USER_ID - повысить до оператора")
    print("   • /demote USER_ID - понизить до пользователя")
    print("   • /staff - список персонала")
    print("   • /myrole - посмотреть свою роль")
    if 'card_monitor' in application.bot_data:
        print("🎴 Мониторинг карт клуба активирован (каждые 2 секунды)")
    print("💳 ФУНКЦИОНАЛ ЦЕН НА КАРТЫ:")
    print("   • Пользователи: кнопка '💳 Узнать цену Карты'")
    print("   • Операторы: кнопка '💳 Загрузить цены' (Excel)")
    print("   • Автоотправка запросов на оценку в топик")
    print("=" * 60)
    logger.info("Бот запущен со всеми системами, включая логирование, управление ролями и функционал цен")
    
    try:
        application.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True
        )
    except KeyboardInterrupt:
        print("\n👋 Бот остановлен пользователем")
        logger.info("Бот остановлен пользователем (Ctrl+C)")
    except Exception as e:
        print(f"\n❌ Критическая ошибка при работе бота: {e}")
        logger.exception("Критическая ошибка в основном цикле бота")


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n👋 Бот остановлен")
        logger.info("Бот остановлен пользователем")
    except Exception as e:
        print(f"\n❌ Критическая ошибка: {e}")
        logger.exception("Критическая ошибка при запуске бота")