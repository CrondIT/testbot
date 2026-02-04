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
user_edit_pending = {}  # Хранит ожидание промпта для редактирования изображ.
user_previous_modes = {}  # Хранит предыдущий режим для каждого пользователя
edited_photo_id = {}  # Хранит ID отредактированного изображения
# Хранит путь к последнему отредактированному
# изображению для каждого пользователя
user_last_edited_images = {}
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
    "image": "gemini-2.5-flash-image",
    "edit": "gemini-2.5-flash-image",
    "ai_file": "gpt-5.2-chat-latest",
}


def get_token_limit(model_name: str) -> int:
    """
    Get the maximum token limit for a specific model
    """
    limits = {
        # OpenAI models
        "gpt-5.2": 128000,
        "gpt-5.1": 128000,
        "gpt-4o-mini": 128000,
        "gpt-4-turbo": 128000,
        "gpt-4o": 128000,
        "gpt-4": 8192,
        "gpt-5.2-chat-latest": 128000,
        # DALL-E models
        "dall-e-3": 4096,  # Prompt length limit
        # Gemini models
        "imagen-4.0-generate-001": 8192,
        "gemini-2.5-pro": 2097152,
        "gemini-2.5-flash-image": 32768,
        "gemini-1.5-pro": 1048576,
        "gemini-1.0-pro": 32768,
    }

    return limits.get(model_name, 4096)  # Default fallback


# Cost per message
COST_PER_MESSAGE = {
    "chat": 2,
    "ai_file": 3,
    "image": 5,
    "edit": 6,
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

RTF_PROMPT = """
    Верни ТОЛЬКО валидныйr rtf без пояснений.
    Не используй markdown, только rtf.
    Не включай тройные кавычки в значениях.
"""


# Shared JSON schema for document generation across formats (DOCX, PDF, etc.)
DOCUMENT_JSON_SCHEMA = """
    Верни ТОЛЬКО валидный JSON без пояснений.
    Не используй markdown, только JSON.
    Не включай тройные кавычки в значениях.
    Строгая схема:
    {
    "meta": {"title": "string", "hide_title": false},
    "header": {
        "content": "string",
        "font_name": "string",
        "font_size": 12,
        "color": "string",
        "bold": false,
        "italic": false,
        "alignment": "left",
        "page_number": {
            "enabled": false,
            "format": "Page {PAGE} of {NUMPAGES}",
            "position": "right"
        }
    },
    "footer": {
        "content": "string",
        "font_name": "string",
        "font_size": 12,
        "color": "string",
        "bold": false,
        "italic": false,
        "alignment": "left",
        "page_number": {
            "enabled": false,
            "format": "Page {PAGE} of {NUMPAGES}",
            "position": "right"
        }
    },
    "blocks": [
        {"type":"heading","level":1,"text":"string", "font_name":"string",
        "font_size":12, "color":"string", "bold":false, "italic":false},
        {"type":"paragraph","text":"string", "font_name":"string",
        "font_size":12, "left_indent":0, "right_indent":0, "space_after":12,
        "alignment":"left", "color":"string", "bold":false, "italic":false,
        "underline":false},
        {"type":"list", "ordered":false, "font_name":"string", "font_size":12,
        "left_indent":0, "right_indent":0, "space_after":12,
        "alignment":"left", "color":"string", "bold":false, "italic":false,
        "items":["item1", "item2"]},
        {"type":"table", "headers":["column1", "column2"],
           "rows":[["value1", "value2"], ["value3", "value4"]],
           "params": {
               "header_font_name":"string",
               "header_font_size":12,
               "header_bold":true,
               "header_italic":false,
               "header_color":"string",
               "body_font_name":"string",
               "body_font_size":12,
               "body_bold":false,
               "body_italic":false,
               "body_color":"string",
               "table_style":"Table Grid",
               "header_bg_color":"string"
           },
           "table_properties": {
               "border": {"style":"single", "size":4, "color":"auto"},
               "cell_margin": {"top": 100, "bottom": 100,
               "left": 100, "right": 100},
               "widths": [2000, 3000]  // Ширина столбцов в TWIP (1/20 пункта)
           },
           "cell_properties": [
               {
                   "row": 0,
                   "col": 0,
                   "bg_color": "#D3D3D3",
                   "text_color": "#000000",
                   "text_wrap": true,
                   "vertical_alignment": "center",
                   "horizontal_alignment": "center",
                   "border": {"top": {"style":"single",
                   "size":4, "color":"auto"}}
               }
           ],
           "row_properties": [
               {
                   "row": 1,
                   "bg_color": "#F0F0F0",
                   "text_color": "#333333"
               }
           ]
        },
        {"type":"math", "formula":"LaTeX formula",
        "caption":"optional caption", "font_name":"string",
        "font_size":12, "math_font_size":12, "caption_font_size":10,
        "bold":false, "italic":true, "alignment":"left", "color":"string"},
        {"type":"function_graph", "function":"mathematical function",
         "x_min":-10, "x_max":10, "title":"Graph Title",
         "xlabel":"x", "ylabel":"y",
         "width":6, "height":4, "line_color":"blue", "line_width":2,
         "show_grid":true, "caption":"optional caption", "alignment":"center"},
        {"type":"toc", "title":"string", "levels":[1,2,3],
         "font_name":"string", "font_size":12, "indent":10,
         "leader_dots":true, "include_pages":true}
    ]
    }
    """
