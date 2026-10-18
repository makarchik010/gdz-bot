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
        for engine_url in search_urls:
            try:
                async with session.get(engine_url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status != 200:
                        continue
                    html = await resp.text()
                    soup = BeautifulSoup(html, "html.parser")

                    found_urls = []
                    for a in soup.find_all("a", href=True):
                        href = a["href"]
                        if "uddg=" in href:
                            href = urllib.parse.unquote(href.split("uddg=")[-1].split("&")[0])
                        if href.startswith("http") and not any(skip in href for skip in ["duckduckgo", "brave.com"]):
                            found_urls.append(href)

                    # Ищем сайты из белого списка
                    for link in found_urls:
                        if any(d in link for d in WHITELIST_DOMAINS):
                            return link, query

                    if found_urls:
                        return found_urls[0], query
            except Exception as e:
                logging.warning(f"Ошибка поиска через {engine_url}: {e}")

    # 2. Фолбек: прямой поиск по Reshak.ru (для алгебры, геометрии, физики, англа)
    try:
        direct_url = f"https://reshak.ru/poisk.php?q={urllib.parse.quote(query)}"
        async with aiohttp.ClientSession(headers=HEADERS) as session:
            async with session.get(direct_url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status == 200:
                    html = await resp.text()
                    soup = BeautifulSoup(html, "html.parser")
                    for a in soup.find_all("a", href=True):
                        href = a["href"]
                        if any(x in href for x in ["otvet", "reshebniki"]) and not href.endswith(".php"):
                            full = f"https://reshak.ru/{href.lstrip('/')}" if not href.startswith("http") else href
                            return full, f"Решение на Reshak: {query}"
    except Exception as e:
        logging.error(f"Фолбек поиск упал: {e}")

    return None, None

# --- ВЫТЯГИВАНИЕ КАРТИНОК ИЗ СТРАНИЦЫ ---
async def get_solution_images(page_url: str) -> list[str]:
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        try:
            async with session.get(page_url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                if resp.status != 200:
                    return []
                html = await resp.text()
        except Exception as e:
            logging.error(f"Ошибка открытия {page_url}: {e}")
            return []

    soup = BeautifulSoup(html, "html.parser")
    found_urls = []

    # Фильтрация для reshak.ru
    if "reshak.ru" in page_url:
        for img in soup.find_all("img"):
            src = img.get("src") or img.get("data-src") or ""
            if any(key in src for key in ["reshebnik", "uploads", "tasks", "content"]):
                if not any(bad in src.lower() for bad in ["logo", "banner", "icon", "star", "advert"]):
                    full_url = f"https://reshak.ru/{src.lstrip('/')}" if not src.startswith("http") else src
                    found_urls.append(full_url)

    # Общая логика для остальных источников
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

# --- СКАЧИВАНИЕ КАРТИНКИ С REFERER (ОБХОД 403 FORBIDDEN) ---
async def download_image_bytes(img_url: str, referer: str) -> bytes | None:
    headers = HEADERS.copy()
    headers["Referer"] = referer
    async with aiohttp.ClientSession(headers=headers) as session:
        try:
            async with session.get(img_url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                if resp.status == 200:
                    return await resp.read()
        except Exception as e:
            logging.error(f"Не скачалась картинка {img_url}: {e}")
    return None

# --- ОБРАБОТЧИКИ СООБЩЕНИЙ ---
@dp.message(CommandStart())
async def cmd_start(message: Message):
    text = (
        "👋 **Бот для поиска ГДЗ**\n\n"
        "Напиши учебник и номер задания.\n\n"
        "📌 Примеры:\n"
        "• `10 класс алгебра Алимов 15`\n"
        "• `Геометрия Атанасян 10-11 класс 45`\n"
        "• `Spotlight 10 класс workbook 12`"
    )
    await message.answer(text, parse_mode="Markdown")

@dp.message(F.text)
async def handle_query(message: Message):
    query = message.text.strip()
    status_msg = await message.answer("🔍 Ищу страницу с решением...")

    page_url, title = await search_gdz_page(query)
    if not page_url:
        await status_msg.edit_text("❌ Не удалось найти страницу. Уточни запрос (например: `10 класс алгебра Алимов 15`).")
        return

    await status_msg.edit_text("📥 Страница найдена, достаю решение...")
    img_urls = await get_solution_images(page_url)

    sent = False
    if img_urls:
        for img_url in img_urls[:2]:
            img_bytes = await download_image_bytes(img_url, referer=page_url)
            if img_bytes:
                try:
                    file = BufferedInputFile(img_bytes, filename="solution.png")
                    await message.answer_photo(
                        photo=file,
                        caption=f"📘 **{title or query}**\n🔗 [Открыть оригинал]({page_url})",
                        parse_mode="Markdown"
                    )
                    sent = True
                except Exception as e:
                    logging.error(f"Ошибка отправки фото: {e}")

    # Если сайт заблокировал картинки (Cloudflare / JS-рендер на gdz.ru)
    if not sent:
        await status_msg.edit_text(
            f"✅ **Решение найдено!**\n\n"
            f"📌 {title or query}\n"
            f"⚠️ На странице стоит защита от парсинга картинок, решение доступно по ссылке:\n\n"
            f"👉 [Открыть решение на сайте]({page_url})",
            parse_mode="Markdown"
        )
    else:
        await status_msg.delete()

# --- ВЕБ-СЕРВЕР ДЛЯ РАЗВЕРТЫВАНИЯ (RENDER / KOYEB / И Т.Д.) ---
async def run_web_server():
    app = web.Application()
    app.router.add_get("/", lambda r: web.Response(text="OK"))
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    await asyncio.Event().wait()

async def main():
    logging.basicConfig(level=logging.INFO)
    asyncio.create_task(run_web_server())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

