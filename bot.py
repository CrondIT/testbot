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
    user_edit_pending,
    edited_photo_id,
    user_last_edited_images,
    user_edit_images_queue,
    
)

import dbbot
import models_config
import billing_utils
from handle_utils import handle_message_or_voice
from message_utils import send_long_message
from send_message_utils import send_telegram_message
from global_state import TELEGRAM_CHAT_ID


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
    """Обработчик команды /start -
    показывает приветственное сообщение с кнопкой"""
    # Создаем красивую кнопку "Старт"
    keyboard = [
        [
            InlineKeyboardButton(
                "🚀 Начать работу с ботом", callback_data="welcome_start"
            )
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    welcome_text = """
        🤖 Добро пожаловать в мульти-режимного бота!

        Этот бот поможет вам:
        • Общаться с ИИ
        • Анализировать файлы
        • Редактировать изображения
        • Управлять счетом

        Нажмите кнопку ниже, чтобы начать работу!
        """

    await update.message.reply_text(welcome_text, reply_markup=reply_markup)


async def welcome_start_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    """Обработчик нажатия на кнопку 'Старт' -
    регистрирует пользователя и показывает основное приветствие"""

    query = update.callback_query
    await query.answer()  # Подтверждаем нажатие

    user_id = query.from_user.id
    username = query.from_user.username or "Без имени"

    # Проверяем, существует ли пользователь до вызова get_user
    user_exists_before = dbbot.check_user(user_id)
    user = dbbot.get_user(user_id)
    coins = user["coins"] + user["giftcoins"]

    # Если пользователь новый, отправляем сообщение в служебный чат
    if not user_exists_before:
        try:
            username = query.from_user.username or "Без имени"
            # Отправляем сообщение в служебный чат
            if TELEGRAM_CHAT_ID and TELEGRAM_BOT_TOKEN:
                service_message = (
                    f"🤖 Новый пользователь зарегистрировался в боте!\n"
                    f"ID: {user_id}\n"
                    f"Username: @{username}\n"
                    f"Время: {(
                        query.message.date.strftime('%Y-%m-%d %H:%M:%S')
                        if query.message and query.message.date else 'N/A'
                        )}"
                )

                await send_telegram_message(
                    bot_token=TELEGRAM_BOT_TOKEN,
                    chat_id=TELEGRAM_CHAT_ID,
                    text=service_message,
                )
            else:
                # Логируем в базу данных, что не удалось отправить сообщение
                log_text = "Не удалось отправить сообщение в служебный чат"
                dbbot.log_action(
                    user_id,
                    "system",
                    log_text,
                    0,
                    0,
                    "warning",
                    "bot>welcome_start_handler",
                )
        except Exception as e:
            dbbot.log_action(
                user_id,
                "system",
                f"Ошибка при отправке сообщения в служебный чат: {e}",
                0,
                0,
                "error",
                "bot>welcome_start_handler",
            )

    user_modes[user_id] = "chat"  # Устанавливаем режим по умолчанию

    # Редактируем сообщение, заменяя кнопку на основное приветствие
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
    await query.edit_message_text(text=welcome_text)


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
    elif data == "welcome_start":
        await query.edit_message_text("Добро пожаловать в бот!")
    else:
        pass


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

    # Очищаем все данные, связанные с редактированием изображений
    if user_id in user_edit_data:
        del user_edit_data[user_id]
    if user_id in user_edit_pending:
        del user_edit_pending[user_id]
    if user_id in edited_photo_id:
        del edited_photo_id[user_id]
    if user_id in user_last_edited_images:
        # Удаляем файл предыдущего отредактированного изображения
        import os

        if os.path.exists(user_last_edited_images[user_id]):
            os.remove(user_last_edited_images[user_id])
        del user_last_edited_images[user_id]
    if user_id in user_edit_images_queue:
        # Удаляем файлы из очереди изображений
        import os
        for img_path in user_edit_images_queue[user_id]:
            if img_path is not None and os.path.exists(img_path):
                os.remove(img_path)
        del user_edit_images_queue[user_id]

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
    """Global error handler."""
    import traceback

    # error_text = f"Update {update} caused error {context.error}"

    # Determine user_id if possible for logging to database
    user_id = None
    if update and hasattr(update, "effective_user") and update.effective_user:
        user_id = update.effective_user.id
    elif (
        update
        and hasattr(update, "message")
        and update.message
        and hasattr(update.message, "from_user")
        and update.message.from_user
    ):
        user_id = update.message.from_user.id
    elif (
        update
        and hasattr(update, "callback_query")
        and update.callback_query
        and hasattr(update.callback_query.from_user)
        and update.callback_query.from_user
    ):
        user_id = update.callback_query.from_user.id

    # Use a default user_id if we can't determine it from the update
    if user_id is None:
        user_id = 0  # Using 0 as a default value for system-level errors

    # Log errors caused by updates
    if isinstance(context.error, NetworkError):
        network_error_text = f"Network error occurred: {context.error}"
        # Don't raise the error to prevent stopping the bot
        # Log the specific network error for debugging
        network_error_details = (
            f"Network error details: {traceback.format_exc()}"
        )

        # Log to database
        dbbot.log_action(
            user_id,
            "system",
            f"{network_error_text}\n{network_error_details}",
            0,
            0,
            "error",
            "bot>error_handler",
        )
        return
    elif isinstance(context.error, TimedOut):
        timeout_error_text = f"Timeout error occurred: {context.error}"
        # Don't raise the error to prevent stopping the bot

        # Log to database
        dbbot.log_action(
            user_id,
            "system",
            timeout_error_text,
            0,
            0,
            "error",
            "bot>error_handler",
        )
        return
    else:
        # Log other errors
        other_error_text = f"Non-network error occurred: {context.error}"
        error_traceback = traceback.format_exc()

        # Log to database
        dbbot.log_action(
            user_id,
            "system",
            f"{other_error_text}\n{error_traceback}",
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

    # Обработчик нажатия на кнопку "Старт"
    app.add_handler(
        CallbackQueryHandler(welcome_start_handler, pattern="welcome_start")
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
            timeout=20,
            bootstrap_retries=-1,
        )
    except KeyboardInterrupt:
        print("Bot stopped by user")
    except Exception as e:
        import traceback

        log_text = (
            f"An error occurred: {e}" f"Traceback: {traceback.format_exc()}"
        )
        dbbot.log_action(
            0,  # Используем 0 как значение по умолчанию для системных ошибок
            "system",
            log_text,
            0,
            0,
            "error",
            "main",
        )


if __name__ == "__main__":
    main()
