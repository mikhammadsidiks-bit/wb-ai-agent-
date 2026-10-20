import os
import asyncio
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

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
ADMIN_ID = os.environ.get("ADMIN_TELEGRAM_ID", "").strip()
WB_API_TOKEN = os.environ.get("WB_API_TOKEN", "").strip()

telegram_app = None


def is_admin(update: Update) -> bool:
    user = update.effective_user
    if user is None:
        return False
    return not ADMIN_ID or str(user.id) == ADMIN_ID


async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not is_admin(update):
        await update.effective_message.reply_text(
            "Доступ запрещён."
        )
        return

    await update.effective_message.reply_text(
        "Привет! Я WB AI Agent.\n\n"
        "Сейчас проверяем подключение к Wildberries.\n"
        "Пока я не изменяю товары, цены или остатки.\n\n"
        "/status — состояние сервиса\n"
        "/wb — проверить WB API\n"
        "/help — помощь"
    )


async def status(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not is_admin(update):
        await update.effective_message.reply_text(
            "Доступ запрещён."
        )
        return

    await update.effective_message.reply_text(
        "Состояние агента:\n"
        f"Telegram-токен задан: {'да' if TOKEN else 'нет'}\n"
        f"WB-токен задан в Render: "
        f"{'да' if WB_API_TOKEN else 'нет'}\n"
        "Проверка WB API: выполни /wb."
    )


async def wb_check():
    if not WB_API_TOKEN:
        return (
            False,
            "Не задан WB_API_TOKEN в Render Environment."
        )

    url = (
        "https://content-api.wildberries.ru/"
        "content/v2/get/cards/list"
    )
    headers = {"Authorization": WB_API_TOKEN}
    payload = {
        "settings": {
            "cursor": {"limit": 1},
            "filter": {"withPhoto": -1},
        }
    }

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                url,
                headers=headers,
                json=payload,
            )

        if response.status_code == 200:
            data = response.json()
            cards = data.get("cards", [])
            return (
                True,
                "Подключение к WB API работает.\n"
                f"Карточек получено: {len(cards)}.\n"
                "Данные не изменялись."
            )

        if response.status_code in (401, 403):
            return (
                False,
                f"WB API отказал в доступе: "
                f"HTTP {response.status_code}.\n"
                "Проверь токен и разрешение «Контент»."
            )

        logger.warning(
            "WB API вернул HTTP %s: %s",
            response.status_code,
            response.text[:500],
        )
        return (
            False,
            f"WB API вернул HTTP {response.status_code}. "
            "Данные не изменялись."
        )

    except httpx.TimeoutException:
        return False, "WB API не ответил вовремя. Попробуй позже."
    except httpx.HTTPError:
        logger.exception("Ошибка соединения с WB API")
        return False, "Ошибка соединения. Подробности в логах Render."
    except ValueError:
        logger.exception("Не удалось разобрать ответ WB API")
        return False, "WB API вернул некорректный ответ."


async def wb_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not is_admin(update):
        await update.effective_message.reply_text(
            "Доступ запрещён."
        )
        return

    await update.effective_message.reply_text(
        "Проверяю соединение с WB API..."
    )

    ok, message = await wb_check()await update.effective_message.reply_text(message)


async def help_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not is_admin(update):
        await update.effective_message.reply_text(
            "Доступ запрещён."
        )
        return

    await update.effective_message.reply_text(
        "Доступные команды:\n"
        "/start — начать работу\n"
        "/status — состояние сервиса\n"
        "/wb — проверить WB API\n"
        "/help — помощь"
    )


async def unknown_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not is_admin(update):
        await update.effective_message.reply_text(
            "Доступ запрещён."
        )
        return

    await update.effective_message.reply_text(
        "Пока доступны команды /status, /wb и /help. "
        "Подключение ИИ добавим следующим этапом."
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    global telegram_app

    if not TOKEN:
        logger.error(
            "Не задан TELEGRAM_BOT_TOKEN в Render Environment."
        )
        yield
        return

    telegram_app = Application.builder().token(TOKEN).build()

    telegram_app.add_handler(CommandHandler("start", start))
    telegram_app.add_handler(CommandHandler("status", status))
    telegram_app.add_handler(CommandHandler("wb", wb_command))
    telegram_app.add_handler(CommandHandler("help", help_command))
    telegram_app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            unknown_message,
        )
    )

    try:
        await telegram_app.initialize()
        await telegram_app.start()

        if telegram_app.updater is None:
            raise RuntimeError("Telegram updater недоступен")

        await telegram_app.updater.start_polling()
        logger.info("Telegram-бот запущен.")

        yield

    finally:
        if telegram_app is not None:
            if (
                telegram_app.updater is not None
                and telegram_app.updater.running
            ):
                await telegram_app.updater.stop()

            if telegram_app.running:
                await telegram_app.stop()

            await telegram_app.shutdown()

            telegram_app = None


app = FastAPI(lifespan=lifespan)


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
