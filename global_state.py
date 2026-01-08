"""
Global variables module for the entire project
"""
# Global variables that need to be accessible across the entire project
user_contexts = {}  # Хранилище контекста для каждого пользователя и режима
user_modes = {}  # Хранит текущий режим для каждого пользователя
user_edit_data = {}  # Хранит данные для редактирования изображений
user_file_data = {}  # Хранит данные для анализа файлов
MAX_CONTEXT_MESSAGES = 5
