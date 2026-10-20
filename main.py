import os
import logging
import httpx
from contextlib import asynccontextmanager
from fastapi import FastAPI
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

logging.basicConfig(level=logging.INFO)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
ADMIN = os.getenv("ADMIN_TELEGRAM_ID", "")
WB_TOKEN = os.getenv("WB_API_TOKEN", "")


def allowed(update):
    user = update.effective_user
    return user and (not ADMIN or str(user.id) == ADMIN)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update):
        return await update.effective_message.reply_text("Доступ запрещён.")
    await update.effective_message.reply_text(
        "WB AI Agent запущен.\n/status — состояние\n/wb — проверка WB\n/help — помощь"
    )


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update):
        return await update.effective_message.reply_text("Доступ запрещён.")
    await update.effective_message.reply_text(
        f"Telegram: {'OK' if TOKEN else 'нет токена'}\n"
        f"WB-токен: {'задан' if WB_TOKEN else 'не задан'}"
    )


async def wb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update):
        return await update.effective_message.reply_text("Доступ запрещён.")
    msg = await update.effective_message.reply_text("Проверяю WB API...")
    if not WB_TOKEN:
        return await msg.edit_text("В Render не задан WB_API_TOKEN.")
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(
                "https://content-api.wildberries.ru/content/v2/get/cards/list",
                headers={"Authorization": WB_TOKEN},
                json={"settings": {"cursor": {"limit": 1},
                                   "filter": {"withPhoto": -1}}},
            )
        if r.status_code == 200:
            await msg.edit_text("WB API подключён. Данные не изменялись.")
        else:
            await msg.edit_text(f"WB API ответил: HTTP {r.status_code}.")
    except Exception:
        logging.exception("Ошибка WB API")
        await msg.edit_text("Ошибка соединения. Проверь логи Render.")


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update):
        return await update.effective_message.reply_text("Доступ запрещён.")
    await update.effective_message.reply_text("/start /status /wb /help")


@asynccontextmanager
async def lifespan(app: FastAPI):
    bot = Application.builder().token(TOKEN).build()
    for command, handler in [
        ("start", start), ("status", status), ("wb", wb), ("help", help_cmd)
    ]:
        bot.add_handler(CommandHandler(command, handler))
    await bot.initialize()
    await bot.start()
    await bot.updater.start_polling()
    try:
        yield
    finally:
        await bot.updater.stop()
        await bot.stop()
        await bot.shutdown()


app = FastAPI(lifespan=lifespan)


@app.get("/")
async def home():
    return {"status": "running", "service": "WB AI Agent"}


@app.get("/health")
async def health():
    return {"status": "ok"} 
