"""
Global variables module for the entire project
"""
import os
from dotenv import load_dotenv

# Global variables that need to be accessible across the entire project
user_contexts = {}  # Хранилище контекста для каждого пользователя и режима
user_modes = {}  # Хранит текущий режим для каждого пользователя
user_edit_data = {}  # Хранит данные для редактирования изображений
user_file_data = {}  # Хранит данные для анализа файлов
MAX_CONTEXT_MESSAGES = 5

# Загрузить переменные из файла .env
load_dotenv()

# Получаем токены для разных режимов
OPENAI_API_KEY_CHAT = os.getenv("OPENAI_API_KEY")
OPENAI_API_KEY_IMAGE = os.getenv("OPENAI_API_KEY_IMAGE")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Модели для разных режимов
MODELS = {
    "chat": "gpt-5.2-chat-latest",
    "image": "dall-e-3",
    "edit": "models/gemini-2.5-flash-image",
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
