"""Utility functions for handling user interactions,
messages, and edit modes."""

import os
import io
from PIL import Image
import google.generativeai as genai
import dbbot
import token_utils
import file_utils
import billing_utils
import models_config
from telegram import Update
from telegram.ext import ContextTypes
from telegram.helpers import escape_markdown


# Global variables that need to be accessible
user_contexts = {}  # Хранилище контекста для каждого пользователя и режима
user_modes = {}  # Хранит текущий режим для каждого пользователя
user_edit_data = {}  # Хранит данные для редактирования изображений
user_file_data = {}  # Хранит данные для анализа файлов
MAX_CONTEXT_MESSAGES = 4


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


async def save_image_from_data(image_data: bytes, filename: str) -> str:
    """Сохраняет изображение из бинарных данных и возвращает путь к файлу"""
    file_path = f"{filename}.png"
    with open(file_path, "wb") as f:
        f.write(image_data)
    return file_path


def initialize_user_context(user_id: int, current_mode: str):
    """Инициализирует контекст для текущего режима пользователя"""
    if user_id not in user_contexts:
        user_contexts[user_id] = {}

    if current_mode not in user_contexts[user_id]:
        # Определяем системные сообщения для разных режимов
        if current_mode == "ai_file":
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


async def handle_edit_mode(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    user_message: str,
    cost: int,
    balance: float,
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

                # Списываем монеты и записываем лог
                from billing_utils import check_user_coins, spend_coins

                user_data, coins, giftcoins, balance, cost = (
                    await check_user_coins(user_id, "edit", context)
                )
                spend_coins(
                    user_id,
                    cost,
                    coins,
                    giftcoins,
                    "edit",
                    user_message,
                    f"Image edited with prompt: {user_message}",
                )
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


async def handle_ai_file_mode(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    user_message: str,
    cost: int,
    balance: float,
):
    """Handle the ai_file mode functionality separately"""
    from billing_utils import spend_coins

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
            await update.message.reply_text("📄 Извлекаю текст из файла...")

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
        model_name = models_config.MODELS.get("ai_file")
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
        model_name = models_config.MODELS.get("ai_file")
        truncated_history = token_utils.truncate_messages_for_token_limit(
            user_contexts[user_id]["ai_file"],
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
                    # Обрезаем сообщения до ... [truncated]
                    messages = token_utils.truncate_messages_for_token_limit(
                        messages,
                        model=model_name,
                        reserve_tokens=1500,
                    )

            response = models_config.client_chat.chat.completions.create(
                model=model_name,  # Используем модель из константы
                messages=messages,
            )
            reply = response.choices[0].message.content

            # Обновляем контекст: добавляем и запрос, и ответ
            user_contexts[user_id]["ai_file"].append(
                {"role": "user", "content": augmented_question}
            )
            user_contexts[user_id]["ai_file"].append(
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
            from billing_utils import check_user_coins

            user_data, coins, giftcoins, balance, cost = (
                await check_user_coins(user_id, "ai_file", context)
            )
            spend_coins(
                user_id,
                cost,
                coins,
                giftcoins,
                "ai_file",
                user_message,
                safe_reply,
            )
        except Exception as e:
            # Обработка ошибки "Message is too long" и других
            error_msg = str(e)
            if "too long" in error_msg.lower() or "token" in error_msg.lower():
                # LOGGING ====================
                log_text = f"Ошибка: Сообщение слишком длинное: {str(e)}"
                dbbot.log_action(user_id, "ai_file", log_text, 0, balance)
                await update.message.reply_text(
                    "⚠️ Сообщение слишком длинное. Пожалуйста, сократите."
                )
            else:
                # LOGGING ====================
                log_text = f"Ошибка при обращении к ChatGPT: {str(e)}"
                dbbot.log_action(user_id, "ai_file", log_text, 0, balance)
                await update.message.reply_text(
                    "⚠️ Ошибка при обращении к ChatGPT."
                )
    else:
        # If user hasn't uploaded a file yet but is in file analysis mode
        await update.message.reply_text(
            "📁 Пожалуйста, сначала загрузите файл для анализа. "
            "Поддерживаются форматы: PDF, DOCX, TXT, XLSX, XLS"
        )


async def handle_image_mode(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    user_message: str,
    cost: int,
    coins: int,
    giftcoins: int,
    balance: float,
):
    """Handle the image mode functionality separately"""
    from billing_utils import spend_coins

    # Режим генерации изображений
    await update.message.reply_text("🎨 Генерирую изображение...")
    try:
        image_url = await models_config.generate_image(user_message)
        await update.message.reply_photo(
            image_url, caption=f"Сгенерировано по запросу: {user_message}"
        )
        # Списываем монеты и записываем лог
        spend_coins(user_id, cost, coins, giftcoins, "image", user_message, "")
    except Exception as e:
        # LOGGING ====================
        log_text = f"⚠️ {str(e)}"
        dbbot.log_action(user_id, "image", log_text, 0, balance)
        await update.message.reply_text(f"⚠️ {str(e)}")


async def handle_chat_mode(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    user_message: str,
    cost: int,
    coins: int,
    giftcoins: int,
    balance: float,
):
    """Handle the chat mode functionality separately"""
    from billing_utils import spend_coins

    try:
        # Используем функцию с веб-поиском для режима chat
        reply = models_config.ask_gpt51_with_web_search(
            user_message, enable_web_search=True
        )

        # Обновляем контекст: добавляем и запрос, и ответ
        user_contexts[user_id]["chat"].append(
            {"role": "user", "content": user_message}
        )
        user_contexts[user_id]["chat"].append(
            {"role": "assistant", "content": reply}
        )

        # Отправляем ответ
        # Экранируем специальные символы Markdown, чтобы избежать ошибок
        safe_reply = escape_markdown(reply, version=2)
        await update.message.reply_text(safe_reply, parse_mode="MarkdownV2")

        # Списываем монеты и записываем лог
        spend_coins(
            user_id,
            cost,
            coins,
            giftcoins,
            "chat",
            user_message,
            safe_reply,
        )
    except Exception as e:
        # LOGGING ====================
        log_text = f"Ошибка при обращении к ChatGPT: {str(e)}"
        dbbot.log_action(user_id, "chat", log_text, 0, balance)
        await update.message.reply_text("⚠️ Ошибка при обращении к ChatGPT.")


async def handle_general_mode(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    user_message: str,
    current_mode: str,
    cost: int,
    coins: int,
    giftcoins: int,
    balance: float,
):
    """Handle the general mode functionality for other modes"""
    from billing_utils import spend_coins

    # Проверяем и ограничиваем количество токенов
    model_name = models_config.MODELS.get(current_mode)
    truncated_history = token_utils.truncate_messages_for_token_limit(
        user_contexts[user_id][current_mode],
        model=model_name,
        reserve_tokens=1500,
    )
    messages = truncated_history + [{"role": "user", "content": user_message}]

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

        response = models_config.client_chat.chat.completions.create(
            model=model_name,  # Используем модель из константы
            messages=messages,
        )
        reply = response.choices[0].message.content

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
        await update.message.reply_text(safe_reply, parse_mode="MarkdownV2")

        # Списываем монеты и записываем лог
        spend_coins(
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


async def handle_voice_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    current_mode: str,
    balance: float,
):
    """Handle voice message transcription and return the transcribed text"""
    # Скачиваем голосовое сообщение
    voice_file = await context.bot.get_file(update.message.voice.file_id)
    # Сохраняем его во временный файл
    file_path = f"voice_{user_id}_{update.message.message_id}.ogg"
    await voice_file.download_to_drive(file_path)

    try:
        # Преобразуем в текст
        user_message = await models_config.transcribe_voice(file_path)
        # Удаляем временный файл
        os.remove(file_path)
        return user_message
    except Exception as e:
        # LOGGING ====================
        log_text = "Не удалось распознать голосовое сообщение."
        dbbot.log_action(user_id, current_mode, log_text, 0, balance)
        print("Ошибка транскрибации:", e)
        await update.message.reply_text(
            "⚠️ Не удалось распознать голосовое сообщение."
        )
        return None


async def handle_message_or_voice(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    user_id = update.effective_user.id
    # Если режим не установлен, устанавливаем режим чата по умолчанию
    if user_id not in user_modes:
        user_modes[user_id] = "chat"

    current_mode = user_modes[user_id]
    print(f"we are in handle message ot voice mode {current_mode}")
    # Continue with standard processing using the augmented question
    # --- ✅ ПРОВЕРКА НАЛИЧИЯ МОНЕТ ---
    user_data, coins, giftcoins, balance, cost = (
        await billing_utils.check_user_coins(user_id, current_mode, context)
    )
    if user_data is None:
        return  # ❌ Прерываем выполнение, если монет не хватает
    # --- ✅ ПРОВЕРКА ЗАВЕРШЕНА ---

    # === ГАРАНТИРОВАННАЯ ИНИЦИАЛИЗАЦИЯ КОНТЕКСТА ДЛЯ ТЕКУЩЕГО РЕЖИМА
    initialize_user_context(user_id, current_mode)

    # Handle file uploads in file_analysis mode
    if current_mode == "ai_file":
        await handle_ai_file_mode(
            update,
            context,
            user_id,
            "",
            cost,
            balance,
        )
        return  # End here for file analysis mode

    # --- ✅ ПРОВЕРКА НАЛИЧИЯ МОНЕТ ---
    user_data, coins, giftcoins, balance, cost = (
        await billing_utils.check_user_coins(user_id, current_mode, context)
    )
    if user_data is None:
        return  # ❌ Прерываем выполнение, если монет не хватает
    # --- ✅ ПРОВЕРКА ЗАВЕРШЕНА ---

    # Обработка режима редактирования изображений
    if current_mode == "edit":
        await handle_edit_mode(
            update,
            context,
            user_id,
            "",
            cost,
            balance
        )
        return

    # === ГАРАНТИРОВАННАЯ ИНИЦИАЛИЗАЦИЯ КОНТЕКСТА ДЛЯ ТЕКУЩЕГО РЕЖИМА ===
    initialize_user_context(user_id, current_mode)

    # Проверяем, является ли сообщение голосовым
    if update.message.voice:
        result = await handle_voice_message(
            update, context, user_id, current_mode, balance
        )
        if result is None:
            return  # Error occurred in voice handling
        user_message = result
    elif update.message.text:
        # Обычное текстовое сообщение
        user_message = update.message.text.strip()
    else:
        return  # Не текст и не голос

    # Обработка в зависимости от режима
    if current_mode == "image":
        await handle_image_mode(
            update,
            context,
            user_id,
            user_message,
            cost,
            coins,
            giftcoins,
            balance,
        )
        return

    # Для режима chat используем специальную функцию с возможностью веб-поиска
    if current_mode == "chat":
        await handle_chat_mode(
            update,
            context,
            user_id,
            user_message,
            cost,
            coins,
            giftcoins,
            balance,
        )
        return
    else:
        # Для других режимов используем общую логику
        await handle_general_mode(
            update,
            context,
            user_id,
            user_message,
            current_mode,
            cost,
            coins,
            giftcoins,
            balance,
        )
