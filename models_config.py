"""Configuration for AI models used by the bot."""
import os
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
    "file_analysis": "gpt-5.1",
}

# Cost per message
COST_PER_MESSAGE = {
    "chat": 2,
    "image": 5,
    "edit": 6,
    "file_analysis": 3,
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
