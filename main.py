import os
import asyncio
import logging
from contextlib import asynccontextmanager

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

telegram_app = None


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if ADMIN_ID and str(user.id) != ADMIN_ID:
        await update.message.reply_text("Доступ запрещён.")
        return

    await update.message.reply_text(
        "Привет! Я будущий ИИ-агент WB Partners.\n\n"
        "Сейчас подключён базовый режим.\n"
        "Я пока не изменяю товары и не выполняю операции WB.\n\n"
        "Команды:\n"
        "/status — состояние агента\n"
        "/help — список команд"
    )


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if ADMIN_ID and str(update.effective_user.id) != ADMIN_ID:
        await update.message.reply_text("Доступ запрещён.")
        return

    await update.message.reply_text(
        "Базовый сервер запущен.\n"
        "Подключение к API WB ещё не настроено."
    )


async def help_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    await update.message.reply_text(
        "Доступные команды:\n"
        "/start — начать работу\n"
        "/status — проверить состояние\n"
        "/help — помощь"
    )


async def unknown_message(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    if ADMIN_ID and str(update.effective_user.id) != ADMIN_ID:
        await update.message.reply_text("Доступ запрещён.")
        return

    await update.message.reply_text(
        "Я пока работаю в тестовом режиме и ещё не подключён к ИИ.\n"
        "Сначала проверим сервер, затем добавим ИИ и WB API."
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    global telegram_app

    if not TOKEN:
        logger.warning("TELEGRAM_BOT_TOKEN не задан.")
        yield
        return

    telegram_app = (
        Application.builder()
        .token(TOKEN)
        .build()
    )

    telegram_app.add_handler(CommandHandler("start", start))
    telegram_app.add_handler(CommandHandler("status", status))
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
        "wb_api_connected": False,
        "ai_connected": False,
    }


@app.get("/health")
async def health():
    return {"status": "ok"}
