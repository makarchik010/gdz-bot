import os
import asyncio
import logging
import re
import aiohttp
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS
from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message, BufferedInputFile

TOKEN = os.getenv("BOT_TOKEN", "ТВОЙ_ТОКЕН_ЗДЕСЬ")

bot = Bot(token=TOKEN)
dp = Dispatcher()

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
}

WHITELIST_DOMAINS = [
    "reshak.ru",
    "gdz.ru",
    "megaresheba.ru",
    "gdzputina.ru",
    "vse-gdz.ru",
    "znanija.com"
]

# --- 1. СТАБИЛЬНЫЙ ПОИСК ЧЕРЕЗ DUCKDUCKGO ---
async def search_gdz_page(query: str) -> tuple[str | None, str | None]:
    clean_query = f"{query} гдз решебник"
    
    def _search():
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(clean_query, region="ru-ru", max_results=8))
                return results
        except Exception as e:
            logging.error(f"DDGS error: {e}")
            return []

    # Выполняем синхронный запрос к DDG в отдельном потоке
    results = await asyncio.to_thread(_search)
    
    if not results:
        return None, None

    # Приоритет 1: сайты из белого списка
    for item in results:
        url = item.get("href", "")
        title = item.get("title", "")
        if any(domain in url for domain in WHITELIST_DOMAINS):
            return url, title

    # Приоритет 2: любая первая ссылка
    first = results[0]
    return first.get("href"), first.get("title")

# --- 2. ВЫТЯГИВАНИЕ ССЫЛОК НА КАРТИНКИ РЕШЕНИЙ ---
async def get_solution_images(page_url: str) -> list[str]:
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        try:
            async with session.get(page_url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                if resp.status != 200:
                    return []
                html = await resp.text()
        except Exception as e:
            logging.error(f"Ошибка загрузки страницы {page_url}: {e}")
            return []

    soup = BeautifulSoup(html, "html.parser")
    found_urls = []

    # Специфика reshak.ru (наиболее надежный для чистого парсинга)
    if "reshak.ru" in page_url:
        for img in soup.find_all("img"):
            src = img.get("src") or img.get("data-src") or ""
            # Отсекаем иконки интерфейса, шапки и рекламу
            if any(key in src for key in ["reshebnik", "uploads", "tasks", "content"]) and not any(bad in src for bad in ["logo", "banner", "icon", "star"]):
                full_url = f"https://reshak.ru/{src.lstrip('/')}" if not src.startswith("http") else src
                found_urls.append(full_url)

    # Общая логика для остальных сайтов
    if not found_urls:
        for img in soup.find_all("img"):
            src = img.get("src") or img.get("data-src") or img.get("data-original") or ""
            if not src:
                continue
            
            src_lower = src.lower()
            if any(term in src_lower for term in ["task", "nomer", "zadanie", "resh", "solution"]):
                if not any(bad in src_lower for bad in ["logo", "avatar", "icon", "counter", "banner"]):
                    if src.startswith("//"):
                        found_urls.append(f"https:{src}")
                    elif src.startswith("http"):
                        found_urls.append(src)

    return list(dict.fromkeys(found_urls))

# --- 3. СКАЧИВАНИЕ КАРТИНКИ В ПАМЯТЬ С REFERER ---
async def download_image_bytes(img_url: str, referer: str) -> bytes | None:
    headers = HEADERS.copy()
    headers["Referer"] = referer  # Без этого сайт даёт 403 Forbidden
    
    async with aiohttp.ClientSession(headers=headers) as session:
        try:
            async with session.get(img_url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    return await resp.read()
        except Exception as e:
            logging.error(f"Не удалось скачать картин
