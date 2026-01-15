"""Utility functions for creating and handling DOCX files."""

import re
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Mm
from docx.oxml.shared import OxmlElement, qn
import io
import json
from telegram import InputFile
from telegram.helpers import escape_markdown
import matplotlib
import matplotlib.pyplot as plt

# Константы для формата страницы и полей (в миллиметрах)
DEFAULT_PAGE_WIDTH_MM = 210  # Ширина A4 в мм
DEFAULT_PAGE_HEIGHT_MM = 297  # Высота A4 в мм
DEFAULT_LEFT_MARGIN_MM = 20  # Левое поле по умолчанию
DEFAULT_RIGHT_MARGIN_MM = 10  # Правое поле по умолчанию
DEFAULT_TOP_MARGIN_MM = 15  # Верхнее поле по умолчанию
DEFAULT_BOTTOM_MARGIN_MM = 15  # Нижнее поле по умолчанию


def clean_html_tags(text):
    """
    Очищает текст от HTML-тегов и других форматирований,
    не поддерживаемых в python-docx.

    Args:
        text (str): Текст для очистки

    Returns:
        str: Очищенный текст
    """
    if not isinstance(text, str):
        return str(text)

    # Удаляем span теги и их атрибуты
    text = re.sub(r"<span[^>]*>", "", text)
    text = re.sub(r"</span>", "", text)

    # Удаляем другие теги
    text = re.sub(r"<[^>]+>", "", text)

    # Удаляем двойные звездочки (жирный текст в markdown)
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)

    # Удаляем одинарные звездочки (курсив в markdown)
    text = re.sub(r"(?<!\*)\*([^\*]+?)\*(?!\*)", r"\1", text)

    # Удаляем подчеркивания (курсив в markdown)
    text = re.sub(r"(?<!_)_([^_]+?)_(?!_)", r"\1", text)

    return text.strip()


matplotlib.use("Agg")  # Use non-interactive backend

JSON_SCHEMA = """
    Верни ТОЛЬКО валидный JSON без пояснений.
    Не используй markdown, только JSON.
    Не включай тройные кавычки в значениях.
    Строгая схема:
    {
    "meta": {"title": "string"},
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
           }
        },
        {"type":"math", "formula":"LaTeX formula",
        "caption":"optional caption", "font_name":"string",
        "font_size":12, "math_font_size":12, "caption_font_size":10,
        "bold":false, "italic":true, "alignment":"left", "color":"string"}
    ]
    }
    """


class DocxRenderer:
    def __init__(self):
        self.doc = Document()
        # Установка полей страницы по умолчанию
        section = self.doc.sections[0]
        section.page_width = Mm(DEFAULT_PAGE_WIDTH_MM)
        section.page_height = Mm(DEFAULT_PAGE_HEIGHT_MM)
        section.left_margin = Mm(DEFAULT_LEFT_MARGIN_MM)
        section.right_margin = Mm(DEFAULT_RIGHT_MARGIN_MM)
        section.top_margin = Mm(DEFAULT_TOP_MARGIN_MM)
        section.bottom_margin = Mm(DEFAULT_BOTTOM_MARGIN_MM)

    def render(self, data: dict, output):
        """
        Рендерим JSON документ в DOCX.
        :param data: dict с ключами "meta" и "blocks"
        :param output: path или BytesIO
        """
        self._render_meta(data.get("meta", {}))

        for block in data.get("blocks", []):
            self._render_block(block)

        # Сохраняем в файл или BytesIO
        self.doc.save(output)

    def _render_meta(self, meta: dict):
        if "title" in meta:
            title = self.doc.add_heading(meta["title"], level=1)
            title.alignment = WD_ALIGN_PARAGRAPH.CENTER

    def _render_block(self, block: dict):
        block_type = block.get("type")

        if block_type == "heading":
            self._heading(block)
        elif block_type == "paragraph":
            self._paragraph(block)
        elif block_type == "list":
            self._list(block)
        elif block_type == "table":
            self._table(block)
        elif block_type == "math":
            self._math(block)
        else:
            raise ValueError(f"Unknown block type: {block_type}")

    def _heading(self, block: dict):
        level = block.get("level", 1)
        text = block.get("text", "")
        # Используем параметры из JSON, если они есть, иначе - стандартные
        font_name = block.get("font_name", None)
        font_size = block.get("font_size", None)
        bold = block.get("bold", None)
        italic = block.get("italic", None)
        color = block.get("color", None)

        heading = self.doc.add_heading(text, level=level)

        # Применяем стили, если они указаны в JSON
        if font_name or font_size or bold is not None or italic is not None:
            run = heading.runs[0] if heading.runs else heading.add_run(text)
            if font_name:
                run.font.name = font_name
            if font_size:
                from docx.shared import Pt

                run.font.size = Pt(font_size)
            if bold is not None:
                run.font.bold = bold
            if italic is not None:
                run.font.italic = italic
            if color:
                # Для цвета нужно импортировать RGBColor
                from docx.shared import RGBColor

                # Предполагаем, что цвет в формате "RRGGBB" или "RGB"
                if len(color) == 6:
                    r = int(color[0:2], 16)
                    g = int(color[2:4], 16)
                    b = int(color[4:6], 16)
                    run.font.color.rgb = RGBColor(r, g, b)

    def _paragraph(self, block: dict):
        # Используем параметры из JSON, если они есть, иначе - стандартные
        text = clean_html_tags(block.get("text", ""))
        font_name = block.get("font_name", None)
        font_size = block.get("font_size", None)
        left_indent = block.get("left_indent", None)
        right_indent = block.get("right_indent", None)
        space_after = block.get("space_after", None)
        alignment = block.get("alignment", None)  # left, center, right
        color = block.get("color", None)

        p = self.doc.add_paragraph()
        run = p.add_run(text)

        # Применяем форматирование из JSON
        if block.get("bold"):
            run.bold = True
        if block.get("italic"):
            run.italic = True
        if block.get("underline"):
            run.underline = True
        if font_name:
            run.font.name = font_name
        if font_size:
            from docx.shared import Pt

            run.font.size = Pt(font_size)
        if color:
            from docx.shared import RGBColor

            # Предполагаем, что цвет в формате "RRGGBB" или "RGB"
            if len(color) == 6:
                r = int(color[0:2], 16)
                g = int(color[2:4], 16)
                b = int(color[4:6], 16)
                run.font.color.rgb = RGBColor(r, g, b)

        # Применяем отступы и интервалы
        if (
            left_indent is not None
            or right_indent is not None
            or space_after is not None
        ):
            paragraph_format = p.paragraph_format
            if left_indent is not None:
                from docx.shared import Inches

                paragraph_format.left_indent = Inches(
                    left_indent / 10.0
                )  # Преобразуем в дюймы
            if right_indent is not None:
                from docx.shared import Inches

                paragraph_format.right_indent = Inches(
                    right_indent / 10.0
                )  # Преобразуем в дюймы
            if space_after is not None:
                from docx.shared import Pt

                paragraph_format.space_after = Pt(
                    space_after
                )  # Интервал после абзаца в пунктах

        # Выравнивание
        if alignment == "center":
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        elif alignment == "right":
            p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        elif alignment == "justify":
            p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        # left - по умолчанию

    def _list(self, block: dict):
        # Используем параметры из JSON, если они есть, иначе - стандартные
        ordered = block.get("ordered", False)
        font_name = block.get("font_name", None)
        font_size = block.get("font_size", None)
        left_indent = block.get("left_indent", None)
        right_indent = block.get("right_indent", None)
        space_after = block.get("space_after", None)
        alignment = block.get("alignment", "left")  # left, center, right
        color = block.get("color", None)

        style = "List Number" if ordered else "List Bullet"

        for item in block.get("items", []):
            cleaned_item = clean_html_tags(item)
            p = self.doc.add_paragraph(cleaned_item, style=style)

            # Применяем стили, если они указаны в JSON
            if p.runs:
                run = p.runs[0]
                if font_name:
                    run.font.name = font_name
                if font_size:
                    from docx.shared import Pt

                    run.font.size = Pt(font_size)
                if color:
                    from docx.shared import RGBColor

                    # Предполагаем, что цвет в формате "RRGGBB" или "RGB"
                    if len(color) == 6:
                        r = int(color[0:2], 16)
                        g = int(color[2:4], 16)
                        b = int(color[4:6], 16)
                        run.font.color.rgb = RGBColor(r, g, b)

            # Применяем отступы и интервалы
            if (
                left_indent is not None
                or right_indent is not None
                or space_after is not None
            ):
                paragraph_format = p.paragraph_format
                if left_indent is not None:
                    from docx.shared import Inches

                    paragraph_format.left_indent = Inches(
                        left_indent / 10.0
                    )  # Преобразуем в дюймы
                if right_indent is not None:
                    from docx.shared import Inches

                    paragraph_format.right_indent = Inches(
                        right_indent / 10.0
                    )  # Преобразуем в дюймы
                if space_after is not None:
                    from docx.shared import Pt

                    paragraph_format.space_after = Pt(
                        space_after
                    )  # Интервал после абзаца в пунктах

            # Выравнивание
            if alignment == "center":
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            elif alignment == "right":
                p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            elif alignment == "justify":
                p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

    def _table(self, block: dict):
        """
        Рендерим таблицу.
        JSON-схема:
        {
            "type": "table",
            "headers": ["Колонка1", "Колонка2"],
            "rows": [
                ["Значение1", "Значение2"]
            ]
        }
        """
        headers = block.get("headers", [])
        rows = block.get("rows", [])

        # Используем параметры из JSON, если они есть, иначе - стандартные
        table_params = block.get("params", {})
        header_font_name = table_params.get("header_font_name", None)
        header_font_size = table_params.get("header_font_size", None)
        header_bold = table_params.get(
            "header_bold", True
        )  # по умолчанию заголовки жирные
        header_italic = table_params.get("header_italic", False)
        header_color = table_params.get("header_color", None)
        body_font_name = table_params.get("body_font_name", None)
        body_font_size = table_params.get("body_font_size", None)
        body_bold = table_params.get("body_bold", False)
        body_italic = table_params.get("body_italic", False)
        body_color = table_params.get("body_color", None)
        table_style = table_params.get("table_style", "Table Grid")
        header_bg_color = table_params.get("header_bg_color", None)

        if not headers or not rows:
            return  # Пустая таблица — ничего не делаем

        table = self.doc.add_table(rows=1, cols=len(headers))
        table.style = table_style  # стиль таблицы из JSON
        # Заголовки
        hdr_cells = table.rows[0].cells
        for i, header in enumerate(headers):
            cleaned_header = clean_html_tags(str(header))
            hdr_cells[i].text = cleaned_header

            # Применяем стили к заголовкам
            if (
                header_font_name
                or header_font_size
                or header_bold
                or header_italic
                or header_color
            ):
                run = (
                    hdr_cells[i].paragraphs[0].runs[0]
                    if hdr_cells[i].paragraphs
                    and hdr_cells[i].paragraphs[0].runs
                    else hdr_cells[i].paragraphs[0].add_run(cleaned_header)
                )
                if header_font_name:
                    run.font.name = header_font_name
                if header_font_size:
                    from docx.shared import Pt

                    run.font.size = Pt(header_font_size)
                if header_bold is not None:
                    run.font.bold = header_bold
                if header_italic is not None:
                    run.font.italic = header_italic
                if header_color:
                    from docx.shared import RGBColor

                    # Предполагаем, что цвет в формате "RRGGBB" или "RGB"
                    if len(header_color) == 6:
                        r = int(header_color[0:2], 16)
                        g = int(header_color[2:4], 16)
                        b = int(header_color[4:6], 16)
                        run.font.color.rgb = RGBColor(r, g, b)

        # Применяем фоновый цвет к заголовкам, если указан
        if header_bg_color:
            for i, header in enumerate(headers):
                # Получаем XML элемент ячейки
                tc = hdr_cells[i]._tc
                # Создаем элемент заливки
                tcFill = OxmlElement("w:shd")
                tcFill.set(qn("w:fill"), header_bg_color.replace("#", ""))
                # Добавляем заливку к ячейке
                tc.get_or_add_tcPr().append(tcFill)

        # Данные
        for row in rows:
            cells = table.add_row().cells
            for i, value in enumerate(row):
                cleaned_value = clean_html_tags(str(value))
                cells[i].text = cleaned_value

                # Применяем стили к ячейкам данных
                if (
                    body_font_name
                    or body_font_size
                    or body_bold
                    or body_italic
                    or body_color
                ):
                    run = (
                        cells[i].paragraphs[0].runs[0]
                        if cells[i].paragraphs and cells[i].paragraphs[0].runs
                        else cells[i].paragraphs[0].add_run(cleaned_value)
                    )
                    if body_font_name:
                        run.font.name = body_font_name
                    if body_font_size:
                        from docx.shared import Pt

                        run.font.size = Pt(body_font_size)
                    if body_bold is not None:
                        run.font.bold = body_bold
                    if body_italic is not None:
                        run.font.italic = body_italic
                    if body_color:
                        from docx.shared import RGBColor

                        # Предполагаем, что цвет в формате "RRGGBB" или "RGB"
                        if len(body_color) == 6:
                            r = int(body_color[0:2], 16)
                            g = int(body_color[2:4], 16)
                            b = int(body_color[4:6], 16)
                            run.font.color.rgb = RGBColor(r, g, b)

    def _math(self, block: dict):
        """
        Рендерим математическую формулу.
        JSON-схема:
        {
            "type": "math",
            "formula": "LaTeX formula",
            "caption": "optional caption"
        }
        """
        formula = block.get("formula", "")
        caption = block.get("caption", "")

        # Используем параметры из JSON, если они есть, иначе - стандартные
        font_name = block.get("font_name", None)
        font_size = block.get("font_size", None)
        # Используем font_size как fallback,
        # если конкретные параметры не указаны
        math_font_size = block.get("math_font_size", None) or font_size or 12
        caption_font_size = (
            block.get("caption_font_size", None) or font_size or 10
        )
        bold = block.get("bold", False)
        italic = block.get("italic", True)  # По умолчанию курсив для формул
        alignment = block.get("alignment", "left")  # left, center, right
        color = block.get("color", None)

        # Создаем изображение с формулой с помощью matplotlib
        # Это более надежный способ отображения сложных формул в Word
        try:
            # Настройка фигуры matplotlib с размерами,
            # пропорциональными длине формулы
            # Преобразуем размеры из миллиметров в дюймы (1 дюйм = 25.4 мм)
            base_width_mm = 60  # базовая ширина в мм
            width_factor = min(
                len(formula) / 10, 3
            )  # масштабируем в зависимости от длины формулы не более чем х3
            width_mm = base_width_mm * width_factor

            # Высота пропорциональна ширине, но с минимальным значением
            height_mm = max(width_mm * 0.2, 15)  # высота в мм, не менее 15 мм

            # Преобразуем миллиметры в дюймы для matplotlib
            width_inches = width_mm / 25.4
            height_inches = height_mm / 25.4

            fig, ax = plt.subplots(figsize=(width_inches, height_inches))
            ax.text(
                0.5,
                0.5,
                f"${formula}$",
                fontsize=16,
                ha="center",
                va="center",
                transform=ax.transAxes,
            )
            ax.axis("off")  # Скрыть оси

            # Сохраняем в байтовый поток
            img_buffer = io.BytesIO()
            plt.savefig(img_buffer, format="png", bbox_inches="tight", dpi=150)
            img_buffer.seek(0)

            # Добавляем изображение в документ
            paragraph = self.doc.add_paragraph()

            # Применяем выравнивание
            if alignment == "center":
                paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
            elif alignment == "right":
                paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            elif alignment == "justify":
                paragraph.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

            run = paragraph.add_run()

            # Добавляем изображение в документ
            run.add_picture(img_buffer, width=Inches(6))

            # Если есть подпись, добавляем её
            if caption:
                caption_p = self.doc.add_paragraph()

                # Применяем выравнивание к подписи
                if alignment == "center":
                    caption_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                elif alignment == "right":
                    caption_p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
                elif alignment == "justify":
                    caption_p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

                caption_run = caption_p.add_run(f"{caption}")

                # Применяем стили к подписи
                if font_name:
                    caption_run.font.name = font_name
                if caption_font_size:
                    from docx.shared import Pt

                    caption_run.font.size = Pt(caption_font_size)
                if bold:
                    caption_run.font.bold = bold
                if italic:
                    caption_run.font.italic = italic
                if color:
                    from docx.shared import RGBColor

                    # Предполагаем, что цвет в формате "RRGGBB" или "RGB"
                    if len(color) == 6:
                        r = int(color[0:2], 16)
                        g = int(color[2:4], 16)
                        b = int(color[4:6], 16)
                        caption_run.font.color.rgb = RGBColor(r, g, b)

        except Exception as e:
            # Если не удалось создать изображение формулы,
            # добавляем как обычный текст
            p = self.doc.add_paragraph()

            # Применяем выравнивание
            if alignment == "center":
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            elif alignment == "right":
                p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            elif alignment == "justify":
                p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

            run = p.add_run(f"Формула: {formula}")

            # Применяем стили к формуле
            if font_name:
                run.font.name = font_name
            if math_font_size:
                from docx.shared import Pt

                run.font.size = Pt(math_font_size)
            if bold:
                run.font.bold = bold
            if italic:
                run.font.italic = italic
            if color:
                from docx.shared import RGBColor

                # Предполагаем, что цвет в формате "RRGGBB" или "RGB"
                if len(color) == 6:
                    r = int(color[0:2], 16)
                    g = int(color[2:4], 16)
                    b = int(color[4:6], 16)
                    run.font.color.rgb = RGBColor(r, g, b)

            print(f"Ошибка при рендеринге формулы: {e}")

            if caption:
                caption_p = self.doc.add_paragraph()

                # Применяем выравнивание к подписи
                if alignment == "center":
                    caption_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                elif alignment == "right":
                    caption_p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
                elif alignment == "justify":
                    caption_p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

                caption_run = caption_p.add_run(f"({caption})")

                # Применяем стили к подписи
                if font_name:
                    caption_run.font.name = font_name
                if caption_font_size:
                    from docx.shared import Pt

                    caption_run.font.size = Pt(caption_font_size)
                if bold:
                    caption_run.font.bold = bold
                if italic:
                    caption_run.font.italic = italic
                if color:
                    from docx.shared import RGBColor

                    # Предполагаем, что цвет в формате "RRGGBB" или "RGB"
                    if len(color) == 6:
                        r = int(color[0:2], 16)
                        g = int(color[2:4], 16)
                        b = int(color[4:6], 16)
                        caption_run.font.color.rgb = RGBColor(r, g, b)

        finally:
            # Очищаем matplotlib
            plt.close()


def check_user_wants_word_format(user_message):
    """
    Check if user wants to receive description in Word format.

    Args:
        user_message (str): The message from user to analyze

    Returns:
        bool: True if user wants Word format, False otherwise
    """
    message = user_message.lower()
    return (
        "word" in message
        or "формат word" in message
        or "docx" in message
        or "в ворде" in message
        or "в формате документа" in message
        or "word документ" in message
        or "документ word" in message
        or "в microsoft word" in message
        or "в формате ворд" in message
        or "в формате word" in message
        or "в документе word" in message
        or "в word формате" in message
        or "в ворд формате" in message
        or "в вордовском формате" in message
        or "в формате ворда" in message
    )


async def send_docx_response(
    update,
    reply,
    image_url=None,
):
    """
    Отправляет DOCX-файл с ответом пользователю.
    Args:
        update: Объект обновления Telegram
        reply: Ответ от модели, который будет преобразован в DOCX
    """
    try:
        # Проверяем, что reply не пустой
        if not reply or reply.strip() == "":
            raise ValueError("Пустой ответ от модели")

        # Удаляем маркеры кода, если они есть
        cleaned_reply = reply.strip()
        if cleaned_reply.startswith("```json"):
            cleaned_reply = cleaned_reply[7:]  # Удаляем '```json'
        elif cleaned_reply.startswith("```"):
            cleaned_reply = cleaned_reply[3:]  # Удаляем '```'

        if cleaned_reply.endswith("```"):
            cleaned_reply = cleaned_reply[:-3]  # Удаляем закрывающий '```'

        cleaned_reply = cleaned_reply.strip()

        data = json.loads(cleaned_reply)
        doc_io = io.BytesIO()
        renderer = DocxRenderer()
        renderer.render(data, doc_io)
        doc_io.seek(0)

        await update.message.reply_document(
            document=InputFile(doc_io, filename="document.docx"),
            caption="Ваш ответ в формате Word",
        )
        if image_url:
            await update.message.reply_photo(
                image_url,
                caption="Вот что сгенерировано по Вашему запросу",
            )
    except json.JSONDecodeError as e:
        # Если ответ не является валидным JSON,
        # отправляем обычное сообщение
        from message_utils import send_long_message

        safe_reply = escape_markdown(reply, version=2)
        await send_long_message(update, safe_reply, parse_mode="MarkdownV2")
        print(f"Ошибка разбора JSON при создании DOCX: {e}")
    except ValueError as e:
        # Если возникла ошибка значения (например, пустой ответ)
        from message_utils import send_long_message

        safe_reply = escape_markdown(reply, version=2)
        await send_long_message(update, safe_reply, parse_mode="MarkdownV2")
        print(f"Ошибка значения при создании DOCX: {e}")
    except Exception as e:
        # Если не удалось создать или отправить
        # DOCX, отправляем обычное сообщение
        from message_utils import send_long_message

        safe_reply = escape_markdown(reply, version=2)
        await send_long_message(update, safe_reply, parse_mode="MarkdownV2")
        print(f"Ошибка при создании или отправке DOCX файла: {e}")
