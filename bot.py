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
from telegram.helpers import escape_markdown

from PIL import Image
import io
import google.generativeai as genai
import dbbot
import token_utils
import file_utils
import coins_utils
import models_config

# File processing imports OCR imports in file_utils.py

# Загрузить переменные из файла .env
load_dotenv()
# Load only the TELEGRAM_BOT_TOKEN
# as it's specifically needed for running the bot
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_TOKEN2")

client_chat = models_config.client_chat
client_image = models_config.client_image

user_contexts = {}  # Хранилище контекста для каждого пользователя и режима
user_modes = {}  # Хранит текущий режим для каждого пользователя
user_edit_data = {}  # Хранит данные для редактирования изображений
user_file_data = {}  # Хранит данные для анализа файлов
MAX_CONTEXT_MESSAGES = 4

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
    await update.message.reply_text(safe_info, parse_mode="MarkdownV2")


async def models_openai(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обработчик команды /models_openai — показывает доступные модели OpenAI.
    """
    await update.message.reply_text("🔄 Запрашиваю список моделей у OpenAI...")
    info = await models_config.get_openai_models_info()
    safe_info = escape_markdown(info, version=2)
    await update.message.reply_text(safe_info, parse_mode="MarkdownV2")


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
        /file_analysis - Анализ файлов
        /ai_image - Генерация изображений
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
    dbbot.log_action(user_id, "billing", log_text, 0, balance)

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


async def ai_image_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Активация режима генерации изображений"""
    user_id = update.effective_user.id
    user_modes[user_id] = "image"
    # Очищаем данные редактирования при смене режима
    if user_id in user_edit_data:
        del user_edit_data[user_id]
    await update.message.reply_text(
        "🎨 Режим генерации изображений активирован. "
        "Опишите, что вы хотите увидеть!"
    )


async def ai_edit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Активация режима редактирования изображений с использованием Gemini"""
    user_id = update.effective_user.id
    user_modes[user_id] = "edit"
    # Инициализируем данные для редактирования
    user_edit_data[user_id] = {
        "step": "waiting_image",  # waiting_image, waiting_prompt
        "original_image": None,
    }
    help_text = """
        🎭 Режим редактирования изображений активирован!

        Как использовать:
        1. Отправьте изображение, которое хотите отредактировать
        2. Опишите, что нужно изменить

        Примеры запросов:
        - "Добавь солнце на небо"
        - "Измени цвет волос на рыжий"
        - "Убери человека с фона"
        - "Сделай стиль поп-арт"
        - "Добавь текст 'Hello World' в верхний левый угол"

        📝 Изображение будет автоматически
        конвертировано в PNG для лучшего качества.
    """
    await update.message.reply_text(help_text)


async def download_and_convert_image(
    file_id: str, context: ContextTypes.DEFAULT_TYPE
) -> io.BytesIO:
    """
    Скачивает изображение, конвертирует в PNG
    и возвращает его в виде BytesIO
    """
    file = await context.bot.get_file(file_id)
    image_data = io.BytesIO()
    await file.download_to_memory(out=image_data)
    image_data.seek(0)
    # Конвертируем изображение в PNG
    try:
        with Image.open(image_data) as img:
            # Конвертируем в RGB если нужно (для JPEG)
            if img.mode in ("P", "RGBA", "LA"):
                # Создаем белый фон для изображений с прозрачностью
                background = Image.new("RGB", img.size, (255, 255, 255))
                if img.mode == "P":
                    img = img.convert("RGBA")
                background.paste(
                    img, mask=img.split()[-1] if img.mode == "RGBA" else None
                )
                img = background
            elif img.mode != "RGB":
                img = img.convert("RGB")
            # Сохраняем как PNG
            png_data = io.BytesIO()
            img.save(png_data, format="PNG", optimize=True)
            png_data.seek(0)
            return png_data
    except Exception as e:
        print(f"Ошибка конвертации изображения: {e}")
        # Если не удалось конвертировать, возвращаем исходные данные
        image_data.seek(0)
        return image_data


async def generate_image(prompt: str) -> str:
    """Генерирует изображение с помощью DALL-E"""
    model_name = models_config.MODELS["image"]  # Используем константу
    # Проверяем длину промпта на токены (ограничение для DALL-E)
    prompt_tokens = token_utils.token_counter.count_openai_tokens(
        prompt, model_name
    )
    max_tokens = token_utils.get_token_limit(model_name)

    if prompt_tokens > max_tokens:
        # Обрезаем промпт до допустимого размера
        avg_token_size = 4  # средний размер токена в символах
        max_chars = max_tokens * avg_token_size
        prompt = prompt[:max_chars]

    try:
        response = client_image.images.generate(
            model=model_name,  # Используем константу
            prompt=prompt,
            size="1024x1024",
            quality="standard",
            n=1,
        )
        return response.data[0].url
    except Exception as e:
        raise Exception(f"Ошибка генерации изображения: {str(e)}")


async def edit_image_with_gemini(
    original_image: io.BytesIO, prompt: str
) -> str:
    """Редактирует изображение с помощью Gemini 2.5 Flash"""
    model_name = models_config.MODELS["edit"]  # Используем константу
    try:
        # Проверяем длину промпта на токены
        prompt_tokens = token_utils.token_counter.count_openai_tokens(
            prompt, model_name
        )
        max_tokens = token_utils.get_token_limit(model_name)

        if prompt_tokens > max_tokens:
            # Обрезаем промпт до допустимого размера
            avg_token_size = 4  # средний размер токена в символах
            max_chars = max_tokens * avg_token_size
            prompt = prompt[:max_chars]

        # Подготовка изображения для Gemini
        original_image.seek(0)
        # Создаем модель Gemini
        model = genai.GenerativeModel(model_name)
        # Подготавливаем промпт для Gemini
        gemini_prompt = f"""
        Проанализируй это изображение и выполни следующие изменения: {prompt}
        Важные инструкции:
        1. Внеси именно те изменения, которые запрошены пользователем
        2. Сохрани общий стиль и качество изображения
        3. Если запрос неясен, уточни у пользователя
        4. Верни только измененное изображение без дополнительного текста
        """
        # Отправляем изображение и промпт в Gemini
        response = model.generate_content(
            [
                gemini_prompt,
                {"mime_type": "image/png", "data": original_image.getvalue()},
            ]
        )
        # Проверяем, содержит ли ответ изображение
        if hasattr(response, "candidates") and response.candidates:
            for part in response.candidates[0].content.parts:
                if hasattr(part, "inline_data"):
                    # Возвращаем данные изображения
                    return part.inline_data.data
                elif hasattr(part, "text"):
                    # Если Gemini вернул текст вместо изображения
                    raise Exception(
                        f"""
                        ИИ вернул текстовый ответ вместо изображения:
                        {part.text}"""
                    )
        # Если не нашли изображение в ответе
        raise Exception("Gemini не вернул изображение в ответе")
    except Exception as e:
        raise Exception(
            f"Ошибка редактирования изображения с помощью ИИ: {str(e)}"
        )


async def save_image_from_data(image_data: bytes, filename: str) -> str:
    """Сохраняет изображение из бинарных данных и возвращает путь к файлу"""
    file_path = f"{filename}.png"
    with open(file_path, "wb") as f:
        f.write(image_data)
    return file_path


async def transcribe_voice(file_path: str) -> str:
    """Преобразует голосовое сообщение в текст с помощью Whisper API."""
    with open(file_path, "rb") as audio_file:
        transcription = client_chat.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
        )
    return transcription.text


def initialize_user_context(user_id: int, current_mode: str):
    """Инициализирует контекст для текущего режима пользователя"""
    if user_id not in user_contexts:
        user_contexts[user_id] = {}

    if current_mode not in user_contexts[user_id]:
        # Определяем системные сообщения для разных режимов
        if current_mode == "file_analysis":
            system_message = (
                "Ты помощник по анализу документов."
                "Отвечай на вопросы касательно "
                "содержимого предоставленного файла."
            )
        elif current_mode == "chat":
            # Для режима чата в file_analysis используется другое сообщение
            system_message = (
                "You are a helpful assistant. "
                "Use web search only when your knowledge may be outdated "
                "or when the user explicitly asks for fresh data."
            )
        elif current_mode == "image":
            system_message = "Ты помогаешь генерировать изображения."
        elif current_mode == "edit":
            system_message = (
                "Ты помогаешь редактировать изображения с помощью Gemini."
            )
        else:
            system_message = "Ты помощник."

        # Инициализируем контекст с системным сообщением
        user_contexts[user_id][current_mode] = [
            {"role": "system", "content": system_message}
        ]


async def handle_message_or_voice(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    user_id = update.effective_user.id
    # Если режим не установлен, устанавливаем режим чата по умолчанию
    if user_id not in user_modes:
        user_modes[user_id] = "chat"

    current_mode = user_modes[user_id]

    # Continue with standard processing using the augmented question
    # --- ✅ ПРОВЕРКА НАЛИЧИЯ МОНЕТ ---
    user_data, coins, giftcoins, balance, cost = (
        await coins_utils.check_user_coins(user_id, current_mode, context)
    )
    if user_data is None:
        return  # ❌ Прерываем выполнение, если монет не хватает
    # --- ✅ ПРОВЕРКА ЗАВЕРШЕНА ---

    # === ГАРАНТИРОВАННАЯ ИНИЦИАЛИЗАЦИЯ КОНТЕКСТА ДЛЯ ТЕКУЩЕГО РЕЖИМА
    initialize_user_context(user_id, current_mode)

    # Проверяем, является ли сообщение голосовым
    if update.message.voice:
        # Скачиваем голосовое сообщение
        voice_file = await context.bot.get_file(update.message.voice.file_id)
        # Сохраняем его во временный файл
        file_path = f"voice_{user_id}_{update.message.message_id}.ogg"
        await voice_file.download_to_drive(file_path)

        try:
            # Преобразуем в текст
            user_message = await transcribe_voice(file_path)
            # Удаляем временный файл
            os.remove(file_path)
        except Exception as e:
            # LOGGING ====================
            log_text = "Не удалось распознать голосовое сообщение."
            dbbot.log_action(user_id, current_mode, log_text, 0, balance)
            print("Ошибка транскрибации:", e)
            await update.message.reply_text(
                "⚠️ Не удалось распознать голосовое сообщение."
            )
            return
    elif update.message.text:
        # Обычное текстовое сообщение
        user_message = update.message.text.strip()
    else:
        return  # Не текст и не голос

    # Handle file uploads in file_analysis mode
    if current_mode == "file_analysis":
        # Check if the message contains a document
        if update.message.document:
            # Get the file
            file = await context.bot.get_file(update.message.document.file_id)

            # Determine file extension
            file_ext = file_utils.get_file_extension(
                update.message.document.file_name
            )
            if file_ext.lower() not in file_utils.SUPPORTED_EXTENSIONS:
                await update.message.reply_text(
                    f"❌Неверный формат."
                    f" Поддерживаются: "
                    f"{', '.join(file_utils.SUPPORTED_EXTENSIONS)}"
                )
                return

            # Download file
            file_path = (
                f"temp_file_{user_id}_{update.message.message_id}{file_ext}"
            )
            await file.download_to_drive(file_path)

            try:
                # Extract text from file
                await update.message.reply_text(
                    "📄 Извлекаю текст из файла..."
                )

                extracted_text = await file_utils.process_uploaded_file(
                    file_path, file_ext
                )

                # Store extracted text for later use
                if user_id not in user_file_data:
                    user_file_data[user_id] = {}
                user_file_data[user_id]["extracted_text"] = extracted_text

                # Confirm extraction
                await update.message.reply_text(
                    f"✅ Файл обработан! Извлечено {len(extracted_text)} симв. "
                    "Теперь можете задавать вопросы о содержимом файла."
                )

                # Clean up temporary file
                os.remove(file_path)
            except Exception as e:
                # Clean up temporary file even if there's an error
                if os.path.exists(file_path):
                    os.remove(file_path)

                await update.message.reply_text(
                    f"❌ Ошибка обработки файла: {str(e)}"
                )
                return
        # Check if the message contains a photo (for OCR of images)
        elif update.message.photo:
            # Get the highest resolution photo
            file = await context.bot.get_file(update.message.photo[-1].file_id)

            # Determine file extension - for photos sent as images,
            # assume it's an image file
            file_ext = ".jpg"  # Telegram converts photos to JPEG

            # Download file
            file_path = (
                f"temp_image_{user_id}_{update.message.message_id}{file_ext}"
            )
            await file.download_to_drive(file_path)

            try:
                # Extract text from image using OCR
                await update.message.reply_text(
                    "🔍 Выполняю OCR распознавание изображения..."
                )

                extracted_text = await file_utils.extract_text_from_image(
                    file_path
                )

                # Store extracted text for later use
                if user_id not in user_file_data:
                    user_file_data[user_id] = {}
                user_file_data[user_id]["extracted_text"] = extracted_text

                # Confirm extraction
                await update.message.reply_text(
                    f"✅ Файл обработан! Извлечено {len(extracted_text)} сим."
                    "Теперь можете задавать вопросы о содержимом изображения."
                )

                # Clean up temporary file
                os.remove(file_path)
            except Exception as e:
                # Clean up temporary file even if there's an error
                if os.path.exists(file_path):
                    os.remove(file_path)

                await update.message.reply_text(
                    f"❌ Ошибка обработки изображения: {str(e)}"
                )
                return
        elif (
            update.message.text
            and user_id in user_file_data
            and "extracted_text" in user_file_data[user_id]
        ):
            # Process the question about the file content
            user_message = update.message.text.strip()
            extracted_text = user_file_data[user_id]["extracted_text"]

            # Limit the extracted text length to prevent connection errors
            # Calculate max characters based on model's token limit
            model_name = models_config.MODELS.get(current_mode)
            max_tokens = token_utils.get_token_limit(model_name)

            # Rough estimation: 1 token ~ 4 characters,
            # reserve tokens for response and context
            # 1500 reserved for context
            max_chars = min(len(extracted_text), (max_tokens - 1500) * 3)

            if len(extracted_text) > max_chars:
                # Truncate the extracted text and inform the user
                truncated_extracted_text = extracted_text[:max_chars]
                await update.message.reply_text(
                    f"📝 Объем файла превышает лимит. Использую первую "
                    f"часть текста ({max_chars} сим.) для анализа."
                )
            else:
                truncated_extracted_text = extracted_text

            # Add file content to the user's question
            augmented_question = (
                f"Файл содержит следующий текст:"
                f" {truncated_extracted_text}\n\nВопрос: {user_message}"
            )

            # Prepare messages with truncated history
            # using the augmented question
            model_name = models_config.MODELS.get(current_mode)
            truncated_history = token_utils.truncate_messages_for_token_limit(
                user_contexts[user_id][current_mode],
                model=model_name,
                reserve_tokens=1500,
            )
            messages = truncated_history + [
                {"role": "user", "content": augmented_question}
            ]

            # Дополнительно ограничиваем длину истории
            if len(messages) > MAX_CONTEXT_MESSAGES:
                messages = messages[-MAX_CONTEXT_MESSAGES:]

            try:
                # Используем клиент чата
                # Проверяем, что последнее сообщение - это от пользователя
                if messages and messages[-1]["role"] == "user":
                    # Проверяем токены перед отправкой
                    token_counter = token_utils.token_counter
                    total_tokens = token_counter.count_openai_messages_tokens(
                        messages, model_name
                    )
                    max_tokens = token_utils.get_token_limit(model_name)

                    if total_tokens > max_tokens:
                        # Обрезаем сообщения до приемлемого размера
                        messages = (
                            token_utils.truncate_messages_for_token_limit(
                                messages,
                                model=model_name,
                                reserve_tokens=1500,
                            )
                        )

                response = client_chat.chat.completions.create(
                    model=model_name,  # Используем модель из константы
                    messages=messages,
                )
                reply = response.choices[0].message.content

                # Обновляем контекст: добавляем и запрос, и ответ
                user_contexts[user_id][current_mode].append(
                    {"role": "user", "content": augmented_question}
                )
                user_contexts[user_id][current_mode].append(
                    {"role": "assistant", "content": reply}
                )

                # Отправляем ответ
                # Экранируем специальные символы Markdown,
                # чтобы избежать ошибок
                safe_reply = escape_markdown(reply, version=2)
                await update.message.reply_text(
                    safe_reply, parse_mode="MarkdownV2"
                )

                # Списываем монеты и записываем лог
                coins_utils.spend_coins(
                    user_id,
                    cost,
                    coins,
                    giftcoins,
                    current_mode,
                    user_message,
                    safe_reply,
                )
            except Exception as e:
                # Обработка ошибки "Message is too long" и других
                error_msg = str(e)
                if (
                    "too long" in error_msg.lower()
                    or "token" in error_msg.lower()
                ):
                    # LOGGING ====================
                    log_text = f"Ошибка: Сообщение слишком длинное: {str(e)}"
                    dbbot.log_action(
                        user_id, current_mode, log_text, 0, balance
                    )
                    await update.message.reply_text(
                        "⚠️ Сообщение слишком длинное. Пожалуйста, сократите."
                    )
                else:
                    # LOGGING ====================
                    log_text = f"Ошибка при обращении к ChatGPT: {str(e)}"
                    dbbot.log_action(
                        user_id, current_mode, log_text, 0, balance
                    )
                    await update.message.reply_text(
                        "⚠️ Ошибка при обращении к ChatGPT."
                    )
        else:
            # If user hasn't uploaded a file yet but is in file analysis mode
            await update.message.reply_text(
                "📁 Пожалуйста, сначала загрузите файл для анализа. "
                "Поддерживаются форматы: PDF, DOCX, TXT, XLSX, XLS"
            )
        return  # End here for file analysis mode

    # --- ✅ ПРОВЕРКА НАЛИЧИЯ МОНЕТ ---
    user_data, coins, giftcoins, balance, cost = (
        await coins_utils.check_user_coins(user_id, current_mode, context)
    )
    if user_data is None:
        return  # ❌ Прерываем выполнение, если монет не хватает
    # --- ✅ ПРОВЕРКА ЗАВЕРШЕНА ---

    # Обработка режима редактирования изображений
    if current_mode == "edit":
        await handle_edit_mode(update, context, user_id)
        return

        # Инициализация контекста для текущего режима
    # === ГАРАНТИРОВАННАЯ ИНИЦИАЛИЗАЦИЯ КОНТЕКСТА ДЛЯ ТЕКУЩЕГО РЕЖИМА ===
    initialize_user_context(user_id, current_mode)

    # Обработка в зависимости от режима
    if current_mode == "image":
        # Режим генерации изображений
        await update.message.reply_text("🎨 Генерирую изображение...")
        try:
            image_url = await generate_image(user_message)
            await update.message.reply_photo(
                image_url, caption=f"Сгенерировано по запросу: {user_message}"
            )
            # Списываем монеты и записываем лог
            coins_utils.spend_coins(
                user_id, cost, coins, giftcoins, current_mode, user_message, ""
            )
        except Exception as e:
            # LOGGING ====================
            log_text = f"⚠️ {str(e)}"
            dbbot.log_action(user_id, current_mode, log_text, 0, balance)
            await update.message.reply_text(f"⚠️ {str(e)}")
        return

    # Для режима chat используем специальную функцию с возможностью веб-поиска
    if current_mode == "chat":
        try:
            # Используем функцию с веб-поиском для режима chat
            reply = models_config.ask_gpt51_with_web_search(
                user_message, enable_web_search=True
            )

            # Обновляем контекст: добавляем и запрос, и ответ
            user_contexts[user_id][current_mode].append(
                {"role": "user", "content": user_message}
            )
            user_contexts[user_id][current_mode].append(
                {"role": "assistant", "content": reply}
            )

            # Отправляем ответ
            # Экранируем специальные символы Markdown, чтобы избежать ошибок
            safe_reply = escape_markdown(reply, version=2)
            await update.message.reply_text(
                safe_reply, parse_mode="MarkdownV2"
            )

            # Списываем монеты и записываем лог
            coins_utils.spend_coins(
                user_id,
                cost,
                coins,
                giftcoins,
                current_mode,
                user_message,
                safe_reply,
            )
        except Exception as e:
            # LOGGING ====================
            log_text = f"Ошибка при обращении к ChatGPT: {str(e)}"
            dbbot.log_action(user_id, current_mode, log_text, 0, balance)
            await update.message.reply_text(
                "⚠️ Ошибка при обращении к ChatGPT."
            )
            return
    else:
        # Для других режимов (image, edit) используем обычную логику
        # Проверяем и ограничиваем количество токенов
        model_name = models_config.MODELS.get(current_mode)
        truncated_history = token_utils.truncate_messages_for_token_limit(
            user_contexts[user_id][current_mode],
            model=model_name,
            reserve_tokens=1500,
        )
        messages = truncated_history + [
            {"role": "user", "content": user_message}
        ]

        # Дополнительно ограничиваем длину истории
        if len(messages) > MAX_CONTEXT_MESSAGES:
            messages = messages[-MAX_CONTEXT_MESSAGES:]

        try:
            # Используем клиент чата
            # Проверяем, что последнее сообщение - это от пользователя
            if messages and messages[-1]["role"] == "user":
                # Проверяем токены перед отправкой
                token_counter = token_utils.token_counter
                total_tokens = token_counter.count_openai_messages_tokens(
                    messages, model_name
                )
                max_tokens = token_utils.get_token_limit(model_name)

                if total_tokens > max_tokens:
                    # Обрезаем сообщения до приемлемого размера
                    messages = token_utils.truncate_messages_for_token_limit(
                        messages,
                        model=model_name,
                        reserve_tokens=1500,  # Оставляем место для ответа
                    )

            response = client_chat.chat.completions.create(
                model=model_name,  # Используем модель из константы
                messages=messages,
            )
            reply = response.choices[0].message.content

            # Обновляем контекст: добавляем и запрос, и ответ
            user_contexts[user_id][current_mode].append(
                {"role": "assistant", "content": reply}
            )

            # Отправляем ответ
            # Экранируем специальные символы Markdown, чтобы избежать ошибок
            safe_reply = escape_markdown(reply, version=2)
            await update.message.reply_text(
                safe_reply, parse_mode="MarkdownV2"
            )

            # Списываем монеты и записываем лог
            coins_utils.spend_coins(
                user_id,
                cost,
                coins,
                giftcoins,
                current_mode,
                user_message,
                safe_reply,
            )
        except Exception as e:
            # Обработка ошибки "Message is too long" и других
            error_msg = str(e)
            if "too long" in error_msg.lower() or "token" in error_msg.lower():
                # LOGGING ====================
                log_text = f"Ошибка: Сообщение слишком длинное: {str(e)}"
                dbbot.log_action(user_id, current_mode, log_text, 0, balance)
                await update.message.reply_text(
                    "⚠️ Сообщение слишком длинное. Пожалуйста, сократите."
                )
            else:
                # LOGGING ====================
                log_text = f"Ошибка при обращении к ChatGPT: {str(e)}"
                dbbot.log_action(user_id, current_mode, log_text, 0, balance)
                await update.message.reply_text(
                    "⚠️ Ошибка при обращении к ChatGPT."
                )


async def handle_edit_mode(
    update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int
):
    """Обработчик для режима редактирования изображений с Gemini"""
    edit_data = user_edit_data.get(user_id, {})
    # Если пользователь отправил изображение
    if update.message.photo:
        await update.message.reply_text("🔄 Конвертирую изображение в PNG...")
        image_data = await download_and_convert_image(
            update.message.photo[-1].file_id, context
        )
        if edit_data.get("step") == "waiting_image":
            # Сохраняем исходное изображение
            user_edit_data[user_id]["original_image"] = image_data
            user_edit_data[user_id]["step"] = "waiting_prompt"
            await update.message.reply_text(
                "✅ Изображение получено и конвертировано в PNG. "
                "Теперь опишите, что нужно изменить в изображении "
                "(используется Gemini 2.5 Flash)."
            )
        return
    # Если пользователь отправил текст
    elif update.message.text:
        user_message = update.message.text.strip()
        if edit_data.get("step") == "waiting_prompt":
            await update.message.reply_text("🔄 Редактирую изображение...")
            try:
                original_image = user_edit_data[user_id]["original_image"]
                # Редактируем изображение с помощью Gemini
                edited_image_data = await edit_image_with_gemini(
                    original_image, user_message
                )
                # Сохраняем изображение во временный файл
                file_path = await save_image_from_data(
                    edited_image_data, f"edited_{user_id}"
                )
                # Отправляем отредактированное изображение
                with open(file_path, "rb") as photo:
                    await update.message.reply_photo(
                        photo,
                        caption=f"Отредактировано по запросу: {user_message}",
                    )
                # Удаляем временный файл
                os.remove(file_path)
                # Сбрасываем состояние редактирования
                user_edit_data[user_id] = {
                    "step": "waiting_image",
                    "original_image": None,
                }
            except Exception as e:
                await update.message.reply_text(f"⚠️ {str(e)}")
                # Сбрасываем состояние при ошибке
                user_edit_data[user_id] = {
                    "step": "waiting_image",
                    "original_image": None,
                }
            return
        # Если текст отправлен не на том шаге
        await update.message.reply_text(
            "❌ Сначала отправьте изображение для редактирования."
        )
        return
    # Если пользователь отправил что-то другое
    await update.message.reply_text(
        "❌ Пожалуйста, отправьте изображение или текст."
    )


async def clear_context(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Очистка контекста текущего режима"""
    user_id = update.effective_user.id
    if user_id in user_modes and user_id in user_contexts:
        current_mode = user_modes[user_id]
        if current_mode in user_contexts[user_id]:
            user_contexts[user_id][current_mode] = [
                {
                    "role": "system",
                    "content": "Контекст очищен. Начните новый разговор.",
                }
            ]
            await update.message.reply_text(
                "🧹 Контекст текущего режима очищен!"
            )
        else:
            await update.message.reply_text(
                "ℹ️ Нет активного контекста для очистки."
            )
    else:
        await update.message.reply_text("ℹ️ Сначала выберите режим работы.")


async def ai_file_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Activate file analysis mode"""
    user_id = update.effective_user.id
    user_modes[user_id] = "file_analysis"

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


async def precheckout_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle pre-checkout queries for Telegram Stars payments."""
    query = update.pre_checkout_query

    # Check if the product is valid (we only accept specific coin packages)
    valid_products = {
        "coins50stars": {"coins": 50, "stars": 50},
        "coins100stars": {"coins": 100, "stars": 100},
        "coins500stars": {"coins": 500, "stars": 500},
    }

    if query.invoice_payload in valid_products:
        await query.answer(ok=True)
    else:
        await query.answer(ok=False, error_message="Неверный продукт")


async def successful_payment_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle successful payments with Telegram Stars."""
    # Get the message with the successful payment
    successful_payment = update.message.successful_payment
    # Map invoice payloads to coin amounts
    product_map = {
        "coins50stars": {"coins": 50, "stars": 50},
        "coins100stars": {"coins": 100, "stars": 100},
        "coins500stars": {"coins": 500, "stars": 500},
    }
    # Get user ID from the payment
    user_id = update.effective_user.id
    user_data = dbbot.get_user(user_id)
    balance = user_data["coins"] + user_data["giftcoins"]
    current_mode = "billing"
    # Check if the invoice payload is valid
    if successful_payment.invoice_payload in product_map:
        product_info = product_map[successful_payment.invoice_payload]
        coins_to_add = product_info["coins"]
        stars_amount = product_info["stars"]

        # Add coins to user's account
        success = dbbot.change_all_coins(user_id, coins_to_add, 0)
        if success:
            # Get updated user info
            balance = user_data["coins"] + user_data["giftcoins"]
            # LOGGING ====================
            log_text = f""" Успешно приобретены монеты {coins_to_add}
                за звезды {stars_amount}
                Баланс монет: {balance}
                """
            dbbot.log_action(
                user_id, current_mode, log_text, coins_to_add, balance
            )
            # Send success message
            await update.message.reply_text(
                f"🎉 Вы приобрели {coins_to_add} монет за {stars_amount} ⭐️ "
                "Telegram Stars!\n"
                f"Ваш новый баланс: {balance} монет."
            )
        else:
            # LOGGING ====================
            log_text = f""" Ошибка при пополнении баланса
                {coins_to_add} монет за звезды {stars_amount}
                Баланс монет: {balance}
                """
            dbbot.log_action(user_id, current_mode, log_text, 0, balance)
            await update.message.reply_text(
                "❌ Произошла ошибка при пополнении баланса. "
                "Пожалуйста, свяжитесь с поддержкой."
            )
    else:
        # LOGGING ====================
        log_text = f""" Неизвестный продукт (при покупке монет за звезды)
            {coins_to_add} монет за звезды {stars_amount}
            Баланс монет: {balance}
            """
        dbbot.log_action(user_id, current_mode, log_text, 0, balance)
        await update.message.reply_text(
            "❌ Неизвестный продукт. "
            "Пожалуйста, используйте кнопки в меню /billing."
        )


def main():
    check_pid()  # Проверка на дубль
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    # Обработчики команд
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ai", ai_command))
    app.add_handler(CommandHandler("ai_image", ai_image_command))
    app.add_handler(CommandHandler("ai_edit", ai_edit_command))
    app.add_handler(CommandHandler("ai_file", ai_file_command))
    app.add_handler(CommandHandler("billing", billing))
    app.add_handler(CommandHandler("clear", clear_context))

    app.add_handler(CommandHandler("models_gemini", models_gemini))
    app.add_handler(CommandHandler("models_openai", models_openai))

    # Обрабатываем и текст, и голосовые сообщения
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND, handle_message_or_voice
        )
    )
    app.add_handler(MessageHandler(filters.VOICE, handle_message_or_voice))
    app.add_handler(MessageHandler(filters.PHOTO, handle_message_or_voice))
    app.add_handler(
        MessageHandler(filters.Document.ALL, handle_message_or_voice)
    )  # Add document handler

    # Обработчик нажатий на кнопки
    app.add_handler(CallbackQueryHandler(button_handler))

    # Обработчики для платежей через Telegram Stars
    app.add_handler(PreCheckoutQueryHandler(precheckout_callback))
    app.add_handler(
        TelegramMessageHandler(
            filters.SUCCESSFUL_PAYMENT, successful_payment_callback
        )
    )

    print("✅ Мульти-режимный бот запущен!")
    print(
        "Режимы: /ai (OpenAI), /ai_image (DALL-E),"
        " /ai_edit (Gemini), /ai_file (File Analysis)"
    )
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
