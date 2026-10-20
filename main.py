import os
import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
ADMIN_ID = os.environ.get("ADMIN_TELEGRAM_ID", "")
WB_API_TOKEN = os.environ.get("WB_API_TOKEN", "")

telegram_app = None


def is_admin(update: Update) -> bool:
    user = update.effective_user
    return bool(user and (not ADMIN_ID or str(user.id) == ADMIN_ID))


async def wb_check():
    if not WB_API_TOKEN:
        return False, "Не задан WB_API_TOKEN в Render."

    url = "https://content-api.wildberries.ru/content/v2/get/cards/list"
    headers = {"Authorization": WB_API_TOKEN}
    payload = {
        "settings": {
            "cursor": {"limit": 1},
            "filter": {"withPhoto": -1}
        }
    }

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                url, headers=headers, json=payload
            )

        if response.status_code == 200:
            data = response.json()
            cards = data.get("cards", [])
            return True, (
                "Подключение к WB API работает.\n"
                f"Карточек получено в тестовом запросе: {len(cards)}.\n"
                "Данные не изменялись."
            )

        if response.status_code in (401, 403):
            return False, (
                f"WB API отказал в доступе: HTTP {response.status_code}.\n"
                "Проверь токен и разрешение «Контент»."
            )

        return False, (
            f"WB API вернул HTTP {response.status_code}.\n"
            "Данные не изменялись. Проверь настройки и повтори позже."
        )

    except httpx.TimeoutException:
        return False, "WB API не ответил вовремя. Попробуй позже."
    except httpx.HTTPError:
        logger.exception("Ошибка соединения с WB API")
        return False, "Не удалось соединиться с WB API. Подробности в логах."


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.effective_message.reply_text("Доступ запрещён.")
        return

    await update.effective_message.reply_text(
        "Привет! Я WB AI Agent.\n\n"
        "Пока подключаем реальные данные и проверяем API.\n"
        "/status — состояние сервиса\n"
        "/wb — проверить WB API\n"
        "/help — помощь"
    )


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.effective_message.reply_text("Доступ запрещён.")
        return

    await update.effective_message.reply_text(
        "Состояние агента:\n"
        f"Telegram настроен: {'да' if TOKEN else 'нет'}\n"
        f"WB токен задан в Render: {'да' if WB_API_TOKEN else 'нет'}\n"
        "Для проверки API выполни /wb."
    )


async def wb_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.effective_message.reply_text("Доступ запрещён.")
        return

    await update.effective_message.reply_text(
        "Проверяю соединение с WB API..."
    )
    ok, message = await wb_check()
    await update.effective_message.reply_text(message)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(
        "Команды:\n"
        "/start — начать работу\n"
        "/status — состояние агента\n"
        "/wb — проверить WB API\n"
        "/help — помощь"
    )


async def unknown_message(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    if not is_admin(update):
        await update.effective_message.reply_text("Доступ запрещён.")
        return

    await update.effective_message.reply_text(
        "Пока доступны команды /status, /wb и /help. "
00:34
"ИИ и выполнение операций добавим следующим этапом."
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    global telegram_app

    if not TOKEN:
        logger.warning("TELEGRAM_BOT_TOKEN не задан.")
        yield
        return

    telegram_app = Application.builder().token(TOKEN).build()
    telegram_app.add_handler(CommandHandler("start", start))
    telegram_app.add_handler(CommandHandler("status", status))
    telegram_app.add_handler(CommandHandler("wb", wb_command))
    telegram_app.add_handler(CommandHandler("help", help_command))
    telegram_app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, unknown_message)
    )

    await telegram_app.initialize()
    await telegram_app.start()

    if telegram_app.updater is None:
        raise RuntimeError("Telegram updater недоступен.")

    await telegram_app.updater.start_polling(drop_pending_updates=False)
    logger.info("Telegram-бот запущен.")

    try:
        yield
    finally:
        if telegram_app.updater and telegram_app.updater.running:
            await telegram_app.updater.stop()
        await telegram_app.stop()
        await telegram_app.shutdown()


app = FastAPI(title="WB AI Agent", lifespan=lifespan)


@app.get("/")
async def home():
    return {
        "service": "WB AI Agent",
        "status": "running",
        "telegram_configured": bool(TOKEN),
        "wb_token_configured": bool(WB_API_TOKEN),
        "ai_connected": False,
    }


@app.get("/health")
async def health():
    return {"status": "ok"}
