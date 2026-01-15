"""Configuration for AI models used by the bot."""

import os
import io
from dotenv import load_dotenv

from google import genai
from openai import OpenAI

import base64

import token_utils

# Загрузить переменные из файла .env
load_dotenv()

# Получаем токены для разных режимов
OPENAI_API_KEY_CHAT = os.getenv("OPENAI_API_KEY")
OPENAI_API_KEY_IMAGE = os.getenv("OPENAI_API_KEY_IMAGE")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Инициализация клиентов OpenAI для разных режимов
client_chat = OpenAI(api_key=OPENAI_API_KEY_CHAT)
client_image = OpenAI(api_key=OPENAI_API_KEY_IMAGE)
# Инициализация клиента Gemini
client_edit_image = genai.Client(api_key=GEMINI_API_KEY)

# Модели для разных режимов
MODELS = {
    "chat": "gpt-5.2-chat-latest",
    "image": "dall-e-3",
    "edit": "gemini-2.5-flash-image",
    "ai_file": "gpt-5.2-chat-latest",
}

SYSTEM_PROMPTS = {
    "chat": (
        "You are a helpful assistant. "
        "Use web search only when your knowledge may be outdated "
        "or when the user explicitly asks for fresh data."
    ),
    "image": ("Ты помогаешь генерировать изображения."),
    "edit": ("Ты помогаешь редактировать изображения с помощью Gemini."),
    "ai_file": (
        "Ты помощник по анализу документов."
        "Отвечай на вопросы касательно "
        "содержимого предоставленного файла."
    ),
}
# Cost per message
COST_PER_MESSAGE = {
    "chat": 2,
    "ai_file": 3,
    "image": 5,
    "edit": 6,
}


async def get_gemini_models_info() -> str:
    """
    Возвращает информацию о доступных моделях Gemini в виде строки.
    """

    try:
        models = client_edit_image.models.list()
        lines = ["🤖 Доступные модели Gemini:\n"]

        for model in models:
            # Имя модели теперь в атрибуте 'name'
            model_id = model.name.split("/")[-1]
            input_tokens = model.input_token_limit
            output_tokens = model.output_token_limit

            # Новый атрибут 'supported_actions' вместо
            # 'supported_generation_methods'
            methods = ", ".join(model.supported_actions)

            # Температура может быть не у всех моделей
            temp = (
                f"{model.temperature:.1f}"
                if hasattr(model, "temperature")
                and model.temperature is not None
                else "не задана"
            )

            lines.append(
                f"🔹 *{model_id}*\n"
                f" Вход: {input_tokens} токенов\n"
                f" Выход: {output_tokens} токенов\n"
                f" Методы: {methods}\n"
                f" Температура: {temp}\n"
            )

        return "\n".join(lines)
    except Exception as e:
        return f"❌ Ошибка при получении моделей Gemini: {str(e)}"


async def get_openai_models_info() -> str:
    try:
        # УБИРАЕМ await — вызов синхронный!
        models = client_image.models.list()
        lines = ["🤖 Доступные модели OpenAI:\n"]
        for model in models:
            lines.append(f"🔹 `{model.id}`")
        return "\n".join(lines)
    except Exception as e:
        return f"❌ Ошибка: `{e}`"


async def ask_gpt51_with_web_search(
    context_history: list,
    enable_web_search: bool = True,
) -> str:
    """
    Задать вопрос GPT-5.2 с опциональным интернет-поиском.

    :param context_history: История сообщений в формате:
        [
            {"role": "system", "content": "Ты полезный ассистент"},
            {"role": "user", "content": "Вопрос"}
        ]
    :param enable_web_search: Разрешить ли web search
    :return: Текст ответа модели
    """

    if not context_history:
        raise ValueError("context_history не должен быть пустым")

    # Инструменты подключаем только если разрешён поиск
    tools = []
    if enable_web_search:
        tools.append(
            {
                "type": "web_search",
            }
        )
    try:
        response = client_chat.responses.create(
            model=MODELS["chat"],
            input=context_history,
            tools=tools,
            timeout=60,
        )

        # Самый простой и безопасный способ получить текст
        return response.output_text.strip()

    except Exception as e:
        print("Ошибка при запросе к GPT:", e)
        raise


async def generate_image(prompt: str) -> str:
    """Генерирует изображение с помощью DALL-E"""
    model_name = MODELS["image"]  # Используем константу
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
            model=model_name,
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
    model_name = MODELS["edit"]  # Используем константу
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
        image_bytes = original_image.read()
        image_base64 = base64.b64encode(image_bytes).decode('utf-8')
        # Подготавливаем промпт для Gemini
        gemini_prompt = f"""
        Оригинальное изображение: {image_base64[:100]}...
        Проанализируй это изображение и выполни следующие изменения: {prompt}
        Важные инструкции:
        1. Внеси именно те изменения, которые запрошены пользователем
        2. Сохрани общий стиль и качество изображения
        3. Если запрос неясен, уточни у пользователя
        4. Верни только измененное изображение без дополнительного текста
        """
        # Отправляем изображение и промпт в Gemini
        response = client_edit_image.models.generate_content(
            model=model_name,
            contents=[gemini_prompt],
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
            f"Ошибка редактирования изображения: {str(e)}"
        )


async def transcribe_voice(file_path: str) -> str:
    """Преобразует голосовое сообщение в текст с помощью Whisper API."""
    with open(file_path, "rb") as audio_file:
        transcription = client_chat.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
        )
    return transcription.text
