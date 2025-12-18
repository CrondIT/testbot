"""Configuration for AI models used by the bot."""

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
