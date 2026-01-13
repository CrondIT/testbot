"""Utility functions for handling user interactions,
messages, and edit modes."""

import os
import io
from PIL import Image
import dbbot
import token_utils
import file_utils
import billing_utils
import models_config
import docx_utils
from telegram import Update
from telegram.ext import ContextTypes
from telegram.helpers import escape_markdown
from global_state import (
    user_contexts,
    user_modes,
    user_edit_data,
    user_file_data,
    MAX_CONTEXT_MESSAGES,
)
import json
from docx import Document
from telegram import InputFile


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
        system_message = models_config.SYSTEM_PROMPTS.get(current_mode)
        # Инициализируем контекст с системным сообщением
        user_contexts[user_id][current_mode] = [
            {"role": "system", "content": system_message}
        ]


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
            )
        return
    # Если пользователь отправил текст
    # или голосовое сообщение (уже преобразованное)
    elif user_message:
        # user_message is already processed (either from text or voice)
        if edit_data.get("step") == "waiting_prompt":
            await update.message.reply_text("🔄 Редактирую изображение...")
            try:
                original_image = user_edit_data[user_id]["original_image"]
                # Редактируем изображение с помощью Gemini
                edited_image_data = await models_config.edit_image_with_gemini(
                    original_image, user_message
                )
                # Проверяем, хочет ли пользователь
                #  получить описание в формате Word
                wants_word_format = docx_utils.check_user_wants_word_format(
                    user_message
                )

                # Сохраняем изображение во временный файл
                file_path = await save_image_from_data(
                    edited_image_data, f"edited_{user_id}"
                )

                if wants_word_format:
                    # Создаем DOCX файл с описанием редактирования
                    try:
                        # Создаем текст описания
                        description_text = (
                            f"Отредактированное изображение\n\n"
                            f"Запрос на редактирование: {user_message}\n\n"
                            f"Изображение было отредактировано по запросу."
                        )

                        # Парсим запрос пользователя на предмет форматирования
                        formatting_instructions = (
                            docx_utils.parse_formatting_request(user_message)
                        )

                        # Очищаем содержимое от форматирования
                        # и упоминаний о DOCX
                        clean_description_text = (
                            docx_utils.clean_content_for_docx(description_text)
                        )

                        # Создаем DOCX файл
                        docx_file = docx_utils.create_formatted_docx(
                            clean_description_text, formatting_instructions
                        )
                        # Убедимся, что указатель находится в начале файла
                        docx_file.seek(0)

                        # Отправляем DOCX файл пользователю и изображение
                        await update.message.reply_document(
                            document=docx_file,
                            filename="document.docx",
                            caption="""
                            Описание отредактированного изображения
                            в формате Word (DOCX)""",
                        )
                        with open(file_path, "rb") as photo:
                            await update.message.reply_photo(
                                photo,
                                caption=(
                                    f"Отредактировано"
                                    f" по запросу: {user_message}"
                                ),
                            )
                    except Exception as e:
                        # Если не удалось создать или отправить DOCX,
                        # отправляем обычное сообщение
                        with open(file_path, "rb") as photo:
                            await update.message.reply_photo(
                                photo,
                                caption=(
                                    f"Отредактировано"
                                    f" по запросу: {user_message}"
                                ),
                            )
                        print(
                            f"Ошибка при создании или отправке DOCX файла: {e}"
                        )
                else:
                    # Отправляем обычное изображение
                    with open(file_path, "rb") as photo:
                        await update.message.reply_photo(
                            photo,
                            caption=(
                                f"Отредактировано по запросу: {user_message}"
                            ),
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
        print("1. Check if the message contains a document")
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
            print("2. Extract text from file")
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
        # This will be true for both text messages and voice-converted messages
        user_message
        and user_id in user_file_data
        and "extracted_text" in user_file_data[user_id]
    ):
        # Process the question about the file content
        # user_message is already processed (either from text or voice)
        extracted_text = user_file_data[user_id]["extracted_text"]
        model_name = models_config.MODELS.get("ai_file")

        max_tokens = token_utils.get_token_limit(model_name)

        print(f"model {model_name} max tokens {max_tokens}")

        # Calculate more conservative character
        # limit considering the full message with history
        # Reserve more tokens for context,
        # history, and response (2500 instead of 1500)
        reserved_tokens_for_context = 2500
        max_content_tokens = max_tokens - reserved_tokens_for_context

        # Calculate max characters based on estimated token size
        avg_token_size = 3  # Average size of a token in characters
        max_chars = min(
            len(extracted_text), max_content_tokens * avg_token_size
        )
        print(f"max_chars {max_chars}")
        if len(extracted_text) > max_chars:
            # Truncate the extracted text and inform the user
            truncated_extracted_text = extracted_text[:max_chars]
            await update.message.reply_text(
                f"📝 Объем файла превышает лимит. Использую первую "
                f"часть текста ({max_chars} символов) для анализа."
            )
        else:
            truncated_extracted_text = extracted_text

        # Add file content to the user's question
        augmented_question = (
            f"Файл содержит следующий текст:"
            f" {truncated_extracted_text}\n\nВопрос: {user_message}"
        )

        # First check if the augmented question itself is too long
        question_tokens = token_utils.token_counter.count_openai_tokens(
            augmented_question, model_name
        )
        print(f"question_tokens {question_tokens}")
        if question_tokens > max_content_tokens:
            # The combined content (file + question) exceeds token limits
            # Try to preserve as much of the file content
            # as possible and truncate the user's question

            # Calculate tokens used by file content and header
            content_and_header_text = (
                f"Файл содержит следующий текст: "
                f"{truncated_extracted_text}\n\nВопрос: "
            )
            content_and_header_tokens = (
                token_utils.token_counter.count_openai_tokens(
                    content_and_header_text, model_name
                )
            )

            # Available tokens for the user's question
            # (with buffer for response)
            available_for_question = (
                max_tokens - content_and_header_tokens - 500
            )  # buffer for response

            if available_for_question > 0:
                # Calculate max characters for the user's question
                max_question_chars = int(
                    available_for_question * avg_token_size
                )
                if len(user_message) > max_question_chars:
                    # Truncate the user's question to fit with the file content
                    truncated_user_message = user_message[:max_question_chars]
                    augmented_question = (
                        f"Файл содержит следующий текст:"
                        f" {truncated_extracted_text}\n\n"
                        f" Вопрос: {truncated_user_message}"
                    )
                    await update.message.reply_text(
                        f"Вопрос сокращен до {len(truncated_user_message)} с."
                        f"для укладывания в лимиты вместе с содержимым файла."
                    )
                else:
                    # The issue might be with accumulated context history,
                    # not the question length
                    # We'll proceed with the original augmented question
                    # and let the later truncation handle it
                    pass
            else:
                # Not enough tokens even for the file content and header,
                # so truncate everything
                max_total_chars = max_content_tokens * avg_token_size
                augmented_question = augmented_question[:max_total_chars]
                await update.message.reply_text(
                    f"Общий объем текста (файл+вопрос) сокращен"
                    f"до {max_total_chars} символов для укладывания в лимиты."
                )

        print(
            f"model {model_name} max tokens {max_tokens}"
            f"max_chars {max_chars} question_tokens {question_tokens}"
        )

        # Prepare messages with truncated history
        # using the augmented question
        truncated_history = token_utils.truncate_messages_for_token_limit(
            user_contexts[user_id]["ai_file"],
            model=model_name,
            reserve_tokens=reserved_tokens_for_context,
        )
        messages = truncated_history + [
            {"role": "user", "content": augmented_question}
        ]

        # Дополнительно ограничиваем длину истории
        if len(messages) > MAX_CONTEXT_MESSAGES:
            messages = messages[-MAX_CONTEXT_MESSAGES:]

        try:
            # Используем клиент чата
            print("3. Используем клиент чата")
            # Проверяем, что последнее сообщение - это от пользователя
            if messages and messages[-1]["role"] == "user":
                # Проверяем токены перед отправкой
                print("4. Проверяем токены перед отправкой")
                token_counter = token_utils.token_counter
                total_tokens = token_counter.count_openai_messages_tokens(
                    messages, model_name
                )
                max_tokens = token_utils.get_token_limit(model_name)
                print(f"4 before send total {total_tokens} max {max_tokens}")
                if total_tokens > max_tokens:
                    print("5 Обрезаем сообщения до ... [truncated]")
                    # Обрезаем сообщения до ... [truncated]
                    messages = token_utils.truncate_messages_for_token_limit(
                        messages,
                        model=model_name,
                        reserve_tokens=reserved_tokens_for_context,
                    )

                    # Double-check token count and if still too long,
                    #  truncate the user message specifically
                    total_tokens = token_counter.count_openai_messages_tokens(
                        messages, model_name
                    )
                    print(
                        f"Double-check tokens before send {total_tokens}"
                        f"max tokens {max_tokens}"
                        f"message {messages}"
                    )
                    if (
                        total_tokens > max_tokens
                        and messages
                        and messages[-1]["role"] == "user"
                    ):
                        original_content = messages[-1]["content"]
                        remaining_tokens = max_tokens - (
                            total_tokens
                            - token_utils.token_counter.count_openai_tokens(
                                original_content, model_name
                            )
                        )
                        if remaining_tokens > 0:
                            max_content_chars = (
                                remaining_tokens * avg_token_size
                            )
                            messages[-1]["content"] = original_content[
                                :max_content_chars
                            ]
            print(f"6. model {model_name} {user_message}")
            # Prepare the full context including system message,
            # history and current query
            system_message = models_config.SYSTEM_PROMPTS.get("ai_file")
            full_context = (
                [{"role": "system", "content": system_message}]
                + truncated_history
                + [{"role": "user", "content": augmented_question}]
            )
            reply = await models_config.ask_gpt51_with_web_search(
                context_history=full_context,
                enable_web_search=False,
            )

            # reply = response.choices[0].message.content

            # Обновляем контекст: добавляем и запрос, и ответ
            user_contexts[user_id]["ai_file"].append(
                {"role": "user", "content": augmented_question}
            )
            user_contexts[user_id]["ai_file"].append(
                {"role": "assistant", "content": reply}
            )

            # Проверяем, хочет ли пользователь получить ответ в формате Word
            wants_word_format = docx_utils.check_user_wants_word_format(
                user_message
            )

            if wants_word_format:
                # Создаем DOCX файл с ответом
                try:
                    # Парсим запрос пользователя на предмет форматирования
                    formatting_instructions = (
                        docx_utils.parse_formatting_request(user_message)
                    )

                    # Очищаем содержимое от форматирования и упоминаний о DOCX
                    clean_reply = docx_utils.clean_content_for_docx(reply)

                    # Создаем DOCX файл
                    docx_file = docx_utils.create_formatted_docx(
                        clean_reply, formatting_instructions
                    )
                    # Убедимся, что указатель находится в начале файла
                    docx_file.seek(0)

                    # Отправляем DOCX файл пользователю
                    await update.message.reply_document(
                        document=docx_file,
                        filename="document.docx",
                        caption="Ваш ответ в формате Word (DOCX)",
                    )
                except Exception as e:
                    # Если не удалось создать или отправить DOCX,
                    # отправляем обычное сообщение
                    safe_reply = escape_markdown(reply, version=2)
                    await send_long_message(
                        update, safe_reply, parse_mode="MarkdownV2"
                    )
                    print(f"Ошибка при создании или отправке DOCX файла: {e}")
            else:
                # Отправляем обычный ответ
                # Экранируем специальные символы Markdown,
                # чтобы избежать ошибок
                safe_reply = escape_markdown(reply, version=2)
                await send_long_message(
                    update, safe_reply, parse_mode="MarkdownV2"
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
                reply,  # Сохраняем оригинальный ответ в логах
            )
        except Exception as e:
            # Обработка ошибки "Message is too long" и других
            error_msg = str(e)
            if "too long" in error_msg.lower() or "token" in error_msg.lower():
                # LOGGING ====================
                log_text = f"Ошибка (ai_file): Сообщение длинное: {str(e)}"
                dbbot.log_action(user_id, "ai_file", log_text, 0, balance)
                await update.message.reply_text(
                    "⚠️ Длинное сообщение (ai_file).Cократите пожалуйста."
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

    # Проверяем, хочет ли пользователь получить описание в формате Word
    wants_word_format = docx_utils.check_user_wants_word_format(user_message)

    try:
        image_url = await models_config.generate_image(user_message)

        if wants_word_format:
            # Создаем DOCX файл с описанием изображения
            try:
                # Создаем простой текст описания
                description_text = (
                    f"Сгенерированное изображение\n\n"
                    f" Запрос: {user_message}\n\n"
                    f" Изображение было сгенерировано по вашему запросу."
                )

                # Парсим запрос пользователя на предмет форматирования
                formatting_instructions = docx_utils.parse_formatting_request(
                    user_message
                )

                # Очищаем содержимое от форматирования и упоминаний о DOCX
                clean_description_text = docx_utils.clean_content_for_docx(
                    description_text
                )

                # Создаем DOCX файл
                docx_file = docx_utils.create_formatted_docx(
                    clean_description_text, formatting_instructions
                )
                # Убедимся, что указатель находится в начале файла
                docx_file.seek(0)

                # Отправляем DOCX файл пользователю и изображение
                await update.message.reply_document(
                    document=docx_file,
                    filename="document.docx",
                    caption="""
                        Описание сгенерированного изображения
                        в формате Word (DOCX)
                        """,
                )
                await update.message.reply_photo(
                    image_url,
                    caption=f"Сгенерировано по запросу: {user_message}",
                )
            except Exception as e:
                # Если не удалось создать или отправить DOCX,
                # отправляем обычное сообщение
                await update.message.reply_photo(
                    image_url,
                    caption=f"Сгенерировано по запросу: {user_message}",
                )
                print(f"Ошибка при создании или отправке DOCX файла: {e}")
        else:
            # Отправляем обычное изображение
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


async def send_long_message(update: Update, text: str, parse_mode: str = None):
    """
    Отправляет длинное сообщение, разбивая его на части,
    если оно превышает лимит Telegram (4096 символов)
    """
    # Telegram's message limit is 4096 characters
    TELEGRAM_MESSAGE_LIMIT = 4096

    if len(text) <= TELEGRAM_MESSAGE_LIMIT:
        # Message fits in a single message
        await update.message.reply_text(text, parse_mode=parse_mode)
        return

    # Split the message by paragraphs first to avoid breaking sentences
    paragraphs = text.split("\n")

    current_message = ""
    for paragraph in paragraphs:
        # Check if adding this paragraph would exceed the limit
        if len(current_message) + len(paragraph) + 1 <= TELEGRAM_MESSAGE_LIMIT:
            if current_message:
                current_message += "\n" + paragraph
            else:
                current_message = paragraph
        else:
            # Send the current message if it's not empty
            if current_message:
                await update.message.reply_text(
                    current_message, parse_mode=parse_mode
                )

            # If the single paragraph is too long, split it by sentences
            if len(paragraph) > TELEGRAM_MESSAGE_LIMIT:
                sentences = paragraph.split(". ")
                temp_message = ""
                for sentence in sentences:
                    if (
                        len(temp_message) + len(sentence) + 2
                        <= TELEGRAM_MESSAGE_LIMIT
                    ):
                        if temp_message:
                            temp_message += ". " + sentence
                        else:
                            temp_message = sentence
                    else:
                        if temp_message:
                            await update.message.reply_text(
                                temp_message + ".", parse_mode=parse_mode
                            )
                        temp_message = sentence

                # Add the last part if there's anything left
                if temp_message:
                    current_message = temp_message
                else:
                    current_message = ""
            else:
                current_message = paragraph

    # Send the remaining message if there's anything left
    if current_message:
        await update.message.reply_text(current_message, parse_mode=parse_mode)


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
    print(f"we are in handle_chat_mode, user_message-{user_message}")
    from billing_utils import spend_coins

    try:
        # Используем функцию с веб-поиском для режима chat
        # Include chat history for context with proper token limit
        model_name = models_config.MODELS.get("chat")
        user_context = []
        # Проверяем, хочет ли пользователь получить ответ в формате Word
        wants_word_format = docx_utils.check_user_wants_word_format(
            user_message
        )
        if wants_word_format:
            user_message = user_message + """
               Верни ТОЛЬКО валидный JSON без пояснений.
                Строгая схема:
                {
                "meta": {"title": "string"},
                "blocks": [
                    {"type":"heading","level":1,"text":"string"},
                    {"type":"paragraph","text":"string"},
                    {"type":"list", "ordered":false, "items":["item1", "item2"]},
                    {"type":"table", "headers":["column1", "column2"], "rows":[["value1", "value2"], ["value3", "value4"]]}
                ]
                }
            """
        if user_id in user_contexts and "chat" in user_contexts[user_id]:
            # Create a temporary history that includes the current user message
            temp_history = user_contexts[user_id]["chat"] + [
                {"role": "user", "content": user_message}
            ]

            # Truncate history based on token limits,
            # including the current message
            user_context = token_utils.truncate_messages_for_token_limit(
                messages=temp_history,
                model=model_name,
                reserve_tokens=1500,
            )

        # Additionally limit the number of messages in history
        if len(user_context) > MAX_CONTEXT_MESSAGES:
            user_context = user_context[-MAX_CONTEXT_MESSAGES:]

        reply = await models_config.ask_gpt51_with_web_search(
            enable_web_search=True,
            context_history=user_context,
        )

        # Обновляем контекст: добавляем и запрос, и ответ
        user_contexts[user_id]["chat"].append(
            {"role": "user", "content": user_message}
        )
        user_contexts[user_id]["chat"].append(
            {"role": "assistant", "content": reply}
        )

        if wants_word_format:
            # Создаем DOCX файл с ответом
            try:
                data = json.loads(reply)

                doc_io = io.BytesIO()
                renderer = docx_utils.DocxRenderer()
                renderer.render(data, doc_io)
                doc_io.seek(0)

                await update.message.reply_document(
                    document=InputFile(doc_io, filename="document.docx"),
                    caption="Ваш ответ в формате Word",
                )
            except Exception as e:
                # Если не удалось создать или отправить DOCX,
                # отправляем обычное сообщение
                safe_reply = escape_markdown(reply, version=2)
                await send_long_message(
                    update, safe_reply, parse_mode="MarkdownV2"
                )
                print(f"Ошибка при создании или отправке DOCX файла: {e}")
        else:
            # Отправляем обычный ответ
            # Экранируем специальные символы Markdown, чтобы избежать ошибок
            safe_reply = escape_markdown(reply, version=2)

            # Send the message, splitting if necessary
            # to respect Telegram's character limit
            await send_long_message(
                update, safe_reply, parse_mode="MarkdownV2"
            )

        # Списываем монеты и записываем лог
        spend_coins(
            user_id,
            cost,
            coins,
            giftcoins,
            "chat",
            user_message,
            reply,  # Сохраняем оригинальный ответ в логах
        )
    except Exception as e:
        # LOGGING ====================
        log_text = f"Ошибка при обращении к ChatGPT: {str(e)}"
        print(log_text)
        dbbot.log_action(user_id, "chat", log_text, 0, balance)
        await update.message.reply_text("⚠️ Ошибка при обращении к ChatGPT.")


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

    # --- start coins check ---
    user_data, coins, giftcoins, balance, cost = (
        await billing_utils.check_user_coins(user_id, current_mode, context)
    )
    if user_data is None:
        return  # Прерываем выполнение, если монет не хватает
    # --- end coins check ---

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
    elif update.message.document or update.message.photo:
        # File or photo message - we'll pass empty string as user_message
        # and let the mode handler process the file
        user_message = ""
    else:
        return  # Не текст, не голос и не файл

    # Handle file uploads in file_analysis mode
    if current_mode == "ai_file":
        await handle_ai_file_mode(
            update,
            context,
            user_id,
            user_message,
            cost,
            balance,
        )
        return  # End here for file analysis mode

    # Обработка режима редактирования изображений
    if current_mode == "edit":
        await handle_edit_mode(
            update, context, user_id, user_message, cost, balance
        )
        return

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
