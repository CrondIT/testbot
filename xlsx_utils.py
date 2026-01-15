"""Utility functions for creating and handling XLSX files."""

import io
import json
from telegram import InputFile
from telegram.helpers import escape_markdown
from message_utils import send_long_message
import xlsxwriter

# Константы для формата страницы и полей (в миллиметрах)
DEFAULT_PAGE_WIDTH_MM = 210  # Ширина A4 в мм
DEFAULT_PAGE_HEIGHT_MM = 297  # Высота A4 в мм
DEFAULT_LEFT_MARGIN_MM = 20  # Левое поле по умолчанию
DEFAULT_RIGHT_MARGIN_MM = 10  # Правое поле по умолчанию
DEFAULT_TOP_MARGIN_MM = 15  # Верхнее поле по умолчанию
DEFAULT_BOTTOM_MARGIN_MM = 15  # Нижнее поле по умолчанию

JSON_SCHEMA_EXCEL = """
    Верни ТОЛЬКО валидный JSON без пояснений.
    Не используй markdown, только JSON.
    Не включай тройные кавычки в значениях.
    Строгая схема:
    {
    "meta": {"title": "string"},
    "sheets": [
        {
            "name": "string",
            "data": [
                ["cell1", "cell2", "cell3"],
                ["row2_col1", "row2_col2", "row2_col3"]
            ],
            "headers": ["header1", "header2", "header3"],
            "formats": {
                "header": {"bold": true, "bg_color": "#D3D3D3"},
                "cell": {"font_size": 12}
            }
        }
    ]
    }
    """


class XlsxRenderer:
    def __init__(self):
        self.workbook = None

    def render(self, data: dict, output):
        """
        Рендерим JSON документ в XLSX.
        :param data: dict с ключами "meta" и "sheets"
        :param output: path или BytesIO
        """
        # Создаем workbook в памяти
        if isinstance(output, io.BytesIO):
            self.workbook = xlsxwriter.Workbook(output, {"in_memory": True})
        else:
            self.workbook = xlsxwriter.Workbook(output)

        self._render_meta(data.get("meta", {}))
        self._render_sheets(data.get("sheets", []))

        # Сохраняем в файл или BytesIO
        self.workbook.close()

    def _render_meta(self, meta: dict):
        # Создаем общую информацию в отдельном листе, если есть заголовок
        if "title" in meta:
            worksheet = self.workbook.add_worksheet("Info")
            worksheet.write(0, 0, "Title")
            worksheet.write(0, 1, meta["title"])

    def _render_sheets(self, sheets: list):
        for i, sheet_data in enumerate(sheets):
            name = sheet_data.get("name", f"Sheet{i+1}")
            worksheet = self.workbook.add_worksheet(name)

            # Установка полей страницы
            worksheet.set_margins(
                left=DEFAULT_LEFT_MARGIN_MM / 25.4,  # Преобразуем мм в дюймы
                right=DEFAULT_RIGHT_MARGIN_MM / 25.4,
                top=DEFAULT_TOP_MARGIN_MM / 25.4,
                bottom=DEFAULT_BOTTOM_MARGIN_MM / 25.4,
            )

            # Установка ориентации и размера страницы
            worksheet.set_paper(9)  # A4
            worksheet.set_portrait()  # Книжная ориентация

            headers = sheet_data.get("headers", [])
            data_rows = sheet_data.get("data", [])
            formats = sheet_data.get("formats", {})

            # Создаем все возможные форматы
            header_format = self._create_format(formats.get("header", {}))
            cell_format = self._create_format(formats.get("cell", {}))
            # Создаем дополнительные форматы, если они определены
            additional_formats = {}
            for format_name, format_props in formats.items():
                if format_name not in [
                    "header",
                    "cell",
                ]:  # Пропускаем уже созданные
                    additional_formats[format_name] = self._create_format(
                        format_props
                    )

            # Записываем заголовки
            for col_num, header in enumerate(headers):
                worksheet.write(0, col_num, header, header_format)

            # Записываем данные
            for row_num, row_data in enumerate(data_rows, start=1):
                for col_num, cell_data in enumerate(row_data):
                    if col_num < len(
                        headers
                    ):  # Только если колонка существует в заголовках
                        # Проверяем, есть ли специальный формат для этой строки
                        # Например, если в строке есть слово "ИТОГО",
                        #  используем формат "total"
                        target_format = cell_format
                        if any(
                            "итого" in str(cell).lower() for cell in row_data
                        ):  # Проверяем, содержит ли строка "ИТОГО"
                            if "total" in additional_formats:
                                target_format = additional_formats["total"]

                        worksheet.write(
                            row_num, col_num, cell_data, target_format
                        )

            # Автонастройка ширины колонок
            for col_num, header in enumerate(headers):
                worksheet.set_column(
                    col_num, col_num, max(len(str(header)), 10)
                )

    def _create_format(self, format_dict: dict):
        """Создает формат XLSX из словаря параметров"""
        if not format_dict:
            return None

        # Создаем копию словаря, чтобы не изменять оригинальный
        format_copy = format_dict.copy()

        # Преобразуем цвета из HEX в формат XLSX
        if "bg_color" in format_copy and format_copy["bg_color"].startswith(
            "#"
        ):
            format_copy["bg_color"] = format_copy["bg_color"][1:]  # Убираем #

        if "fg_color" in format_copy and format_copy["fg_color"].startswith(
            "#"
        ):
            format_copy["fg_color"] = format_copy["fg_color"][1:]  # Убираем #

        # Обработка параметра border
        if "border" in format_copy:
            border_value = format_copy["border"]
            # В xlsxwriter используется общий параметр border,
            # а не отдельные стороны
            if border_value == "thin":
                format_copy.update({"border": 1, "border_color": "black"})
            elif border_value == "medium":
                format_copy.update({"border": 2, "border_color": "black"})
            elif border_value == "thick":
                format_copy.update({"border": 3, "border_color": "black"})
            # Удаляем исходный параметр border, так как он заменен 
            # общим параметром
            del format_copy["border"]

        return self.workbook.add_format(format_copy)


def check_user_wants_xlsx_format(user_message):
    """
    Check if user wants to receive description in XLSX format.

    Args:
        user_message (str): The message from user to analyze

    Returns:
        bool: True if user wants XLSX format, False otherwise
    """
    message = user_message.lower()
    return (
        "xlsx" in message
        or "excel" in message
        or "таблица" in message
        or "таблицу" in message
        or "в экселе" in message
        or "в формате excel" in message
        or "в формате xlsx" in message
        or "в формате xls" in message
        or "в формате таблицы" in message
        or "в виде таблицы" in message
        or "в виде экселя" in message
        or "в виде xlsx" in message
        or "excel документ" in message
        or "документ excel" in message
        or "табличный формат" in message
    )


async def send_xlsx_response(update, reply):
    """
    Отправляет XLSX-файл с ответом пользователю.
    Args:
        update: Объект обновления Telegram
        reply: Ответ от модели, который будет преобразован в XLSX
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
        xlsx_io = io.BytesIO()
        renderer = XlsxRenderer()
        renderer.render(data, xlsx_io)
        xlsx_io.seek(0)

        await update.message.reply_document(
            document=InputFile(xlsx_io, filename="document.xlsx"),
            caption="Ваш ответ в формате Excel",
        )
    except json.JSONDecodeError as e:
        # Если ответ не является валидным JSON,
        # отправляем обычное сообщение
        safe_reply = escape_markdown(reply, version=2)
        await send_long_message(update, safe_reply, parse_mode="MarkdownV2")
        print(f"Ошибка разбора JSON при создании XLSX: {e}")
    except ValueError as e:
        # Если возникла ошибка значения (например, пустой ответ)
        safe_reply = escape_markdown(reply, version=2)
        await send_long_message(update, safe_reply, parse_mode="MarkdownV2")
        print(f"Ошибка значения при создании XLSX: {e}")
    except Exception as e:
        # Если не удалось создать или отправить
        # XLSX, отправляем обычное сообщение
        safe_reply = escape_markdown(reply, version=2)
        await send_long_message(update, safe_reply, parse_mode="MarkdownV2")
        print(f"Ошибка при создании или отправке XLSX файла: {e}")
