"""Configuration for AI models used by the bot."""
import os
import io
from dotenv import load_dotenv
import google.generativeai as genai
from openai import OpenAI
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
genai.configure(api_key=GEMINI_API_KEY)

# Модели для разных режимов
MODELS = {
    "chat": "gpt-5.1",
    "image": "dall-e-3",
    "edit": "gemini-2.5-flash-preview-image",
    "ai_file": "gpt-5.1",
}

# Cost per message
COST_PER_MESSAGE = {
    "chat": 2,
    "image": 5,
    "edit": 6,
    "ai_file": 3,
}


async def get_gemini_models_info() -> str:
    """
    Возвращает информацию о доступных моделях Gemini в виде строки.
    """
    try:
        models = genai.list_models()
        lines = ["🤖 Доступные модели Gemini:\n"]
        for model in models:
            model_id = model.name.split("/")[-1]
            input_tokens = model.input_token_limit
            output_tokens = model.output_token_limit
            methods = ", ".join(model.supported_generation_methods)
            temp = (
                f"{model.temperature:.1f}"
                if model.temperature
                else "не задана"
            )

            lines.append(
                f"🔹 *{model_id}*"
                f"\n   Вход: `{input_tokens}` токенов"
                f"\n   Выход: `{output_tokens}` токенов"
                f"\n   Режимы: `{methods}`"
                f"\n   Температура: `{temp}`"
                f"\n"
            )
        return "\n".join(lines)
    except Exception as e:
        return f"❌ Ошибка при получении моделей Gemini: `{str(e)}`"


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


def ask_gpt51_with_web_search(
    query: str, enable_web_search: bool = True
) -> str:
    """
    Задать вопрос GPT-5.1 с опциональным поиском в интернете.

    :param query: Текст вопроса.
    :param enable_web_search:
        Если True — модель может использовать интернет-поиск.
        Если False — только внутренние знания, без поиска.
    :return: Текст ответа от модели.
    """
    # Проверяем длину запроса и ограничиваем его при необходимости
    model_name = "gpt-5.1"
    max_tokens = token_utils.get_token_limit(model_name)
    query_tokens = token_utils.token_counter.count_openai_tokens(
        query, model_name
    )

    if query_tokens > max_tokens:
        # Обрезаем запрос до допустимого размера
        avg_token_size = 4  # средний размер токена в символах
        max_chars = max_tokens * avg_token_size
        query = query[:max_chars]

    # Подготовка инструментов: только если разрешён поиск
    tools = (
        [
            {
                "type": "web_search",
                # Можно расширить: фильтры, язык, регион и т.п.
            }
        ]
        if enable_web_search
        else []
    )

    # Выбор поведения: использовать ли инструменты
    tool_choice = "auto" if enable_web_search else "none"

    response = client_chat.responses.create(
        model="gpt-5.1",  # или "gpt-5.1-thinking"
        tools=tools,
        tool_choice=tool_choice,
        input=query,
        instructions=(
            "You are a helpful assistant. "
            "Use web search only when your knowledge may be outdated "
            "or when the user explicitly asks for fresh data."
        ),
        temperature=0.4,
        # include sources only if web search is enabled
        include=(
            ["web_search_call.action.sources"] if enable_web_search else []
        ),
    )

    return response.output_text


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


async def transcribe_voice(file_path: str) -> str:
    """Преобразует голосовое сообщение в текст с помощью Whisper API."""
    with open(file_path, "rb") as audio_file:
        transcription = client_chat.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
        )
    return transcription.text
