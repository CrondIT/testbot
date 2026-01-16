from global_state import (
    GEMINI_API_KEY,
    MODELS,
)

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

# GrabCut нужен только из OpenCV
# cv2.grabCut уже импортирован


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
        max_size: int = 2048,
    ):
        """
        :param api_key: ключ Gemini
        :param max_size: максимальный размер длинной стороны изображения
        """
        self.client = Client(api_key=api_key)
        self.max_size = max_size

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
        img.save(buf, format="PNG")
        return buf.getvalue()

    def _bytes_to_pil(self, data: bytes) -> Image.Image:
        return Image.open(io.BytesIO(data)).convert("RGBA")

    # ----------------------------------------------------------------------
    # МАСКИ
    # ----------------------------------------------------------------------

    def make_mask_canny(
        self, image: Image.Image, threshold1=100, threshold2=200
    ) -> bytes:
        img = np.array(image.convert("RGB"))
        edges = cv2.Canny(img, threshold1, threshold2)
        mask = Image.fromarray(edges).convert("L")
        return self._pil_to_bytes(mask)

    def make_mask_grabcut(self, image: Image.Image) -> bytes:
        img = np.array(image.convert("RGB"))
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

        mask_img = Image.fromarray(mask2, mode="L")
        return self._pil_to_bytes(mask_img)

    def make_mask_rembg(self, image: Image.Image) -> Optional[bytes]:
        if not REMBG_AVAILABLE:
            return None

        result = remove(self._pil_to_bytes(image))
        mask_img = Image.open(io.BytesIO(result)).convert("L")
        return self._pil_to_bytes(mask_img)

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
        response = await self.client.images.generate_async(
            model=MODELS["edit"],
            prompt=prompt,
        )
        img_bytes = response.images[0].image_bytes
        return self._bytes_to_pil(img_bytes)

    async def image2image(
        self,
        prompt: str,
        image: Image.Image,
    ) -> Image.Image:
        image = self._resize_if_needed(image)
        img_bytes = self._pil_to_bytes(image)

        response = await self.client.images.edits_async(
            model=MODELS["edit"],
            image=img_bytes,
            prompt=prompt,
        )
        img_bytes = response.images[0].image_bytes
        return self._bytes_to_pil(img_bytes)

    async def inpainting(
        self,
        prompt: str,
        image: Image.Image,
        mask: Optional[Image.Image] = None,
        auto_mask_mode: Optional[str] = None,
    ) -> Image.Image:

        image = self._resize_if_needed(image)
        img_bytes = self._pil_to_bytes(image)

        if mask:
            mask_bytes = self._pil_to_bytes(mask)
        else:
            mask_bytes = self.auto_mask(
                image, mode=auto_mask_mode or "grabcut"
            )

        response = await self.client.images.edits_async(
            model=MODELS["edit"],
            image=img_bytes,
            mask=mask_bytes,
            prompt=prompt,
        )
        img_bytes = response.images[0].image_bytes
        return self._bytes_to_pil(img_bytes)

    async def outpainting(
        self,
        prompt: str,
        image: Image.Image,
    ) -> Image.Image:
        image = self._resize_if_needed(image)
        img_bytes = self._pil_to_bytes(image)

        response = await self.client.images.edits_async(
            model=MODELS["edit"],
            image=img_bytes,
            prompt=prompt,
        )
        img_bytes = response.images[0].image_bytes
        return self._bytes_to_pil(img_bytes)

    async def style_transfer(
        self,
        content_image: Image.Image,
        style_image: Image.Image,
    ) -> Image.Image:
        content_image = self._resize_if_needed(content_image)
        style_image = self._resize_if_needed(style_image)

        content_bytes = self._pil_to_bytes(content_image)
        style_bytes = self._pil_to_bytes(style_image)

        response = await self.client.images.edits_async(
            model=MODELS["edit"],
            image=content_bytes,
            reference_image=style_bytes,
        )
        img_bytes = response.images[0].image_bytes
        return self._bytes_to_pil(img_bytes)
