import os
import asyncio
import logging
import urllib.parse
import aiohttp
from bs4 import BeautifulSoup
from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message, BufferedInputFile

# Вставь свой токен сюда или пропиши переменную окружения BOT_TOKEN
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
    "znanija.com",
]

# --- ПОИСК С ФОЛЛБЕКАМИ (НЕ ПАДАЕТ ОТ БАНОВ ПО IP) ---
async def search_gdz_page(query: str) -> tuple[str | None, str | None]:
    clean_query = f"{query} гдз"
    encoded_q = urllib.parse.quote(clean_query)

    # 1. Попытка через публичные инстансы SearXNG и DuckDuckGo HTML
    search_urls = [
        f"https://html.duckduckgo.com/html/?q={encoded_q}",
        f"https://search.brave.com/search?q={encoded_q}",
    ]

    async with aiohttp.ClientSession(headers=HEADERS) as session:
        for

