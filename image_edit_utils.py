from global_state import (
    GEMINI_API_KEY,
    MODELS,
)

import base64
import io
import cv2
import numpy as np
from PIL import Image
from typing import Optional, Literal
from google.genai import Client

# Rembg (если установлен)
try:
    from rembg import remove

    REMBG_AVAILABLE = True
except ImportError:
    REMBG_AVAILABLE = False


class AsyncGeminiImageProcessor:
    """
    Универсальный асинхронный процессор для работы с Gemini:
    - text2image
    - image2image
    - inpainting
    - outpainting
    - style transfer
    - автоматическое создание масок: Canny / GrabCut / Rembg
    - автоматический ресайз
    """

    def __init__(
        self,
        api_key: str = GEMINI_API_KEY,
        max_size: int = 512,
    ):
        """
        :param api_key: ключ Gemini
        :param max_size: максимальный размер длинной стороны изображения
        """
        self.client = Client(api_key=api_key)
        self.max_size = max_size
        self.model_name = MODELS["edit"]

    # ----------------------------------------------------------------------
    # УТИЛИТЫ
    # ----------------------------------------------------------------------

    def _resize_if_needed(self, image: Image.Image) -> Image.Image:
        w, h = image.size
        max_dim = max(w, h)

        if max_dim <= self.max_size:
            return image

        scale = self.max_size / max_dim
        new_w = int(w * scale)
        new_h = int(h * scale)
        return image.resize((new_w, new_h), Image.LANCZOS)

    def _pil_to_bytes(self, img: Image.Image) -> bytes:
        buf = io.BytesIO()
        # Используем JPEG с качеством 85 для уменьшения размера файла
        # PNG может быть слишком большим для API
        img.save(buf, format="JPEG", quality=85, optimize=True)
        return buf.getvalue()

    def _bytes_to_pil(self, data: bytes) -> Image.Image:
        return Image.open(io.BytesIO(data)).convert("RGBA")

    def _pil_to_base64(self, img: Image.Image) -> str:
        """Конвертирует PIL Image в base64 строку"""
        buf = io.BytesIO()
        # Используем JPEG с качеством 85 для уменьшения размера файла
        img.save(buf, format="JPEG", quality=85, optimize=True)
        img_bytes = buf.getvalue()
        return base64.b64encode(img_bytes).decode("utf-8")

    # ----------------------------------------------------------------------
    # МАСКИ
    # ----------------------------------------------------------------------

    def make_mask_canny(
        self, image: Image.Image, threshold1=100, threshold2=200
    ) -> bytes:
        # Уменьшаем изображение перед созданием маски для экономии токенов
        resized_image = self._resize_if_needed(image)
        img = np.array(resized_image.convert("RGB"))
        edges = cv2.Canny(img, threshold1, threshold2)
        mask = Image.fromarray(edges).convert("L")

        # Уменьшаем маску до размеров исходного изображения
        mask = mask.resize(image.size, Image.LANCZOS)
        buf = io.BytesIO()
        # Используем более низкое качество для маски, 
        # так как важна только форма
        mask.save(buf, format="JPEG", quality=50, optimize=True)
        return buf.getvalue()

    def make_mask_grabcut(self, image: Image.Image) -> bytes:
        # Уменьшаем изображение перед созданием маски для экономии токенов
        resized_image = self._resize_if_needed(image)
        img = np.array(resized_image.convert("RGB"))
        mask = np.zeros(img.shape[:2], np.uint8)
        bgm = np.zeros((1, 65), np.float64)
        fgm = np.zeros((1, 65), np.float64)

        h, w = img.shape[:2]
        rect = (10, 10, w - 20, h - 20)

        cv2.grabCut(img, mask, rect, bgm, fgm, 5, cv2.GC_INIT_WITH_RECT)

        mask2 = np.where(
            (mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD),
            255,
            0,
        ).astype("uint8")

        # Уменьшаем маску до размеров исходного изображения
        mask_img = Image.fromarray(mask2, mode="L")
        mask_img = mask_img.resize(image.size, Image.LANCZOS)
        buf = io.BytesIO()
        # Используем более низкое качество для маски,
        # так как важна только форма
        mask_img.save(buf, format="JPEG", quality=50, optimize=True)
        return buf.getvalue()

    def make_mask_rembg(self, image: Image.Image) -> Optional[bytes]:
        if not REMBG_AVAILABLE:
            return None

        # Уменьшаем изображение перед обработкой для экономии токенов
        resized_image = self._resize_if_needed(image)
        result = remove(self._pil_to_bytes(resized_image))
        mask_img = Image.open(io.BytesIO(result)).convert("L")

        # Уменьшаем маску до размеров исходного изображения
        mask_img = mask_img.resize(image.size, Image.LANCZOS)
        buf = io.BytesIO()
        # Используем более низкое качество для маски,
        # так как важна только форма
        mask_img.save(buf, format="JPEG", quality=50, optimize=True)
        return buf.getvalue()

    def auto_mask(
        self,
        image: Image.Image,
        mode: Literal["canny", "grabcut", "rembg"] = "canny",
    ) -> bytes:
        if mode == "canny":
            return self.make_mask_canny(image)
        elif mode == "grabcut":
            return self.make_mask_grabcut(image)
        elif mode == "rembg":
            m = self.make_mask_rembg(image)
            if m is None:
                return self.make_mask_grabcut(image)
            return m
        else:
            raise ValueError("Unknown mask mode")

    # ----------------------------------------------------------------------
    # GEMINI: ОСНОВНЫЕ РЕЖИМЫ
    # ----------------------------------------------------------------------

    async def text2image(self, prompt: str) -> Image.Image:
        """Генерация изображения из текста"""
        response = await self.client.aio.models.generate_content(
            model=self.model_name,
            contents=[prompt],
        )
        return self._process_response(response)

    async def image2image(
        self,
        prompt: str,
        image: Image.Image,
    ) -> Image.Image:
        """Редактирование изображения (image2image)"""
        # Убедимся, что изображение уменьшено до приемлемого размера
        image = self._resize_if_needed(image)
        image_base64 = self._pil_to_base64(image)

        contents = [
            f"Изображение: {image_base64}",
            f"Измени это изображение согласно запросу: {prompt}",
        ]

        response = await self.client.aio.models.generate_content(
            model=self.model_name,
            contents=contents,
        )
        return self._process_response(response)

    async def inpainting(
        self,
        prompt: str,
        image: Image.Image,
        mask: Optional[Image.Image] = None,
        auto_mask_mode: Optional[str] = None,
    ) -> Image.Image:
        """Инпеинтинг - редактирование с маской"""
        # Убедимся, что изображение уменьшено до приемлемого размера
        image = self._resize_if_needed(image)
        image_base64 = self._pil_to_base64(image)

        if mask:
            # Убедимся, что маска соответствует размеру изображения
            if mask.size != image.size:
                mask = mask.resize(image.size, Image.LANCZOS)
            buf = io.BytesIO()
            # Используем более низкое качество для маски,
            #  так как важна только форма
            mask.save(buf, format="JPEG", quality=50, optimize=True)
            mask_bytes = buf.getvalue()
        else:
            mask_bytes = self.auto_mask(
                image, mode=auto_mask_mode or "grabcut"
            )
        mask_base64 = base64.b64encode(mask_bytes).decode("utf-8")

        contents = [
            f"Изображение: {image_base64}",
            f"Маска: {mask_base64}",
            f"Измени область внутри маски согласно запросу: {prompt}",
        ]

        response = await self.client.aio.models.generate_content(
            model=self.model_name,
            contents=contents,
        )
        return self._process_response(response)

    async def outpainting(
        self,
        prompt: str,
        image: Image.Image,
    ) -> Image.Image:
        """Аутпеинтинг - расширение изображения"""
        # Убедимся, что изображение уменьшено до приемлемого размера
        image = self._resize_if_needed(image)
        image_base64 = self._pil_to_base64(image)

        contents = [
            f"Изображение: {image_base64}",
            f"Расширь или дополни изображение согласно запросу: {prompt}",
        ]

        response = await self.client.aio.models.generate_content(
            model=self.model_name,
            contents=contents,
        )
        return self._process_response(response)

    async def style_transfer(
        self,
        content_image: Image.Image,
        style_image: Image.Image,
    ) -> Image.Image:
        """Перенос стиля"""
        # Убедимся, что изображения уменьшены до приемлемого размера
        content_image = self._resize_if_needed(content_image)
        style_image = self._resize_if_needed(style_image)

        content_base64 = self._pil_to_base64(content_image)
        style_base64 = self._pil_to_base64(style_image)

        contents = [
            f"Контент: {content_base64}",
            f"Стиль: {style_base64}",
            "Примени стиль второго изображения к первому",
        ]

        response = await self.client.aio.models.generate_content(
            model=self.model_name,
            contents=contents,
        )
        return self._process_response(response)

    def _process_response(self, response) -> Image.Image:
        """Обрабатывает ответ от Gemini и возвращает PIL Image"""
        # Проверяем, содержит ли ответ изображение
        if hasattr(response, "candidates") and response.candidates:
            for part in response.candidates[0].content.parts:
                if hasattr(part, "inline_data"):
                    # Возвращаем данные изображения
                    return self._bytes_to_pil(part.inline_data.data)
                elif hasattr(part, "text"):
                    # Если Gemini вернул текст вместо изображения
                    raise Exception(f"ИИ вернул текстовый ответ: {part.text}")

        # Прямая проверка на inline_data
        if hasattr(response, "inline_data") and response.inline_data:
            return self._bytes_to_pil(response.inline_data.data)

        raise Exception("Gemini не вернул изображение в ответе")
