"""Utility functions for handling user interactions,
messages, and edit modes."""

import os
import dbbot
import token_utils
import file_utils
import billing_utils
import models_config
import docx_utils
import xlsx_utils
import pdf_utils
import rtf_utils
import image_edit_utils
from telegram import Update
from telegram.ext import ContextTypes
from telegram.helpers import escape_markdown
from telegram.error import TimedOut
from global_state import (
    user_contexts,
    user_modes,
    user_file_data,
    user_edit_pending,
    edited_photo_id,
    user_last_edited_images,
    MAX_CONTEXT_MESSAGES,
    SYSTEM_PROMPTS,
    RTF_PROMPT,
    MODELS,
)
from message_utils import send_long_message
from pdf_utils import send_pdf_response
from docx_utils import send_docx_response
from xlsx_utils import send_xlsx_response
from rtf_utils import send_rtf_response


def initialize_user_context(user_id: int, current_mode: str):
    """Инициализирует контекст для текущего режима пользователя"""
    if user_id not in user_contexts:
        user_contexts[user_id] = {}

    if current_mode not in user_contexts[user_id]:
        # Определяем системные сообщения для разных режимов
        system_message = SYSTEM_PROMPTS.get(current_mode)
        # Инициализируем контекст с системным сообщением
        user_contexts[user_id][current_mode] = [
            {"role": "system", "content": system_message}
        ]


# ==================== ФУНКЦИЯ НИГДЕ НЕ ИСПОЛЬЗУЕТЯ ====================
async def get_last_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """находит последнее фото в чате"""
    chat_id = update.effective_chat.id
    try:
        # Получаем историю сообщений (последние 15 сообщений)
        messages = await context.bot.get_chat_history(chat_id, limit=15)

        last_photo_id = None
        # Ищем последнее сообщение с фото
        async for message in messages:
            if message.photo:
                last_photo_id = message.photo[-1].file_id
                break
        if last_photo_id:
            # Отправляем пользователю найденный file_id
            return last_photo_id
        else:
            return None
    except Exception as e:
        print(f"Error in get_last_photo: {e}")
        return None


async def handle_file_analysis_mode(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    user_message: str,
    cost: int,
    balance: float,
):
    """Handle the ai_file mode functionality separately"""
    from billing_utils import spend_coins

    wants_word_format = docx_utils.check_user_wants_word_format(user_message)
    wants_pdf_format = pdf_utils.check_user_wants_pdf_format(user_message)
    wants_excel_format = xlsx_utils.check_user_wants_xlsx_format(user_message)
    wants_rtf_format = rtf_utils.check_user_wants_rtf_format(user_message)

    if wants_word_format:
        user_message = user_message + " " + docx_utils.JSON_SCHEMA
    elif wants_pdf_format:
        user_message = user_message + " " + pdf_utils.JSON_SCHEMA_PDF
    elif wants_excel_format:
        user_message = user_message + " " + xlsx_utils.JSON_SCHEMA_EXCEL
    elif wants_rtf_format:
        user_message = user_message + " " + RTF_PROMPT

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
                        reserve_tokens=reserved_tokens_for_context,
                    )

                    # Double-check token count and if still too long,
                    #  truncate the user message specifically
                    total_tokens = token_counter.count_openai_messages_tokens(
                        messages, model_name
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
            # Prepare the full context including system message,
            # history and current query
            system_message = SYSTEM_PROMPTS.get("ai_file")
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

            if wants_word_format:
                # Создаем DOCX файл с ответом
                await send_docx_response(update, reply)
            elif wants_pdf_format:
                # Создаем PDF файл с ответом
                await send_pdf_response(update, reply)
            elif wants_excel_format:
                # Создаем PDF файл с ответом
                await send_xlsx_response(update, reply)
            elif wants_rtf_format:
                # Создаем rtf файл с ответом
                await send_rtf_response(update, reply)
            else:
                # Проверяем, является ли ответ валидным JSON
                # с подходящей структурой
                # для форматов DOCX/PDF
                import json

                try:
                    parsed_reply = json.loads(reply)
                    # Проверяем наличие обязательных полей для форматов
                    if isinstance(parsed_reply, dict) and (
                        "meta" in parsed_reply or "blocks" in parsed_reply
                    ):
                        # Ответ имеет структуру, подходящую для DOCX/PDF
                        # Предлагаем пользователю выбрать формат
                        await update.message.reply_text(
                            "Я подготовил структурированный ответ. "
                            "В каком формате вы хотите получить результат?\n"
                            "/get_docx - для получения в формате Word\n"
                            "/get_pdf - для получения в формате PDF\n"
                            "/get_text - для получения в виде текста"
                        )
                        # Сохраняем ответ во временное хранилище для
                        # последующего использования
                        user_id = update.effective_user.id
                        if user_id not in user_contexts:
                            user_contexts[user_id] = {}
                        if "temp_reply" not in user_contexts[user_id]:
                            user_contexts[user_id]["temp_reply"] = {}
                        user_contexts[user_id]["temp_reply"][
                            "structured_reply"
                        ] = reply
                    else:
                        # Ответ не имеет подходящей структуры,
                        # отправляем как текст
                        # Экранируем специальные символы Markdown,
                        # чтобы избежать ошибок
                        safe_reply = escape_markdown(reply, version=2)
                        # Send the message, splitting if necessary
                        await send_long_message(
                            update, safe_reply, parse_mode="MarkdownV2"
                        )
                except json.JSONDecodeError:
                    # Ответ не является JSON, отправляем как текст
                    # Экранируем специальные символы Markdown,
                    # чтобы избежать ошибок
                    safe_reply = escape_markdown(reply, version=2)
                    # Send the message, splitting if necessary
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
                dbbot.log_action(user_id, "ai_file", log_text, 0, balance,
                                 "error",
                                 "handle_utils>handle_file_analysis_mode"
                                 )
                await update.message.reply_text(
                    "⚠️ Длинное сообщение (ai_file).Cократите пожалуйста."
                )
            else:
                # LOGGING ====================
                log_text = f"Ошибка при обращении к ChatGPT: {str(e)}"
                dbbot.log_action(user_id, "ai_file", log_text, 0, balance,
                                 "error",
                                 "handle_utils>handle_file_analysis_mode"
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


async def handle_image_create_mode(
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
        try:
            await update.message.reply_photo(
                image_url, caption=f"Сгенерировано по запросу: {user_message}"
            )
        except TimedOut:
            await update.message.reply_text(
                "⏰ Время ожидания отправки изображения истекло. "
                "Пожалуйста, попробуйте снова."
            )
            # Логируем ошибку таймаута
            log_text = "Таймаут при отправке сгенерированного изображения"
            dbbot.log_action(user_id, "image", log_text, 0, balance,
                             "error", "handle_utils>handle_image_create_mode")
            return
        except Exception as photo_error:
            raise photo_error
        # Списываем монеты и записываем лог
        spend_coins(user_id, cost, coins, giftcoins, "image", user_message, "")
    except Exception as e:
        # LOGGING ====================
        log_text = f"⚠️ {str(e)}"
        dbbot.log_action(user_id, "image", log_text, 0, balance,
                         "error", "handle_utils>handle_image_create_mode")
        await update.message.reply_text(f"⚠️ {str(e)}")


async def handle_image_edit_mode(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    user_message: str,
    cost: int,
    coins: int,
    giftcoins: int,
    balance: float,
):
    """Handle the image edit mode functionality separately"""
    from billing_utils import spend_coins
    import os

    # Инициализируем переменную для пути к файлу
    file_path = None
    file_ext = ".jpg"  # Телеграм все в jpeg превращает
    # Проверяем, есть ли фото в сообщении
    if update.message.photo:
        if user_id in edited_photo_id:
            # Удаляем предыдущее (отредактированное) фото из кэша
            del edited_photo_id[user_id]

        # Если у пользователя уже есть предыдущее
        # отредактированное изображение, удаляем его
        if user_id in user_last_edited_images:
            if os.path.exists(user_last_edited_images[user_id]):
                os.remove(user_last_edited_images[user_id])
            del user_last_edited_images[user_id]

        # Сохраняем информацию о фото для последующего редактирования
        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        # Скачиваем файл
        file_path = (
            f"temp_edit_{user_id}_{update.message.message_id}{file_ext}"
        )
        await file.download_to_drive(file_path)

        if not user_message:
            # Сохраняем путь к файлу в состоянии ожидания
            user_edit_pending[user_id] = file_path
            await update.message.reply_text(
                "✏️ Теперь укажите, что нужно выполнить с изображением."
            )
            return
    else:
        # Нет фото в текущем сообщении
        if user_id in user_edit_pending:
            # Проверяем, есть ли ожидающее изображение для редактирования
            file_path = user_edit_pending[user_id]
            # Удаляем из состояния ожидания
            del user_edit_pending[user_id]
            # Проверяем, существует ли файл
            if not os.path.exists(file_path):
                await update.message.reply_text(
                    """
                    ❌ Время ожидания истекло или файл был удален.
                    Пожалуйста, отправьте изображение заново.
                    """
                )
                return
        elif user_message and user_id in user_last_edited_images:
            # Если пользователь отправляет промпт без изображения
            # и есть предыдущее изображение
            file_path = user_last_edited_images[user_id]
            # Проверяем, существует ли файл
            if not os.path.exists(file_path):
                await update.message.reply_text(
                  """
                  🖼️ Предыдущее изображение не найдено.
                  Пожалуйста, отправьте новое изображение для редактирования.
                  """
                )
                return
        else:
            # Нет фото и нет ожидающего изображения или предыдущего изображения
            # await update.message.reply_text(
            #    "🖼️ Пожалуйста, отправьте изображение для редактирования."
            # )
            # return
            file_path = None
    try:
        # Подсчитываем токены, использованные для запроса
        model_name = MODELS["edit"]
        token_count = token_utils.token_counter.count_openai_tokens(
            user_message, model_name
        )
        # Отправляем сообщение о начале редактирования
        await update.message.reply_text("🎨 Редактирую изображение...")

        # Редактируем изображение
        try:
            edited_image_bytes = await image_edit_utils.edit_image(
                file_path, user_message
            )
        except TimedOut:
            await update.message.reply_text(
                "⏰ Время ожидания редактирования изображения истекло. "
                "Пожалуйста, попробуйте снова с более простым запросом, "
                "или другим изображением."
            )
            # Логируем ошибку таймаута редактирования
            log_text = "Таймаут при редактировании изображения"
            dbbot.log_action(user_id, "edit", log_text, 0, balance,
                             "error", "handle_utils>handle_image_edit_mode")
            return
        except Exception as edit_error:
            if "timeout" in str(edit_error).lower():
                await update.message.reply_text(
                    "⏰ Время ожидания редактирования изображения истекло. "
                    "Пожалуйста, попробуйте снова с более простым запросом, "
                    "или другим изображением."
                )
                # Логируем ошибку таймаута редактирования
                log_text = f"Таймаут при редактировании: {str(edit_error)}"
                dbbot.log_action(user_id, "edit", log_text, 0, balance,
                                 "error",
                                 "handle_utils>handle_image_edit_mode"
                                 )
                return
            else:
                raise edit_error

        # Сохраняем отредактированное изображение
        edited_file_path = (
            f"edited_{user_id}_{update.message.message_id}{file_ext}"
        )
        with open(edited_file_path, "wb") as f:
            f.write(edited_image_bytes)

        # Отправляем отредактированное изображение пользователю
        try:
            with open(edited_file_path, "rb") as f:
                await update.message.reply_photo(
                    photo=f,
                    caption=f"Отредактировано по запросу: {user_message}",
                )
        except TimedOut:
            await update.message.reply_text(
                "⏰ Время ожидания отправки изображения истекло. "
                "Пожалуйста, попробуйте снова или с другим изображением."
            )
            # Логируем ошибку таймаута
            log_text = "Таймаут при отправке изображения"
            dbbot.log_action(user_id, "edit", log_text, 0, balance,
                             "error", "handle_utils>handle_image_edit_mode")
        except Exception as e:
            raise e

        # Если у пользователя уже есть предыдущее
        # отредактированное изображение,
        # удаляем его перед сохранением нового
        if user_id in user_last_edited_images:
            if os.path.exists(user_last_edited_images[user_id]):
                os.remove(user_last_edited_images[user_id])

        # Сохраняем путь к отредактированному
        # изображению как последнее отредактированное
        user_last_edited_images[user_id] = edited_file_path

        # Списываем монеты и записываем лог
        spend_coins(
            user_id,
            cost,
            coins,
            giftcoins,
            "edit",
            user_message,
            f"Token usage: {token_count}",
        )

        # Удаляем временные файлы
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
        # Удаляем из состояния ожидания, если оно там есть
        if user_id in user_edit_pending:
            del user_edit_pending[user_id]

    except Exception as e:
        # Удаляем временные файлы даже при ошибке
        if file_path and os.path.exists(file_path):
            os.remove(file_path)

        # Удаляем из состояния ожидания, если оно там есть
        if user_id in user_edit_pending:
            del user_edit_pending[user_id]

        # LOGGING ====================
        log_text = f"Ошибка при редактировании изображения: {str(e)}"
        dbbot.log_action(user_id, "edit", log_text, 0, balance,
                         "error", "handle_utils>handle_image_edit_mode")
        await update.message.reply_text(log_text)


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
        # Include chat history for context with proper token limit
        model_name = models_config.MODELS.get("chat")
        user_context = []

        wants_word_format = docx_utils.check_user_wants_word_format(
            user_message
        )
        wants_pdf_format = pdf_utils.check_user_wants_pdf_format(user_message)
        wants_excel_format = xlsx_utils.check_user_wants_xlsx_format(
            user_message
        )
        wants_rtf_format = rtf_utils.check_user_wants_rtf_format(user_message)
        if wants_word_format:
            user_message = user_message + " " + docx_utils.JSON_SCHEMA
        elif wants_pdf_format:
            user_message = user_message + " " + pdf_utils.JSON_SCHEMA_PDF
        elif wants_excel_format:
            user_message = user_message + " " + xlsx_utils.JSON_SCHEMA_EXCEL
        elif wants_rtf_format:
            user_message = user_message + " " + RTF_PROMPT
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
            await send_docx_response(update, reply)
        elif wants_pdf_format:
            # Создаем PDF файл с ответом
            await send_pdf_response(update, reply)
        elif wants_excel_format:
            # Создаем EXCEL файл с ответом
            await send_xlsx_response(update, reply)
        elif wants_rtf_format:
            # Создаем rtf файл с ответом
            await send_rtf_response(update, reply)
        else:
            # Ответ не имеет подходящей структуры, отправляем как текст
            # Экранируем специальные символы Markdown, чтобы избежать ошибок
            safe_reply = escape_markdown(reply, version=2)
            # Send the message, splitting if necessary
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
        dbbot.log_action(user_id, "chat", log_text, 0, balance,
                         "error", "handle_utils>handle_chat_mode")
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
        log_text = f"Не удалось распознать голосовое сообщение. {e}"
        dbbot.log_action(user_id, current_mode, log_text, 0, balance,
                         "error", "handle_utils>handle_voice_message")
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

    # Проверяем, изменился ли режим и нужно
    # ли очистить состояние ожидания редактирования
    from global_state import (
        user_edit_pending,
        user_previous_modes,
        user_last_edited_images,
    )

    previous_mode = user_previous_modes.get(user_id)
    if (
        user_id in user_edit_pending
        and previous_mode
        and previous_mode != current_mode
    ):
        # Если пользователь меняет режим,
        # удаляем ожидающее изображение для редактирования
        if os.path.exists(user_edit_pending[user_id]):
            os.remove(user_edit_pending[user_id])
        del user_edit_pending[user_id]

    # Также очищаем предыдущее отредактированное изображение,
    # если пользователь меняет режим с edit на другой
    if (
        user_id in user_last_edited_images
        and previous_mode == "edit"
        and current_mode != "edit"
    ):
        # Удаляем файл предыдущего отредактированного изображения
        if os.path.exists(user_last_edited_images[user_id]):
            os.remove(user_last_edited_images[user_id])
        del user_last_edited_images[user_id]

    # Сохраняем текущий режим как предыдущий для следующей проверки
    user_previous_modes[user_id] = current_mode

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
    elif update.message.document:
        # File message - we'll pass empty string as user_message
        # and let the mode handler process the file
        user_message = ""
    elif update.message.photo:
        # Photo message - check if it has a caption
        if update.message.caption:
            user_message = update.message.caption.strip()
        else:
            user_message = ""
    else:
        return  # Не текст, не голос и не файл

    # Handle file uploads in file_analysis mode
    if current_mode == "ai_file":
        await handle_file_analysis_mode(
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
        await handle_image_edit_mode(
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

    # Обработка в зависимости от режима
    if current_mode == "image":
        await handle_image_create_mode(
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
