import os
import asyncio
import logging
import urllib.parse
import aiohttp
from bs4 import BeautifulSoup
from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message

TOKEN = "ТВОЙ_ТОКЕН_ЗДЕСЬ"

bot = Bot(token=TOKEN)
dp = Dispatcher()

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
}

# --- ПОИСК ЧЕРЕЗ ОТКРЫТЫЙ HTML ПОИСКОВИКОВ ---
async def search_gdz_page(query: str) -> str | None:
    clean_query = f"{query} гдз решебник"
    encoded_query = urllib.parse.quote(clean_query)
    
    search_engines = [
        f"https://html.duckduckgo.com/html/?q={encoded_query}",
        f"https://search.brave.com/search?q={encoded_query}",
    ]

    async with aiohttp.ClientSession(headers=HEADERS) as session:
        for engine_url in search_engines:
            try:
                async with session.get(engine_url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                    if resp.status != 200:
                        continue
                    html = await resp.text()
                    soup = BeautifulSoup(html, "html.parser")

                    links = []
                    for a in soup.find_all("a", href=True):
                        href = a["href"]
                        if "uddg=" in href:
                            actual_url = href.split("uddg=")[-1].split("&")[0]
                            href = urllib.parse.unquote(actual_url)
                        if href.startswith("http"):
                            links.append(href)

                    for link in links:
                        if any(domain in link for domain in ["reshak.ru", "gdz.ru", "megaresheba", "vse-gdz", "gdzputina"]):
                            return link

                    if links and not any(skip in links[0] for skip in ["duckduckgo.com", "brave.com"]):
                        return links[0]
            except Exception as e:
                logging.error(f"Сбой источника: {e}")
                continue
    return None

async def extract_solution_images(url: str) -> list[str]:
    images = []
    try:
        async with aiohttp.ClientSession(headers=HEADERS) as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    return []
                html = await resp.text()

        soup = BeautifulSoup(html, "html.parser")

        if "reshak.ru" in url:
            for img in soup.find_all("img"):
                src = img.get("src", "")
                if any(x in src for x in ["reshebnik", "uploads", "tasks"]):
                    full_url = f"https://reshak.ru/{src.lstrip('/')}" if not src.startswith("http") else src
                    images.append(full_url)

        for img in soup.find_all("img"):
            src = img.get("src") or img.get("data-src") or img.get("data-original")
            if not src:
                continue
            if any(term in src.lower() for term in ["task", "nomer", "zadanie", "resh", "solution"]):
                if src.startswith("//"):
                    images.append(f"https:{src}")
                elif src.startswith("http"):
                    images.append(src)

    except Exception as e:
        logging.error(f"Ошибка парсинга: {e}")

    return list(dict.fromkeys(images))

# --- ХЕНДЛЕРЫ ---
@dp.message(CommandStart())
async def cmd_start(message: Message):
