import os
from dotenv import load_dotenv
from openai import OpenAI
from telegram import Update
from telegram.ext import MessageHandler, ContextTypes, filters, CommandHandler
from telegram.ext import ApplicationBuilder
from ddgs import DDGS
from PIL import Image
import io
import google.generativeai as genai
import dbbot

# Загрузить переменные из файла .env
load_dotenv()

# Получаем токены для разных режимов
OPENAI_API_KEY_CHAT = os.getenv("OPENAI_API_KEY")
OPENAI_API_KEY_IMAGE = os.getenv("OPENAI_API_KEY_IMAGE")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_TOKEN2")

# Инициализация клиентов OpenAI для разных режимов
client_chat = OpenAI(api_key=OPENAI_API_KEY_CHAT)
client_image = OpenAI(api_key=OPENAI_API_KEY_IMAGE)

# Инициализация клиента Gemini
genai.configure(api_key=GEMINI_API_KEY)

# Хранилище контекста для каждого пользователя и каждого режима
user_contexts = {}
user_modes = {}  # Хранит текущий режим для каждого пользователя
user_edit_data = {}  # Хранит данные для редактирования изображений
MAX_CONTEXT_MESSAGES = 10


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user_id = update.effective_user.id
    user = dbbot.get_user(user_id)
    coins = user['coins'] + user['giftcoins']

    user_modes[user_id] = "chat"  # Устанавливаем режим по умолчанию
    welcome_text = f"""
        🤖 Добро пожаловать в мульти-режимного бота!
        Ваш ID: {user_id}, у Вас {coins} монета

        Доступные команды:
        /ai - Чат с ИИ
        /ai_internet - ИИ с поиском в интернете
        /ai_image - Генерация изображений
        /ai_edit - Редактирование изображений

        Выберите режим и начните общение!
        """
    await update.message.reply_text(welcome_text)


async def ai_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Активация режима обычного чата"""
    user_id = update.effective_user.id
    user_modes[user_id] = "chat"
    if user_id not in user_contexts:
        user_contexts[user_id] = {}
    if "chat" not in user_contexts[user_id]:
        user_contexts[user_id]["chat"] = [
            {"role": "system",
             "content": (
                "Ты дружелюбный Telegram-бот, "
                "отвечай понятно и по существу."
                )
             }
        ]
    # Очищаем данные редактирования при смене режима
    if user_id in user_edit_data:
        del user_edit_data[user_id]
    await update.message.reply_text(
        "🔮 Режим чата (OpenAI) активирован. Задавайте вопросы!"
        )


async def ai_internet_command(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
        ):
    """Активация режима поиска в интернете"""
    user_id = update.effective_user.id
    user_modes[user_id] = "internet"
    if user_id not in user_contexts:
        user_contexts[user_id] = {}
    if "internet" not in user_contexts[user_id]:
        user_contexts[user_id]["internet"] = [
            {
                "role": "system",
                "content": (
                    "Ты помощник, который ищет информацию в интернете "
                    "и предоставляет актуальные данные."
                )
            }
        ]
    # Очищаем данные редактирования при смене режима
    if user_id in user_edit_data:
        del user_edit_data[user_id]
    await update.message.reply_text(
        "🌐 Режим поиска в интернете активирован. "
        "Задавайте вопросы с поиском!"
        )


async def ai_image_command(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
        ):
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
        "original_image": None
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
    file_id: str,
    context: ContextTypes.DEFAULT_TYPE
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
            if img.mode in ('P', 'RGBA', 'LA'):
                # Создаем белый фон для изображений с прозрачностью
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                background.paste(
                    img,
                    mask=img.split()[-1] if img.mode == 'RGBA' else None
                    )
                img = background
            elif img.mode != 'RGB':
                img = img.convert('RGB')
            # Сохраняем как PNG
            png_data = io.BytesIO()
            img.save(png_data, format='PNG', optimize=True)
            png_data.seek(0)
            return png_data
    except Exception as e:
        print(f"Ошибка конвертации изображения: {e}")
        # Если не удалось конвертировать, возвращаем исходные данные
        image_data.seek(0)
        return image_data


async def generate_image(prompt: str) -> str:
    """Генерирует изображение с помощью DALL-E"""
    try:
        response = client_image.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size="1024x1024",
            quality="standard",
            n=1,
        )
        return response.data[0].url
    except Exception as e:
        raise Exception(f"Ошибка генерации изображения: {str(e)}")


async def edit_image_with_gemini(
        original_image: io.BytesIO,
        prompt: str
        ) -> str:
    """Редактирует изображение с помощью Gemini 2.5 Flash"""
    try:
        # Подготовка изображения для Gemini
        original_image.seek(0)
        # Создаем модель Gemini
        model = genai.GenerativeModel('gemini-2.5-flash-image')
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
        response = model.generate_content([
            gemini_prompt,
            {"mime_type": "image/png", "data": original_image.getvalue()}
        ])
        # Проверяем, содержит ли ответ изображение
        if hasattr(response, 'candidates') and response.candidates:
            for part in response.candidates[0].content.parts:
                if hasattr(part, 'inline_data'):
                    # Возвращаем данные изображения
                    return part.inline_data.data
                elif hasattr(part, 'text'):
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
            file=audio_file
        )
    return transcription.text


async def handle_message_or_voice(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
        ):
    user_id = update.effective_user.id
    # Если режим не установлен, устанавливаем режим чата по умолчанию
    if user_id not in user_modes:
        user_modes[user_id] = "chat"

    current_mode = user_modes[user_id]

    # Обработка режима редактирования изображений
    if current_mode == "edit":
        await handle_edit_mode(update, context, user_id)
        return

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

    # Обработка в зависимости от режима
    if current_mode == "image":
        # Режим генерации изображений
        await update.message.reply_text("🎨 Генерирую изображение...")
        try:
            image_url = await generate_image(user_message)
            await update.message.reply_photo(
                image_url,
                caption=f"Сгенерировано по запросу: {user_message}"
                )
        except Exception as e:
            await update.message.reply_text(f"⚠️ {str(e)}")
        return

    # Инициализация контекста для текущего режима
    if user_id not in user_contexts:
        user_contexts[user_id] = {}

    if current_mode not in user_contexts[user_id]:
        if current_mode == "chat":
            user_contexts[user_id][current_mode] = [
                {
                 "role": "system",
                 "content": "Ты дружелюбный Telegram-бот, "
                 "отвечай понятно и по существу."
                 }
            ]
        else:  # internet mode
            user_contexts[user_id][current_mode] = [
                {
                 "role": "system",
                 "content": "Ты помощник, который ищет информацию "
                 "в интернете и предоставляет актуальные данные."
                 }
            ]

    # Для режима internet проверяем необходимость поиска
    if current_mode == "internet":
        try:
            await update.message.reply_text("🔍 Ищу информацию в интернете...")
            # Выполняем поиск через DuckDuckGo
            results = DDGS().text(user_message, max_results=4)

            if not results:
                await update.message.reply_text(
                    "❌ Не удалось найти результаты по запросу."
                    )
                return

            # Формируем текст из результатов
            search_content = "\n".join([
                f"{i+1}. [{r['title']}]({r['href']}): {r['body']}"
                for i, r in enumerate(results)
            ])

            # Подготовим сообщение с результатами для GPT
            search_prompt = f"""Вот результаты поиска в интернете:
                \n\n{search_content}\n\nОтветь на запрос пользователя,
                используя эту информацию: {user_message}"""

            # Формируем сообщения для GPT
            messages = (
                user_contexts[user_id][current_mode] +
                [{"role": "user", "content": search_prompt}]
            )

        except Exception as e:
            print("Ошибка поиска DuckDuckGo:", e)
            await update.message.reply_text(
                "⚠️ Не удалось выполнить поиск в интернете."
                )
            return
    else:
        # Обычный режим — добавляем сообщение пользователя
        messages = user_contexts[user_id][current_mode] + [
            {
             "role": "user",
             "content": user_message
             }
            ]

    # Ограничиваем длину истории
    if len(messages) > MAX_CONTEXT_MESSAGES:
        messages = messages[-MAX_CONTEXT_MESSAGES:]

    try:
        # Используем клиент чата для обоих текстовых режимов
        response = client_chat.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages
        )

        reply = response.choices[0].message.content

        # Обновляем контекст: добавляем и запрос, и ответ
        if current_mode == "internet":
            user_contexts[user_id][current_mode].append(
                {
                 "role": "user",
                 "content": user_message
                 }
            )
        user_contexts[user_id][current_mode].append(
            {
             "role": "assistant",
             "content": reply
            }
        )

        await update.message.reply_text(reply, parse_mode="Markdown")

    except Exception as e:
        print("Ошибка:", e)
        await update.message.reply_text("⚠️ Ошибка при обращении к ChatGPT.")


async def handle_edit_mode(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        user_id: int
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
                    original_image,
                    user_message
                    )
                # Сохраняем изображение во временный файл
                file_path = await save_image_from_data(
                    edited_image_data,
                    f"edited_{user_id}"
                    )
                # Отправляем отредактированное изображение
                with open(file_path, "rb") as photo:
                    await update.message.reply_photo(
                        photo,
                        caption=f"Отредактировано по запросу: {user_message}"
                        )
                # Удаляем временный файл
                os.remove(file_path)
                # Сбрасываем состояние редактирования
                user_edit_data[user_id] = {
                    "step": "waiting_image",
                    "original_image": None
                }
            except Exception as e:
                await update.message.reply_text(f"⚠️ {str(e)}")
                # Сбрасываем состояние при ошибке
                user_edit_data[user_id] = {
                    "step": "waiting_image",
                    "original_image": None
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
                    "content": "Контекст очищен. Начните новый разговор."
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
        await update.message.reply_text(
            "ℹ️ Сначала выберите режим работы."
            )


def main():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    # Обработчики команд
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ai", ai_command))
    app.add_handler(CommandHandler("ai_internet", ai_internet_command))
    app.add_handler(CommandHandler("ai_image", ai_image_command))
    app.add_handler(CommandHandler("ai_edit", ai_edit_command))
    app.add_handler(CommandHandler("clear", clear_context))

    # Обрабатываем и текст, и голосовые сообщения
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, handle_message_or_voice
    ))
    app.add_handler(MessageHandler(
        filters.VOICE, handle_message_or_voice
    ))
    app.add_handler(MessageHandler(
        filters.PHOTO, handle_message_or_voice
    ))

    print("✅ Мульти-режимный бот запущен!")
    print("Режимы: /ai (OpenAI), /ai_internet, "
          "/ai_image (DALL-E), /ai_edit (Gemini)")
    app.run_polling()


if __name__ == "__main__":
    main()
