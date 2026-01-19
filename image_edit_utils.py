import google.generativeai as genai
from PIL import Image, ImageDraw, ImageFilter, ImageEnhance
import io
import asyncio

# Импортируем настройки
from global_state import MODELS, GEMINI_API_KEY


class AsyncImageEditor:
    def __init__(self):
        """
        Инициализация клиента Google Generative AI
        с использованием ключа из global_state.
        """
        genai.configure(api_key=GEMINI_API_KEY)
        self.model_name = MODELS["edit"]
        self.model = genai.GenerativeModel(self.model_name)

    async def edit_image(self, image_bytes: bytes, prompt: str) -> bytes:
        """
        Асинхронное редактирование изображения.
        Использует возможности модели Gemini для понимания промпта
        и PIL для выполнения базовых операций редактирования.

        Args:
            image_bytes (bytes): Исходное изображение в байтах.
            prompt (str): Текстовое описание того, что нужно изменить.

        Returns:
            bytes: Отредактированное изображение в байтах.
        """
        try:
            # Конвертируем байты изображения в объект PIL.Image
            image = Image.open(io.BytesIO(image_bytes))

            # Анализируем промпт с помощью Gemini, чтобы определить,
            # какие изменения нужно внести
            analysis_prompt = f"""
            Analyze this image editing request: '{prompt}'
            Respond with a structured format indicating the type of edit requested.
            Possible edit types: 'brightness', 'contrast', 'saturation', 'blur', 'sharpen',
            'crop', 'resize', 'add_text', 'remove_object', 'color_change', 'other'.
            Respond in the format: EDIT_TYPE: [type]
            """

            # Выполняем анализ промпта (синхронно, так как асинхронный вызов может быть сложным)
            response = self.model.generate_content(analysis_prompt)
            edit_analysis = response.text.lower()

            # Определяем тип редактирования на основе анализа
            if (
                "brightness" in edit_analysis
                or "light" in edit_analysis
                or "bright" in edit_analysis
            ):
                # Изменяем яркость
                enhancer = ImageEnhance.Brightness(image)
                image = enhancer.enhance(1.2)  # Увеличиваем яркость на 20%
            elif "contrast" in edit_analysis:
                # Изменяем контраст
                enhancer = ImageEnhance.Contrast(image)
                image = enhancer.enhance(1.2)  # Увеличиваем контраст на 20%
            elif "saturation" in edit_analysis or "color" in edit_analysis:
                # Изменяем насыщенность
                enhancer = ImageEnhance.Color(image)
                image = enhancer.enhance(
                    1.2
                )  # Увеличиваем насыщенность на 20%
            elif "blur" in edit_analysis:
                # Размываем изображение
                image = image.filter(ImageFilter.GaussianBlur(radius=2))
            elif "sharpen" in edit_analysis:
                # Повышаем резкость
                image = image.filter(ImageFilter.SHARPEN)
            elif "rotate" in edit_analysis:
                # Поворачиваем изображение
                image = image.rotate(90, expand=True)
            # Можно добавить больше типов редактирования по мере необходимости

            # Конвертируем обратно в байты
            output_buffer = io.BytesIO()
            image.save(output_buffer, format="JPEG", quality=95)
            output_buffer.seek(0)
            edited_image_bytes = output_buffer.getvalue()

            return edited_image_bytes

        except Exception as e:
            print(f"Ошибка в AsyncImageEditor: {e}")
            # В случае ошибки с API Gemini, возвращаем исходное изображение
            # или применяем базовые эвристики к промпту
            return self.apply_basic_editing(image_bytes, prompt)

    def apply_basic_editing(self, image_bytes: bytes, prompt: str) -> bytes:
        """
        Применяет базовое редактирование изображения на основе эвристик из промпта
        """
        try:
            image = Image.open(io.BytesIO(image_bytes))

            prompt_lower = prompt.lower()

            # Применяем базовые изменения в зависимости от ключевых слов в промпте
            if any(
                word in prompt_lower for word in ["light", "bright", "lighten"]
            ):
                enhancer = ImageEnhance.Brightness(image)
                image = enhancer.enhance(1.3)
            elif any(word in prompt_lower for word in ["dark", "darken"]):
                enhancer = ImageEnhance.Brightness(image)
                image = enhancer.enhance(0.7)

            if any(word in prompt_lower for word in ["contrast", "contrasty"]):
                enhancer = ImageEnhance.Contrast(image)
                image = enhancer.enhance(1.3)

            if any(
                word in prompt_lower
                for word in ["saturation", "saturated", "colorful"]
            ):
                enhancer = ImageEnhance.Color(image)
                image = enhancer.enhance(1.3)

            if any(word in prompt_lower for word in ["blur", "soften"]):
                image = image.filter(ImageFilter.GaussianBlur(radius=2))

            if any(word in prompt_lower for word in ["sharp", "sharpen"]):
                image = image.filter(ImageFilter.SHARPEN)

            # Конвертируем обратно в байты
            output_buffer = io.BytesIO()
            image.save(output_buffer, format="JPEG", quality=95)
            output_buffer.seek(0)
            edited_image_bytes = output_buffer.getvalue()

            return edited_image_bytes
        except Exception as e:
            print(f"Ошибка в apply_basic_editing: {e}")
            # В случае ошибки возвращаем исходное изображение
            return image_bytes
