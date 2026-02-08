import atexit
import os
from dotenv import load_dotenv

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    MessageHandler,
    ContextTypes,
    filters,
    CommandHandler,
    ApplicationBuilder,
    CallbackQueryHandler,
    PreCheckoutQueryHandler,
    MessageHandler as TelegramMessageHandler,
)
from telegram.error import NetworkError, TimedOut
from telegram.helpers import escape_markdown

from global_state import (
    user_contexts,
    user_modes,
    user_edit_data,
    user_file_data,
)

import dbbot
import models_config
import billing_utils
from handle_utils import handle_message_or_voice
from message_utils import send_long_message


# Загрузить переменные из файла .env
load_dotenv()
# Load only the TELEGRAM_BOT_TOKEN
# as it's specifically needed for running the bot
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_TOKEN2")

client_chat = models_config.client_chat
client_image = models_config.client_image

# --- Файл для хранения PID для котроля что процесс уже запущен- ---
PID_FILE = "bot.pid"


def check_pid():
    if os.path.exists(PID_FILE):
        with open(PID_FILE, "r") as f:
            try:
                pid = int(f.read().strip())
                # Проверяем, жив ли процесс
                os.kill(pid, 0)
                print(f"❌ Бот уже запущен (PID: {pid}). Завершаем.")
                exit(1)
            except (OSError, ValueError):
                # Процесс не существует — можно запускаться
                pass
    # Записываем текущий PID
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))

    # Удаляем файл при выходе
    atexit.register(lambda: os.path.exists(PID_FILE) and os.remove(PID_FILE))


# --- окончание проверки PID  для котроля что процесс уже запущен---


async def models_gemini(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обработчик команды /models_gemini — показывает доступные модели Gemini.
    """
    await update.message.reply_text(
        "🔄 Запрашиваю список моделей у Gemini...", parse_mode="Markdown"
    )
    info = await models_config.get_gemini_models_info()
    safe_info = escape_markdown(info, version=2)
    await send_long_message(update, safe_info, parse_mode="MarkdownV2")


async def models_openai(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обработчик команды /models_openai — показывает доступные модели OpenAI.
    """
    await update.message.reply_text("🔄 Запрашиваю список моделей у OpenAI...")
    info = await models_config.get_openai_models_info()
    safe_info = escape_markdown(info, version=2)
    await send_long_message(update, safe_info, parse_mode="MarkdownV2")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user_id = update.effective_user.id
    user = dbbot.get_user(user_id)
    coins = user["coins"] + user["giftcoins"]

    user_modes[user_id] = "chat"  # Устанавливаем режим по умолчанию
    welcome_text = f"""
        🤖 Добро пожаловать в мульти-режимного бота!
        Ваш ID: {user_id}, у Вас {coins} монета

        Доступные команды:
        /ai - Чат с ИИ
        /ai_file - Анализ файлов
        /ai_edit - Редактирование изображений
        /billing - Управление счетом

        Выберите режим и начните общение!
        """
    await update.message.reply_text(welcome_text)


async def billing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /billing"""
    user_id = update.effective_user.id
    user = dbbot.get_user(user_id)
    balance = user["coins"] + user["giftcoins"]

    # Создаём кнопки
    keyboard = [
        [
            InlineKeyboardButton(
                " 50 монет -  50 ⭐️", callback_data="coins50stars"
            ),
            InlineKeyboardButton(
                "100 монет - 100 ⭐️", callback_data="coins100stars"
            ),
            InlineKeyboardButton(
                "500 монет - 500 ⭐️", callback_data="coins500stars"
            ),
        ],
        [
            InlineKeyboardButton(
                " 50 монет -  50 руб.", callback_data="coins50rub"
            ),
            InlineKeyboardButton(
                "100 монет - 100 руб.", callback_data="coins100rub"
            ),
            InlineKeyboardButton(
                "500 монет - 500 руб.", callback_data="coins500rub"
            ),
        ],
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)
    # LOGGING ====================
    log_text = "Пользователь выбрал режим billing"
    dbbot.log_action(
        user_id, "billing", log_text, 0, balance, "success", "bot>billing"
    )

    welcome_text = f"""
        Ваш ID: {user_id}. Ваш баланс: {balance} монет

        Чтобы приобрести монеты выберите нужный вариант ниже:
        """
    await update.message.reply_text(
        welcome_text, reply_markup=reply_markup, parse_mode="Markdown"
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()  # Подтверждаем нажатие

    data = query.data

    if data == "coins50stars":
        # Send invoice for 50 coins via Telegram Stars
        await context.bot.send_invoice(
            chat_id=query.message.chat_id,
            title="Покупка монет",
            description="50 монет за 50 ⭐️ Telegram Stars",
            payload="coins50stars",
            provider_token="",  # Empty for Telegram Stars
            currency="XTR",  # Telegram Stars currency
            prices=[{"label": "Монеты", "amount": 50}],  # 50 stars
            max_tip_amount=0,
            suggested_tip_amounts=[],
            start_parameter="buy_coins",
        )
    elif data == "coins100stars":
        # Send invoice for 100 coins via Telegram Stars
        await context.bot.send_invoice(
            chat_id=query.message.chat_id,
            title="Покупка монет",
            description="100 монет за 100 ⭐️ Telegram Stars",
            payload="coins100stars",
            provider_token="",  # Empty for Telegram Stars
            currency="XTR",  # Telegram Stars currency
            prices=[{"label": "Монеты", "amount": 100}],  # 100 stars
            max_tip_amount=0,
            suggested_tip_amounts=[],
            start_parameter="buy_coins",
        )
    elif data == "coins500stars":
        # Send invoice for 500 coins via Telegram Stars
        await context.bot.send_invoice(
            chat_id=query.message.chat_id,
            title="Покупка монет",
            description="500 монет за 500 ⭐️ Telegram Stars",
            payload="coins500stars",
            provider_token="",  # Empty for Telegram Stars
            currency="XTR",  # Telegram Stars currency
            prices=[{"label": "Монеты", "amount": 500}],  # 500 stars
            max_tip_amount=0,
            suggested_tip_amounts=[],
            start_parameter="buy_coins",
        )
    elif data == "coins50rub":
        await query.edit_message_text("Раздел в работе!")
    elif data == "coins100rub":
        await query.edit_message_text("Раздел в работе!")
    elif data == "coins500rub":
        await query.edit_message_text("Раздел в работе!")
    else:
        await query.edit_message_text(
            "📋 История операций:\n- Пополнение: +10 \n- Использовано: -5 "
        )


async def ai_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Активация режима обычного чата"""
    user_id = update.effective_user.id
    user_modes[user_id] = "chat"
    # Очищаем данные редактирования при смене режима
    if user_id in user_edit_data:
        del user_edit_data[user_id]
    await update.message.reply_text(
        "🔮 Режим чата (OpenAI) активирован. Задавайте вопросы!"
    )


async def ai_file_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Activate file analysis mode"""
    user_id = update.effective_user.id
    user_modes[user_id] = "ai_file"

    # Clear file data for this user
    if user_id in user_file_data:
        del user_file_data[user_id]

    help_text = """
📄 Режим анализа файлов активирован!

Как использовать:
1. Отправьте файл в одном из поддерживаемых форматов:
   • PDF - документы в формате PDF
   • DOC, DOCX - документы Word
   • TXT - текстовые файлы
   • XLS, XLSX - таблицы Excel
   • PPT, PPTX - презентации Power Point
   • ODF, ODS, ODP текст, таблицы и презентации OpenDocument

2. Бот извлечет текст из файла и позволит вам задавать вопросы

Примеры запросов после загрузки файла:
• "Резюмируй этот документ"
• "Найди все ключевые моменты"
• "Переведи на английский"
• "Найди информацию о контракте"
"""
    await update.message.reply_text(help_text)


async def ai_edit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Активация режима генерации и редактирования изображений
    с использованием Gemini
    """
    user_id = update.effective_user.id
    user_modes[user_id] = "edit"
    # Инициализируем данные для редактирования
    user_edit_data[user_id] = {
        "step": "waiting_image",  # waiting_image, waiting_prompt
        "original_image": None,
    }
    help_text = """
        🎭 Режим генерации и редактирования изображений активирован!

        Как использовать:
        1. Опишите какое изображение хотите создать
        ИЛИ
        1. Отправьте изображение, которое хотите отредактировать
        2. Опишите, что нужно изменить

        Примеры запросов:
        - "Нарисуй кота в стиле стимпанк на фоне горы"
        - "Измени цвет волос на рыжий"
        - "Убери человека с фона"
        - "Сделай стиль поп-арт"
        - "Добавь текст 'Hello World' в верхний левый угол"
    """
    await update.message.reply_text(help_text)


async def clear_context(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Очистка контекста текущего режима или всех режимов"""
    user_id = update.effective_user.id

    # Проверяем, есть ли аргументы в команде
    args = context.args if context.args else []

    if user_id in user_modes and user_id in user_contexts:
        if "all" in args or "--all" in args:
            # Очищаем контексты для всех режимов
            if user_id in user_contexts:
                # Сохраняем текущий режим для правильного системного сообщения
                current_mode = (
                    user_modes[user_id] if user_id in user_modes else None
                )

                # Очищаем все контексты для всех режимов
                for mode in user_contexts[user_id].keys():
                    user_contexts[user_id][mode] = [
                        {
                            "role": "system",
                            "content": "Контекст очищен.",
                        }
                    ]

                await update.message.reply_text(
                    "🧹 Контекст всех режимов очищен!"
                )
            else:
                await update.message.reply_text(
                    "ℹ️ Нет активных контекстов для очистки."
                )
        else:
            # Очищаем контекст только текущего режима (поведение по умолчанию)
            current_mode = (
                user_modes[user_id] if user_id in user_modes else None
            )
            if current_mode and current_mode in user_contexts[user_id]:
                user_contexts[user_id][current_mode] = [
                    {
                        "role": "system",
                        "content": "Контекст очищен. Начните новый разговор.",
                    }
                ]
                await update.message.reply_text(
                    f"🧹 Контекст текущего режима '{current_mode}' очищен!"
                )
            else:
                await update.message.reply_text(
                    "ℹ️ Нет активного контекста для очистки."
                )
    else:
        # Даже если режим не установлен,
        # пробуем очистить хотя бы какой-то контекст
        if user_id in user_contexts:
            # Очищаем все известные режимы, если они существуют
            cleared_any = False
            for mode in list(user_contexts[user_id].keys()):
                user_contexts[user_id][mode] = [
                    {
                        "role": "system",
                        "content": "Контекст очищен. Начните новый разговор.",
                    }
                ]
                cleared_any = True

            if cleared_any:
                await update.message.reply_text(
                    "🧹 Контекст очищен (режим не определен, очищено все)!"
                )
            else:
                await update.message.reply_text(
                    "ℹ️ Нет активных контекстов для очистки."
                )
        else:
            await update.message.reply_text("ℹ️ Сначала выберите режим.")


async def error_handler(
    update: object, context: ContextTypes.DEFAULT_TYPE
) -> None:
    user_id = update.effective_user.id
    """Global error handler."""
    # Log the error before we do anything else
    print(f"Update {update} caused error {context.error}")

    # Log errors caused by updates
    if isinstance(context.error, NetworkError):
        print(f"Network error occurred: {context.error}")
        # Don't raise the error to prevent stopping the bot
        # Log the specific network error for debugging
        import traceback
        print(f"Network error details: {traceback.format_exc()}")
        log_text = (
            f"Network error occurred: {context.error}"
            f"Network error details: {traceback.format_exc()}"
            )
        dbbot.log_action(
                    user_id,
                    "bot",
                    log_text,
                    0,
                    0,
                    "error",
                    "bot>error_handler",
                )
        return
    elif isinstance(context.error, TimedOut):
        log_text = f"Timeout error occurred: {context.error}"
        print(log_text)
        # Don't raise the error to prevent stopping the bot
        dbbot.log_action(
                    user_id,
                    "bot",
                    log_text,
                    0,
                    0,
                    "error",
                    "bot>error_handler",
                )
        return
    else:
        # Log other errors
        import traceback

        print(f"Non-network error occurred: {context.error}")
        print(traceback.format_exc())
        log_text = (
            f"Non-network error occurred: {context.error}"
            f"Traceback: {traceback.format_exc()}"
            )
        dbbot.log_action(
                    user_id,
                    "bot",
                    log_text,
                    0,
                    0,
                    "error",
                    "bot>error_handler",
                )


def main():
    check_pid()  # Проверка на дубль
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    # Add error handler
    app.add_error_handler(error_handler)

    # Обработчики команд
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ai", ai_command))
    app.add_handler(CommandHandler("ai_edit", ai_edit_command))
    app.add_handler(CommandHandler("ai_file", ai_file_command))
    app.add_handler(CommandHandler("billing", billing))
    app.add_handler(CommandHandler("clear", clear_context))
    app.add_handler(CommandHandler("models_gemini", models_gemini))
    app.add_handler(CommandHandler("models_openai", models_openai))
    # Обрабатываем  текст, голосовые сообщения, изображения и документы
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message_or_voice,
        )
    )
    app.add_handler(
        MessageHandler(
            filters.VOICE,
            handle_message_or_voice,
        )
    )
    app.add_handler(
        MessageHandler(
            filters.PHOTO,
            handle_message_or_voice,
        )
    )
    app.add_handler(
        MessageHandler(
            filters.Document.ALL,
            handle_message_or_voice,
        )
    )

    # Обработчик нажатий на кнопки
    app.add_handler(CallbackQueryHandler(button_handler))
    # Обработчики для платежей через Telegram Stars
    app.add_handler(
        PreCheckoutQueryHandler(billing_utils.precheckout_callback)
    )
    app.add_handler(
        TelegramMessageHandler(
            filters.SUCCESSFUL_PAYMENT,
            billing_utils.successful_payment_callback,
        )
    )

    print("Multi-mode bot started!")
    print(
        "Modes: /ai (OpenAI) " " /ai_edit (Gemini), /ai_file (File Analysis)"
    )

    # Run the bot with error handling for network issues
    try:
        app.run_polling(
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES,
            poll_interval=1.0,
            timeout=20,
            read_timeout=10,
            connect_timeout=10,
            pool_timeout=30,
            bootstrap_retries=-1,
            network_delay=1.0,
        )
    except KeyboardInterrupt:
        print("Bot stopped by user")
    except Exception as e:
        print(f"An error occurred: {e}")
        import traceback
        log_text = (
            f"An error occurred: {e}"
            f"Traceback: {traceback.format_exc()}"
            )
        dbbot.log_action(
                    None,
                    "bot",
                    log_text,
                    0,
                    0,
                    "error",
                    "bot>error_handler",
                )


if __name__ == "__main__":
    main()
