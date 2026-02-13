"""
Обработчик функционала "Хотелки"
✅ Парсинг хотелок пользователя и общага
✅ Проверка цен на карты
✅ Группировка результатов по 10 карт
✅ ОБНОВЛЕНО: Формат "Имя карты Ранг ранга есть у вас Ссылка"
✅ АСИНХРОННЫЙ: Парсинг не блокирует обработку других запросов
"""
import logging
import re
import json
import asyncio
from typing import List, Set, Optional, Tuple, Dict
from bs4 import BeautifulSoup
import requests
import csv
from io import StringIO

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from config.settings import BASE_URL, REQUEST_TIMEOUT
from database.db import get_card_price, get_user_info
from utils.helpers import site_session
from utils.sheets_parser import get_sheets_parser

logger = logging.getLogger(__name__)

# ID общага (фиксированный)
OBSHAGA_USER_ID = "309607"


# ══════════════════════════════════════════════════════════════
# ПАРСИНГ КАРТ
# ══════════════════════════════════════════════════════════════

def parse_card_ids_from_page(html: str) -> Set[str]:
    """
    Извлекает все data-card-id из HTML страницы
    
    Пример: <div data-card-id="145928">
    
    Returns:
        Set[str]: Множество ID карт
    """
    soup = BeautifulSoup(html, 'html.parser')
    card_ids = set()
    
    # Ищем все элементы с атрибутом data-card-id
    for element in soup.find_all(attrs={'data-card-id': True}):
        card_id = element.get('data-card-id')
        if card_id:
            card_ids.add(str(card_id))
    
    return card_ids


def get_total_pages(html: str) -> int:
    """
    Определяет общее количество страниц из пагинации
    
    Returns:
        int: Количество страниц (минимум 1)
    """
    try:
        soup = BeautifulSoup(html, 'html.parser')
        pagination = soup.find('ul', class_='pagination')
        
        if not pagination:
            return 1
        
        max_page = 1
        for btn in pagination.find_all('li', class_='pagination__button'):
            a = btn.find('a')
            if a and a.get_text(strip=True).isdigit():
                max_page = max(max_page, int(a.get_text(strip=True)))
        
        return max_page
    except Exception as e:
        logger.error(f"Ошибка определения количества страниц: {e}")
        return 1


def parse_all_offers(profile_id: str, session=None):
    """Парсит все хотелки пользователя"""
    
    # ✅ ИСПРАВЛЕНИЕ: Используем глобальную сессию
    if session is None:
        from utils.helpers import site_session
        session = site_session
    
    # Проверяем что сессия есть
    if session is None:
        logger.error("❌ Сессия не инициализирована для загрузки хотелок")
        return []
    
    base_url = f"{BASE_URL}/cards/{profile_id}/offers"
    response = session.get(base_url, timeout=REQUEST_TIMEOUT)
    all_card_ids = set()
    
    try:
        # Загружаем первую страницу чтобы узнать количество страниц
        logger.info(f"📄 Загрузка хотелок пользователя {profile_id}...")
        response = session.get(base_url, timeout=REQUEST_TIMEOUT)
        
        if response.status_code != 200:
            logger.error(f"Ошибка загрузки страницы хотелок: {response.status_code}")
            return all_card_ids
        
        # Парсим первую страницу
        page_cards = parse_card_ids_from_page(response.text)
        all_card_ids.update(page_cards)
        logger.info(f"  Страница 1: найдено {len(page_cards)} карт")
        
        # Определяем количество страниц
        total_pages = get_total_pages(response.text)
        logger.info(f"  Всего страниц: {total_pages}")
        
        # Парсим остальные страницы
        for page in range(2, total_pages + 1):
            page_url = f"{base_url}?page={page}"
            logger.debug(f"  Загрузка страницы {page}/{total_pages}...")
            
            response = session.get(page_url, timeout=REQUEST_TIMEOUT)
            
            if response.status_code != 200:
                logger.warning(f"Ошибка загрузки страницы {page}: {response.status_code}")
                continue
            
            page_cards = parse_card_ids_from_page(response.text)
            all_card_ids.update(page_cards)
            logger.info(f"  Страница {page}: найдено {len(page_cards)} карт")
        
        logger.info(f"✅ Всего хотелок: {len(all_card_ids)}")
        return all_card_ids
        
    except Exception as e:
        logger.error(f"Ошибка парсинга хотелок: {e}", exc_info=True)
        return all_card_ids


def parse_all_user_cards(profile_id: str, session: requests.Session, locked: bool = False) -> Set[str]:
    """
    Парсит все карты пользователя (все страницы /users/{id}/cards)
    
    Args:
        profile_id: ID профиля
        session: Сессия requests
        locked: Если False, парсит только незакрытые карты (?lock=0)
    
    Returns:
        Set[str]: Множество ID карт
    """
    """Парсит все карты пользователя"""
    
    # ✅ ИСПРАВЛЕНИЕ: Используем глобальную сессию
    if session is None:
        from utils.helpers import site_session
        session = site_session
    
    if session is None:
        logger.error("❌ Сессия не инициализирована для загрузки карт")
        return []
    
    base_url = f"{BASE_URL}/users/{profile_id}/cards"
    if not locked:
        base_url += "?lock=0"
    
    all_card_ids = set()
    
    try:
        # Загружаем первую страницу
        logger.info(f"📄 Загрузка карт пользователя {profile_id}...")
        response = session.get(base_url, timeout=REQUEST_TIMEOUT)
        
        if response.status_code != 200:
            logger.error(f"Ошибка загрузки карт: {response.status_code}")
            return all_card_ids
        
        # Парсим первую страницу
        page_cards = parse_card_ids_from_page(response.text)
        all_card_ids.update(page_cards)
        logger.info(f"  Страница 1: найдено {len(page_cards)} карт")
        
        # Определяем количество страниц
        total_pages = get_total_pages(response.text)
        logger.info(f"  Всего страниц: {total_pages}")
        
        # Парсим остальные страницы
        for page in range(2, total_pages + 1):
            separator = "&" if not locked else "?"
            page_url = f"{base_url}{separator}page={page}"
            logger.debug(f"  Загрузка страницы {page}/{total_pages}...")
            
            response = session.get(page_url, timeout=REQUEST_TIMEOUT)
            
            if response.status_code != 200:
                logger.warning(f"Ошибка загрузки страницы {page}: {response.status_code}")
                continue
            
            page_cards = parse_card_ids_from_page(response.text)
            all_card_ids.update(page_cards)
            logger.info(f"  Страница {page}: найдено {len(page_cards)} карт")
        
        logger.info(f"✅ Всего карт: {len(all_card_ids)}")
        return all_card_ids
        
    except Exception as e:
        logger.error(f"Ошибка парсинга карт: {e}", exc_info=True)
        return all_card_ids


def parse_obshaga_wishlist_from_sheet() -> Dict[str, Dict[str, str]]:
    """
    ✅ ОБНОВЛЕНО: Парсит хотелки общага из Google Sheets с именем и рангом
    
    Столбцы:
    - A: Имя карты
    - B: Ранг карты  
    - C: Ссылка на карту
    
    Returns:
        Dict[str, Dict[str, str]]: {
            'card_id': {
                'name': 'Имя карты',
                'rank': 'C'
            },
            ...
        }
    """
    WISHLIST_SHEET_GID = "1363566974"
    SPREADSHEET_ID = "1sYvrBU9BPhcoxTnNJfx8TOutxwFrSiRm2mw_8s6rdZM"
    
    url = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/export?format=csv&gid={WISHLIST_SHEET_GID}"
    
    try:
        logger.info("📊 Загрузка хотелок общага из Google Sheets...")
        response = requests.get(url, timeout=30)
        response.encoding = 'utf-8'
        
        if response.status_code != 200:
            logger.error(f"Ошибка загрузки таблицы: {response.status_code}")
            return {}
        
        card_data = {}
        
        # Парсим CSV
        csv_data = StringIO(response.text)
        reader = csv.reader(csv_data)
        
        # Пропускаем заголовок
        next(reader, None)
        
        # Столбцы: A=0 (имя), B=1 (ранг), C=2 (ссылка)
        for row in reader:
            if len(row) < 3:  # Проверяем что есть все нужные столбцы
                continue
            
            card_name = row[0].strip()
            card_rank = row[1].strip()
            card_url = row[2].strip()
            
            # Извлекаем ID карты из ссылки
            match = re.search(r'/cards/(\d+)/', card_url)
            if match:
                card_id = match.group(1)
                card_data[card_id] = {
                    'name': card_name,
                    'rank': card_rank
                }
            elif card_url.isdigit():
                # Если в столбце C просто ID
                card_data[card_url] = {
                    'name': card_name,
                    'rank': card_rank
                }
        
        logger.info(f"✅ Найдено {len(card_data)} карт в хотелках общага с именами и рангами")
        return card_data
        
    except Exception as e:
        logger.error(f"Ошибка парсинга таблицы: {e}", exc_info=True)
        return {}


# ══════════════════════════════════════════════════════════════
# ОБРАБОТЧИКИ
# ══════════════════════════════════════════════════════════════

async def handle_my_wishlist_in_obshaga(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обработчик: "Мои хотелки у общага"
    
    1. Парсит хотелки пользователя
    2. Парсит карты общага
    3. Находит пересечения
    4. Проверяет цены
    5. Отправляет результат группами по 10
    """
    query = update.callback_query
    user_id = query.from_user.id
    
    # Получаем выбранный профиль из context
    selected_profile_id = context.user_data.get('selected_profile_id')
    
    if not selected_profile_id:
        await query.answer("❌ Ошибка: профиль не выбран", show_alert=True)
        return
    
    # Отправляем сообщение о начале поиска
    await query.answer()
    loading_msg = await query.message.edit_text(
        "🔍 <b>Поиск ваших хотелок в общаге...</b>\n\n"
        "⏳ Это может занять несколько минут, пожалуйста подождите.",
        parse_mode=ParseMode.HTML
    )
    
    try:
        # 1. Парсим хотелки пользователя
        user_wishlist = parse_all_offers(selected_profile_id, site_session)
        
        if not user_wishlist:
            await loading_msg.edit_text(
                "😔 <b>У вас нет хотелок</b>\n\n"
                "Добавьте карты в хотелки на сайте MangaBuff.",
                parse_mode=ParseMode.HTML
            )
            return
        
        await loading_msg.edit_text(
            f"✅ Найдено {len(user_wishlist)} ваших хотелок\n\n"
            f"🔍 Проверяю карты общага...",
            parse_mode=ParseMode.HTML
        )
        
        # 2. Парсим карты общага
        obshaga_cards = parse_all_user_cards(OBSHAGA_USER_ID, site_session, locked=False)
        
        if not obshaga_cards:
            await loading_msg.edit_text(
                "❌ <b>Ошибка загрузки карт общага</b>\n\n"
                "Попробуйте позже.",
                parse_mode=ParseMode.HTML
            )
            return
        
        await loading_msg.edit_text(
            f"✅ Найдено {len(obshaga_cards)} карт в общаге\n\n"
            f"🔍 Ищу совпадения...",
            parse_mode=ParseMode.HTML
        )
        
        # 3. Находим пересечения
        matches = user_wishlist & obshaga_cards
        
        if not matches:
            await loading_msg.edit_text(
                "😔 <b>К сожалению, ваших хотелок нет в общаге</b>\n\n"
                f"Проверено:\n"
                f"• Ваши хотелки: {len(user_wishlist)}\n"
                f"• Карты общага: {len(obshaga_cards)}",
                parse_mode=ParseMode.HTML
            )
            return
        
        logger.info(f"✅ Найдено {len(matches)} совпадений")
        
        # 4. Проверяем цены и формируем результат
        await loading_msg.edit_text(
            f"✅ Найдено {len(matches)} совпадений!\n\n"
            f"💰 Проверяю цены...",
            parse_mode=ParseMode.HTML
        )
        
        results = []
        for card_id in matches:
            price = get_card_price(card_id)
            price_str = f"{price} ОК" if price is not None else "Цена неизвестна"
            
            results.append({
                'card_id': card_id,
                'price': price_str,
                'url': f"{BASE_URL}/cards/{card_id}/users"
            })
        
        # Сортируем по цене (карты с известной ценой первые)
        results.sort(key=lambda x: (x['price'] == "Цена неизвестна", x['card_id']))
        
        # 5. Отправляем результат группами по 5
        await loading_msg.delete()
        
        # Отправляем заголовок
        await context.bot.send_message(
            chat_id=user_id,
            text=(
                f"🎉 <b>Ваши хотелки в общаге ({len(results)})</b>\n\n"
                f"Найдено {len(results)} карт из ваших хотелок:"
            ),
            parse_mode=ParseMode.HTML
        )
        
        # Отправляем группами по 10
        for i in range(0, len(results), 10):
            batch = results[i:i+10]
            
            text = "\n\n".join([
                f"🎴 <a href='{r['url']}'>Карта {r['card_id']}</a>\n"
                f"💰 Цена: <b>{r['price']}</b>"
                for r in batch
            ])
            
            await context.bot.send_message(
                chat_id=user_id,
                text=text,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True
            )
        
        logger.info(f"Отправлено {len(results)} карт пользователю {user_id}")
        
    except Exception as e:
        logger.error(f"Ошибка поиска хотелок: {e}", exc_info=True)
        await loading_msg.edit_text(
            f"❌ <b>Произошла ошибка</b>\n\n"
            f"Попробуйте позже или обратитесь к оператору.",
            parse_mode=ParseMode.HTML
        )


async def handle_obshaga_wishlist_with_me(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    ✅ ОБНОВЛЕНО: Формат "Имя карты Ранг ранга есть у вас Ссылка"
    
    Обработчик: "Хотелки общага у меня"
    
    1. Парсит незакрытые карты пользователя (?lock=0)
    2. Загружает хотелки общага из Google Sheets (с именем и рангом)
    3. Находит пересечения
    4. Отправляет результат группами по 10
    
    ✅ Асинхронный - не блокирует обработку других запросов
    """
    query = update.callback_query
    user_id = query.from_user.id
    
    # Получаем выбранный профиль
    selected_profile_id = context.user_data.get('selected_profile_id')
    
    if not selected_profile_id:
        await query.answer("❌ Ошибка: профиль не выбран", show_alert=True)
        return
    
    # Отправляем сообщение о начале поиска
    await query.answer()
    loading_msg = await query.message.edit_text(
        "🔍 <b>Поиск хотелок общага у вас...</b>\n\n"
        "⏳ Это может занять несколько минут, пожалуйста подождите.",
        parse_mode=ParseMode.HTML
    )
    
    try:
        # 1. Парсим незакрытые карты пользователя (в отдельном потоке)
        user_cards = await asyncio.to_thread(
            parse_all_user_cards, selected_profile_id, site_session, False
        )
        
        if not user_cards:
            await loading_msg.edit_text(
                "😔 <b>У вас нет незакрытых карт</b>",
                parse_mode=ParseMode.HTML
            )
            return
        
        await loading_msg.edit_text(
            f"✅ Найдено {len(user_cards)} ваших незакрытых карт\n\n"
            f"📊 Загружаю хотелки общага...",
            parse_mode=ParseMode.HTML
        )
        
        # 2. Парсим хотелки общага из таблицы (в отдельном потоке)
        obshaga_wishlist = await asyncio.to_thread(parse_obshaga_wishlist_from_sheet)
        
        if not obshaga_wishlist:
            await loading_msg.edit_text(
                "❌ <b>Ошибка загрузки хотелок общага</b>\n\n"
                "Попробуйте позже.",
                parse_mode=ParseMode.HTML
            )
            return
        
        await loading_msg.edit_text(
            f"✅ Найдено {len(obshaga_wishlist)} хотелок общага\n\n"
            f"🔍 Ищу совпадения...",
            parse_mode=ParseMode.HTML
        )
        
        # 3. Находим пересечения
        obshaga_card_ids = set(obshaga_wishlist.keys())
        matches = user_cards & obshaga_card_ids
        
        if not matches:
            await loading_msg.edit_text(
                "😔 <b>У вас нет карт из хотелок общага</b>\n\n"
                f"Проверено:\n"
                f"• Ваши карты: {len(user_cards)}\n"
                f"• Хотелки общага: {len(obshaga_wishlist)}",
                parse_mode=ParseMode.HTML
            )
            return
        
        logger.info(f"✅ Найдено {len(matches)} совпадений")
        
        # 4. Формируем результат с именем и рангом
        results = []
        for card_id in sorted(matches):
            card_info = obshaga_wishlist[card_id]
            results.append({
                'card_id': card_id,
                'name': card_info['name'],
                'rank': card_info['rank'],
                'url': f"{BASE_URL}/cards/{card_id}/users"
            })
        
        # 5. Отправляем результат
        await loading_msg.delete()
        
        # Заголовок
        await context.bot.send_message(
            chat_id=user_id,
            text=(
                f"🎉 <b>Хотелки общага у вас ({len(results)})</b>\n\n"
                f"Найдено {len(results)} карт из хотелок общага:"
            ),
            parse_mode=ParseMode.HTML
        )
        
        # ✅ НОВЫЙ ФОРМАТ: "Имя карты Ранг ранга есть у вас Ссылка"
        for i in range(0, len(results), 10):
            batch = results[i:i+10]
            
            text = "\n\n".join([
                f"🎴 <b>{r['name']}</b> {r['rank']} ранга есть у вас\n"
                f"<a href='{r['url']}'>Ссылка на карту</a>"
                for r in batch
            ])
            
            await context.bot.send_message(
                chat_id=user_id,
                text=text,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True
            )
        
        logger.info(f"Отправлено {len(results)} карт пользователю {user_id}")
        
    except Exception as e:
        logger.error(f"Ошибка поиска хотелок общага: {e}", exc_info=True)
        await loading_msg.edit_text(
            f"❌ <b>Произошла ошибка</b>\n\n"   
            f"Попробуйте позже или обратитесь к оператору.",
            parse_mode=ParseMode.HTML
        )