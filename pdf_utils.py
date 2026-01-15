"""Utility functions for creating and handling PDF files."""

import re
from reportlab.lib.pagesizes import A4
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import io
import json
from telegram import InputFile
from telegram.helpers import escape_markdown
from message_utils import send_long_message
from reportlab.lib.colors import Color as RLColor
import reportlab.lib.colors as colors_module

# Создаем объект изображения для ReportLab
from reportlab.platypus import Image as RLImage


def parse_color(color_value):
    """
    Универсальная функция для обработки различных форматов цветов

    Args:
        color_value: Значение цвета в одном из поддерживаемых форматов:
                     - строка с именем цвета ('black', 'red', и т.д.)
                     - строка в формате HEX ('#FF0000')
                     - кортеж/список RGB ((255, 0, 0))
                     - объект Color из reportlab

    Returns:
        Объект Color из reportlab
    """
    if isinstance(color_value, RLColor):
        # Если уже объект Color, используем его напрямую
        return color_value
    elif isinstance(color_value, str):
        if color_value.startswith("#"):
            # HEX-формат, например "#FF5733"
            hex_color = color_value.lstrip("#")
            # Проверяем длину HEX-кода (может быть 3 или 6 символов)
            if len(hex_color) == 3:
                # Формат с сокращенным представлением (RGB)
                rgb = tuple(
                    int(hex_color[i], 16) * 17 for i in range(3)
                )  # Умножаем на 17 для расширения 0-F до 0-255
            elif len(hex_color) == 6:
                # Полный формат (RRGGBB)
                rgb = tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
            else:
                raise ValueError(
                    f"Неподдерживаемый формат HEX цвета: {color_value}"
                )
            return RLColor(rgb[0] / 255.0, rgb[1] / 255.0, rgb[2] / 255.0)
        else:
            # Проверяем, является ли это именованным цветом из reportlab
            try:
                color_obj = getattr(colors_module, color_value.lower())
                if not isinstance(color_obj, RLColor):
                    raise AttributeError
                return color_obj
            except AttributeError:
                raise ValueError(
                    f"Неподдерживаемый формат цвета: {color_value}"
                )
    elif isinstance(color_value, (tuple, list)) and len(color_value) == 3:
        # RGB в формате (R, G, B), где 0 <= R,G,B <= 255
        r, g, b = color_value
        return RLColor(r / 255.0, g / 255.0, b / 255.0)
    else:
        raise ValueError(f"Неподдерживаемый формат цвета: {color_value}")


# JSON схема для PDF, аналогичная DOCX
JSON_SCHEMA_PDF = """
    Верни ТОЛЬКО валидный JSON без пояснений.
    Строгая схема:
    {
    "meta": {"title": "string"},
    "blocks": [
        {"type":"heading","level":1,"text":"string",
        "font_name":"string", "font_size":12, "color":"string"},
        {"type":"paragraph","text":"string", "font_name":"string",
        "font_size":12, "left_indent":0, "right_indent":0,
        "space_after":12, "alignment":"left", "color":"string",
        "bold":false, "italic":false, "underline":false},
        {"type":"list", "ordered":false, "font_name":"string",
        "font_size":12, "left_indent":0, "right_indent":0, "space_after":12,
        "items":["item1", "item2"]},
        {"type":"table", "headers":["column1", "column2"],
           "rows":[["value1", "value2"], ["value3", "value4"]],
           "params": {
               "header_font_name":"CyrillicFont-Bold",
               "header_font_size":10,
               "body_font_name":"string",
               "body_font_size":9,
               "grid_width":0.5,
               "grid_color":"black",
               "header_bg_color":"cyan",
               "header_text_color":"black",
               "align":"LEFT",
               "valign":"TOP",
               "padding_top":6,
               "padding_bottom":6,
               "body_padding_top":4,
               "body_padding_bottom":4
           }
        },
        {"type":"math", "formula":"LaTeX formula",
        "caption":"optional caption",
        "font_name":"string", "font_size":12,
        "math_font_size":12,
        "caption_font_size":10, "bold":false, "italic":true,
        "alignment":"left"}
    ]
    }
    """


# Регистрируем шрифт, поддерживающий кириллицу
def register_cyrillic_font():
    """Регистрирует шрифт, поддерживающий кириллицу"""
    try:
        # Попробуем использовать стандартный шрифт Windows
        import platform

        if platform.system() == "Windows":
            font_path = "C:/Windows/Fonts/calibri.ttf"
            bold_font_path = "C:/Windows/Fonts/calibrib.ttf"  # Жирный Calibri
        else:
            # Для других систем можно использовать другие шрифты
            font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
            bold_font_path = (
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
            )

        # Регистрируем обычный шрифт
        pdfmetrics.registerFont(TTFont("CyrillicFont", font_path))

        # Попробуем зарегистрировать жирное начертание
        try:
            pdfmetrics.registerFont(
                TTFont("CyrillicFont-Bold", bold_font_path)
            )
        except (IOError, OSError):
            # Если не удалось загрузить жирный шрифт,
            #  регистрируем обычный как жирный
            pdfmetrics.registerFont(TTFont("CyrillicFont-Bold", font_path))

        return "CyrillicFont"
    except (IOError, OSError, RuntimeError):
        # Если не удалось загрузить шрифт, используем стандартный
        return "Helvetica"


# Константы для полей страницы
PAGE_LEFT_MARGIN = 20 * mm
PAGE_RIGHT_MARGIN = 10 * mm
PAGE_TOP_MARGIN = 15 * mm
PAGE_BOTTOM_MARGIN = 15 * mm


def clean_html_tags(text):
    """
    Очищает текст от HTML-тегов и других форматирований,
    не поддерживаемых в ReportLab.

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


CYRILLIC_FONT = register_cyrillic_font()

# Убедимся, что мы используем правильные имена шрифтов
CYRILLIC_FONT_BOLD = "CyrillicFont-Bold"


def normalize_font_name(font_name):
    """
    Нормализует имя шрифта, заменяя недопустимые шрифты на зарегистрированные

    Args:
        font_name (str): Имя шрифта из JSON

    Returns:
        str: Нормализованное имя шрифта
    """
    if not font_name:
        return CYRILLIC_FONT

    # Приводим к нижнему регистру и удаляем пробелы для сравнения
    normalized = font_name.lower().replace(" ", "").replace("-", "")

    # Проверяем, является ли шрифт Times New Roman или его вариантом
    if "times" in normalized or "newroman" in normalized:
        return CYRILLIC_FONT

    # Если это один из зарегистрированных шрифтов, возвращаем как есть
    if font_name in ["CyrillicFont", "CyrillicFont-Bold", "Helvetica"]:
        return font_name

    # В остальных случаях используем кириллический шрифт по умолчанию
    return CYRILLIC_FONT


def create_pdf_from_json(data: dict) -> io.BytesIO:
    """
    Создает PDF документ из JSON данных.

    Args:
        data: dict с ключами "meta" и "blocks" в формате, аналогичному DOCX

    Returns:
        io.BytesIO: PDF файл в виде байтового потока
    """
    # Создаем байтовый поток для PDF
    pdf_buffer = io.BytesIO()

    # Создаем документ с настраиваемыми полями (20 мм со всех сторон)
    doc = SimpleDocTemplate(
        pdf_buffer,
        pagesize=A4,
        leftMargin=PAGE_LEFT_MARGIN,
        rightMargin=PAGE_RIGHT_MARGIN,
        topMargin=PAGE_TOP_MARGIN,
        bottomMargin=PAGE_BOTTOM_MARGIN,
    )

    # Получаем стили
    styles = getSampleStyleSheet()

    # Обновляем стили, чтобы использовать кириллический шрифт
    styles["Normal"].fontName = CYRILLIC_FONT
    styles["Heading1"].fontName = CYRILLIC_FONT
    styles["Heading2"].fontName = CYRILLIC_FONT
    styles["Heading3"].fontName = CYRILLIC_FONT
    styles["Italic"].fontName = CYRILLIC_FONT

    title_style = ParagraphStyle(
        "CustomTitle",
        parent=styles["Heading1"],
        fontSize=18,
        spaceAfter=30,
        alignment=TA_CENTER,
        fontName=CYRILLIC_FONT,
    )

    # Список элементов для документа
    elements = []

    # Добавляем заголовок
    meta = data.get("meta", {})
    if "title" in meta:
        title = Paragraph(meta["title"], title_style)
        elements.append(title)
        elements.append(Spacer(1, 12))

    # Обрабатываем блоки
    for block in data.get("blocks", []):
        block_type = block.get("type")

        if block_type == "heading":
            level = block.get("level", 1)
            text = block.get("text", "")
            # Используем параметры из JSON, если они есть, иначе - стандартные
            font_name = block.get("font_name", CYRILLIC_FONT)
            font_name = normalize_font_name(
                font_name
            )  # Нормализуем имя шрифта
            font_size = block.get(
                "font_size", 16 if level == 1 else 14 if level == 2 else 12
            )
            text_color = block.get(
                "color", None
            )  # ReportLab поддерживает цвета

            heading_style = ParagraphStyle(
                f"CustomHeading{level}",
                parent=(
                    styles[f"Heading{min(level, 6)}"]
                    if f"Heading{min(level, 6)}" in styles
                    else styles["Heading1"]
                ),
                fontSize=font_size,
                spaceAfter=12,
                fontName=font_name,
            )
            # Если указан цвет, добавляем его
            if text_color:
                # Применяем цвет к стилю заголовка
                heading_style.textColor = parse_color(text_color)

            heading = Paragraph(text, heading_style)
            elements.append(heading)

        elif block_type == "paragraph":
            text = block.get("text", "")
            # Используем параметры из JSON, если они есть, иначе - стандартные
            font_name = block.get("font_name", CYRILLIC_FONT)
            font_name = normalize_font_name(
                font_name
            )  # Нормализуем имя шрифта
            font_size = block.get("font_size", 12)
            left_indent = block.get("left_indent", 0)
            right_indent = block.get("right_indent", 0)
            space_after = block.get("space_after", 12)
            alignment = block.get("alignment", "left")  # left, center, right
            text_color = block.get("color", None)

            # Определяем выравнивание
            alignment_val = TA_LEFT
            if alignment == "center":
                alignment_val = TA_CENTER
            elif alignment == "right":
                alignment_val = TA_RIGHT

            paragraph_style = ParagraphStyle(
                "CustomParagraph",
                parent=styles["Normal"],
                fontSize=font_size,
                spaceAfter=space_after,
                leftIndent=left_indent,
                rightIndent=right_indent,
                fontName=font_name,
                alignment=alignment_val,
            )

            # Применяем цвет, если он указан
            if text_color:
                # Применяем цвет к стилю параграфа
                paragraph_style.textColor = parse_color(text_color)

            # Применяем форматирование из JSON
            if block.get("bold"):
                text = f"<b>{text}</b>"
            if block.get("italic"):
                text = f"<i>{text}</i>"
            if block.get("underline"):
                text = f"<u>{text}</u>"

            paragraph = Paragraph(text, paragraph_style)
            elements.append(paragraph)

        elif block_type == "list":
            ordered = block.get("ordered", False)
            items = block.get("items", [])
            # Используем параметры из JSON, если они есть, иначе - стандартные
            font_name = block.get("font_name", CYRILLIC_FONT)
            font_name = normalize_font_name(
                font_name
            )  # Нормализуем имя шрифта
            font_size = block.get("font_size", 12)
            left_indent = block.get("left_indent", 0)
            right_indent = block.get("right_indent", 0)
            space_after = block.get("space_after", 12)

            # Создаем стиль для списка
            list_style = ParagraphStyle(
                "ListStyle",
                parent=styles["Normal"],
                fontSize=font_size,
                spaceAfter=space_after,
                leftIndent=left_indent,
                rightIndent=right_indent,
                fontName=font_name,
            )

            for item in items:
                bullet = (
                    "•" if not ordered else "○"
                )  # используем символ маркера
                list_item = Paragraph(f"{bullet} {item}", list_style)
                elements.append(list_item)

        elif block_type == "table":
            headers = block.get("headers", [])
            rows = block.get("rows", [])

            # Используем параметры из JSON, если они есть, иначе - стандартные
            table_params = block.get("params", {})
            header_font_name = table_params.get(
                "header_font_name", "CyrillicFont-Bold"
            )
            header_font_name = normalize_font_name(
                header_font_name
            )  # Нормализуем имя шрифта
            header_font_size = table_params.get("header_font_size", 10)
            body_font_name = table_params.get("body_font_name", CYRILLIC_FONT)
            body_font_name = normalize_font_name(
                body_font_name
            )  # Нормализуем имя шрифта
            body_font_size = table_params.get("body_font_size", 9)
            grid_width = table_params.get("grid_width", 0.5)
            grid_color = parse_color(table_params.get("grid_color", "black"))
            header_bg_color = parse_color(
                table_params.get("header_bg_color", "gray")
            )
            header_text_color = parse_color(
                table_params.get("header_text_color", "whitesmoke")
            )
            align = table_params.get("align", "LEFT")
            valign = table_params.get("valign", "TOP")
            padding_top = table_params.get("padding_top", 6)
            padding_bottom = table_params.get("padding_bottom", 6)
            body_padding_top = table_params.get("body_padding_top", 4)
            body_padding_bottom = table_params.get("body_padding_bottom", 4)

            if headers and rows:
                # Подготовим данные таблицы с учетом переноса текста
                # Для этого обернем каждую ячейку в Paragraph
                # с ограниченной шириной
                # Используем параметры из JSON для стиля
                normal_style = ParagraphStyle(
                    "TableNormal",
                    parent=getSampleStyleSheet()["Normal"],
                    fontName=body_font_name,
                    fontSize=body_font_size,
                    wordWrap="LTR",
                    alignment=TA_LEFT,
                )

                # Подготовим данные таблицы
                processed_table_data = []

                # Обрабатываем заголовки
                processed_headers = []
                for header in headers:
                    cleaned_header = clean_html_tags(str(header))
                    p = Paragraph(cleaned_header, normal_style)
                    processed_headers.append(p)
                processed_table_data.append(processed_headers)

                # Обрабатываем строки данных
                for row in rows:
                    processed_row = []
                    for cell in row:
                        cleaned_cell = clean_html_tags(str(cell))
                        p = Paragraph(cleaned_cell, normal_style)
                        processed_row.append(p)
                    processed_table_data.append(processed_row)

                # Создаем таблицу с обработанными данными
                table = Table(processed_table_data)

                # Устанавливаем максимальную ширину таблицы
                # равной ширине страницы минус отступы
                available_width = (
                    A4[0] - PAGE_LEFT_MARGIN - PAGE_RIGHT_MARGIN
                )  # ширина A4 минус левое и правое поля

                # Определяем количество столбцов
                num_cols = (
                    len(headers) if headers else len(rows[0]) if rows else 0
                )

                if num_cols > 0:
                    # Рассчитываем приблизительную ширину для каждого столбца
                    # на основе длины текста в заголовках
                    # и первых строках данных
                    col_widths = []

                    for col_idx in range(num_cols):
                        # Определяем максимальную длину текста в столбце
                        # (заголовок + первые несколько строк данных)
                        max_text_length = 0

                        # Проверяем заголовок
                        if col_idx < len(headers):
                            max_text_length = max(
                                max_text_length, len(str(headers[col_idx]))
                            )

                        # Проверяем первые несколько строк данных
                        # (ограничимся 5 строками для производительности)
                        for row_idx in range(min(5, len(rows))):
                            if col_idx < len(rows[row_idx]):
                                max_text_length = max(
                                    max_text_length,
                                    len(str(rows[row_idx][col_idx])),
                                )

                        # Устанавливаем ширину пропорционально длине текста
                        # Минимальная ширина - 1/num_cols от доступной ширины
                        # Максимальная ширина - пропорционально длине текста,
                        # но не больше 0.4 от всей ширины
                        col_width = min(
                            available_width * 0.4,
                            max(
                                available_width / num_cols, max_text_length * 3
                            ),
                        )  # примерный коэффициент
                        col_widths.append(col_width)

                    # Нормализуем ширину, чтобы общая ширина
                    # не превышала доступную
                    total_width = sum(col_widths)
                    if total_width > available_width:
                        # Масштабируем ширину столбцов
                        scale_factor = available_width / total_width
                        col_widths = [
                            width * scale_factor for width in col_widths
                        ]

                    table._argW = col_widths

                # Применяем стиль к таблице с параметрами из JSON
                table.setStyle(
                    TableStyle(
                        [
                            (
                                "ALIGN",
                                (0, 0),
                                (-1, -1),
                                align,
                            ),  # Выравнивание из JSON
                            (
                                "FONTNAME",
                                (0, 0),
                                (-1, 0),
                                header_font_name,
                            ),  # Шрифт для первой строки из JSON
                            (
                                "FONTSIZE",
                                (0, 0),
                                (-1, 0),
                                header_font_size,
                            ),  # Размер шрифта для заголовков из JSON
                            ("BOTTOMPADDING", (0, 0), (-1, 0), padding_bottom),
                            ("TOPPADDING", (0, 0), (-1, 0), padding_top),
                            (
                                "BOTTOMPADDING",
                                (0, 1),
                                (-1, -1),
                                body_padding_bottom,
                            ),
                            ("TOPPADDING", (0, 1), (-1, -1), body_padding_top),
                            (
                                "FONTNAME",
                                (0, 1),
                                (-1, -1),
                                body_font_name,
                            ),  # Шрифт для остальных строк из JSON
                            (
                                "FONTSIZE",
                                (0, 1),
                                (-1, -1),
                                body_font_size,
                            ),  # Размер шрифта для остальных строк из JSON
                            (
                                "GRID",
                                (0, 0),
                                (-1, -1),
                                grid_width,
                                grid_color,
                            ),  # Параметры сетки из JSON
                            (
                                "VALIGN",
                                (0, 0),
                                (-1, -1),
                                valign,
                            ),  # Выравнивание по вертикали из JSON
                            (
                                "BACKGROUND",
                                (0, 0),
                                (-1, 0),
                                header_bg_color,
                            ),  # Цвет фона заголовка из JSON
                            (
                                "TEXTCOLOR",
                                (0, 0),
                                (-1, 0),
                                header_text_color,
                            ),  # Цвет текста заголовка из JSON
                        ]
                    )
                )

                elements.append(table)
                elements.append(Spacer(1, 12))

        elif block_type == "math":
            # Для формул добавляем как изображение
            # с формулой или как обычный параграф
            formula = block.get("formula", "")
            caption = block.get("caption", "")

            # Используем параметры из JSON, если они есть, иначе - стандартные
            font_name = block.get("font_name", CYRILLIC_FONT)
            font_name = normalize_font_name(
                font_name
            )  # Нормализуем имя шрифта
            font_size = block.get("font_size", None)
            # Используем font_size как fallback,
            # если конкретные параметры не указаны
            math_font_size = (
                block.get("math_font_size", None) or font_size or 12
            )
            caption_font_size = (
                block.get("caption_font_size", None) or font_size or 10
            )
            bold = block.get("bold", False)
            italic = block.get(
                "italic", True
            )  # По умолчанию курсив для формул
            alignment = block.get("alignment", "left")  # left, center, right

            # Попробуем создать изображение с формулой с помощью matplotlib
            try:
                import matplotlib
                import matplotlib.pyplot as plt
                import io as io_module

                matplotlib.use("Agg")  # Use non-interactive backend

                # Настройка фигуры matplotlib с размерами,
                # пропорциональными длине формулы
                # Преобразуем размеры из миллиметров в дюймы (1 дюйм = 25.4 мм)
                base_width_mm = 60  # базовая ширина в мм
                width_factor = min(
                    len(formula) / 10, 3
                )  # масштабируем в зависимости от длины формулы, не более х3
                width_mm = base_width_mm * width_factor

                # Высота пропорциональна ширине, но с минимальным значением
                height_mm = max(
                    width_mm * 0.2, 15
                )  # высота в мм, не менее 15 мм

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
                img_buffer = io_module.BytesIO()
                plt.savefig(
                    img_buffer, format="png", bbox_inches="tight", dpi=150
                )
                img_buffer.seek(0)

                # Закрываем фигуру matplotlib
                plt.close(fig)

                # Преобразуем размеры из миллиметров в точки
                # (1 мм = 2.834645669 points)
                width_points = width_mm * 2.834645669
                height_points = height_mm * 2.834645669

                # Создаем изображение с подходящими размерами
                img = RLImage(
                    img_buffer, width=width_points, height=height_points
                )

                # Выравнивание изображения
                if alignment == "center":
                    img.hAlign = "CENTER"
                elif alignment == "right":
                    img.hAlign = "RIGHT"
                else:
                    img.hAlign = "LEFT"

                elements.append(img)

                if caption:
                    # Создаем стиль для подписи
                    caption_style = ParagraphStyle(
                        "CaptionStyle",
                        parent=styles["Normal"],
                        fontSize=caption_font_size,
                        fontName=font_name,
                        alignment=TA_LEFT if alignment != "left" else TA_LEFT,
                    )

                    caption_para = Paragraph(caption, caption_style)
                    elements.append(caption_para)

            except ImportError:
                # Если matplotlib не установлен, используем обычный текст
                # Определяем выравнивание
                alignment_val = TA_LEFT
                if alignment == "center":
                    alignment_val = TA_CENTER
                elif alignment == "right":
                    alignment_val = TA_RIGHT

                # Создаем стиль для формулы
                math_style = ParagraphStyle(
                    "MathStyle",
                    parent=styles["Normal"],
                    fontSize=math_font_size,
                    fontName=font_name,
                    alignment=alignment_val,
                )

                # Формируем текст формулы
                formula_text = f"Формула: {formula}"
                if bold:
                    formula_text = f"<b>{formula_text}</b>"
                if italic:
                    formula_text = f"<i>{formula_text}</i>"

                # Добавляем формулу как специальный параграф
                math_para = Paragraph(formula_text, math_style)
                elements.append(math_para)

                if caption:
                    # Создаем стиль для подписи
                    caption_style = ParagraphStyle(
                        "CaptionStyle",
                        parent=styles["Normal"],
                        fontSize=caption_font_size,
                        fontName=font_name,
                        alignment=alignment_val,
                    )

                    caption_para = Paragraph(caption, caption_style)
                    elements.append(caption_para)
            except Exception as e:
                # Если возникла ошибка при создании изображения,
                # используем обычный текст
                print(f"Ошибка при создании изображения формулы: {e}")

                # Определяем выравнивание
                alignment_val = TA_LEFT
                if alignment == "center":
                    alignment_val = TA_CENTER
                elif alignment == "right":
                    alignment_val = TA_RIGHT

                # Создаем стиль для формулы
                math_style = ParagraphStyle(
                    "MathStyle",
                    parent=styles["Normal"],
                    fontSize=math_font_size,
                    fontName=font_name,
                    alignment=alignment_val,
                )

                # Формируем текст формулы
                formula_text = f"Формула: {formula}"
                if bold:
                    formula_text = f"<b>{formula_text}</b>"
                if italic:
                    formula_text = f"<i>{formula_text}</i>"

                # Добавляем формулу как специальный параграф
                math_para = Paragraph(formula_text, math_style)
                elements.append(math_para)

                if caption:
                    # Создаем стиль для подписи
                    caption_style = ParagraphStyle(
                        "CaptionStyle",
                        parent=styles["Normal"],
                        fontSize=caption_font_size,
                        fontName=font_name,
                        alignment=alignment_val,
                    )

                    caption_para = Paragraph(caption, caption_style)
                    elements.append(caption_para)

    # Собираем документ
    doc.build(elements)

    # Перемещаем указатель в начало
    pdf_buffer.seek(0)

    return pdf_buffer


def check_user_wants_pdf_format(user_message):
    """
    Проверяет, хочет ли пользователь получить ответ в формате PDF.

    Args:
        user_message (str): Сообщение от пользователя для анализа

    Returns:
        bool: True если пользователь хочет формат PDF, False в противном случае
    """
    message = user_message.lower()
    return (
        "pdf" in message
        or "формат pdf" in message
        or "в pdf" in message
        or "в формате pdf" in message
        or "в формате пдф" in message
        or "пдф" in message
        or "adobe" in message
        or "документ pdf" in message
        or "pdf документ" in message
    )


async def send_pdf_response(update, reply):
    """
    Отправляет PDF-файл с ответом пользователю.

    Args:
        update: Объект обновления Telegram
        reply: Ответ от модели, который будет преобразован в PDF
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
        pdf_buffer = create_pdf_from_json(data)

        await update.message.reply_document(
            document=InputFile(pdf_buffer, filename="document.pdf"),
            caption="Ваш ответ в формате PDF",
        )
    except json.JSONDecodeError as e:
        # Если ответ не является валидным JSON,
        # отправляем обычное сообщение
        safe_reply = escape_markdown(reply, version=2)
        await send_long_message(update, safe_reply, parse_mode="MarkdownV2")
        print(f"Ошибка разбора JSON при создании PDF: {e}")
    except ValueError as e:
        # Если возникла ошибка значения (например, пустой ответ)
        safe_reply = escape_markdown(reply, version=2)
        await send_long_message(update, safe_reply, parse_mode="MarkdownV2")
        print(f"Ошибка значения при создании PDF: {e}")
    except Exception as e:
        # Если не удалось создать или отправить PDF,
        # отправляем обычное сообщение
        safe_reply = escape_markdown(reply, version=2)
        await send_long_message(update, safe_reply, parse_mode="MarkdownV2")
        print(f"Ошибка при создании или отправке PDF файла: {e}")
