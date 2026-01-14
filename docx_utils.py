"""Utility functions for creating and handling DOCX files."""

from docx import Document
from docx.shared import Inches, Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
import re
import io

JSON_SCHEMA = """
    Верни ТОЛЬКО валидный JSON без пояснений.
    Строгая схема:
    {
    "meta": {"title": "string"},
    "blocks": [
        {"type":"heading","level":1,"text":"string"},
        {"type":"paragraph","text":"string"},
        {"type":"list", "ordered":false,
            "items":["item1", "item2"]
        },
        {"type":"table", "headers":["column1", "column2"],
           "rows":[["value1", "value2"], ["value3", "value4"]]
        }
    ]
    }
    """


class DocxRenderer:
    def __init__(self):
        self.doc = Document()

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
        else:
            raise ValueError(f"Unknown block type: {block_type}")

    def _heading(self, block: dict):
        level = block.get("level", 1)
        text = block.get("text", "")
        self.doc.add_heading(text, level=level)

    def _paragraph(self, block: dict):
        p = self.doc.add_paragraph()
        run = p.add_run(block.get("text", ""))

        if block.get("bold"):
            run.bold = True
        if block.get("italic"):
            run.italic = True

        align = block.get("align")
        if align == "center":
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        elif align == "right":
            p.alignment = WD_ALIGN_PARAGRAPH.RIGHT

    def _list(self, block: dict):
        ordered = block.get("ordered", False)
        style = "List Number" if ordered else "List Bullet"

        for item in block.get("items", []):
            self.doc.add_paragraph(item, style=style)

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

        if not headers or not rows:
            return  # Пустая таблица — ничего не делаем

        table = self.doc.add_table(rows=1, cols=len(headers))
        table.style = "Table Grid"  # красивый стиль с границами
    # Заголовки
        hdr_cells = table.rows[0].cells
        for i, header in enumerate(headers):
            hdr_cells[i].text = str(header)

        # Данные
        for row in rows:
            cells = table.add_row().cells
            for i, value in enumerate(row):
                cells[i].text = str(value)


def create_formatted_docx(text_content, formatting_instructions=None):
    """
    Create a formatted DOCX document from text content
    based on formatting instructions.
    Args:
        text_content (str): The content to format
        formatting_instructions (dict): 
        Instructions for formatting the document
    Returns:
        io.BytesIO: The DOCX file as bytes
    """
    doc = Document()
    # Apply basic formatting if no specific instructions provided
    if not formatting_instructions:
        formatting_instructions = {
            "title": True,
            "headings": True,
            "paragraph_spacing": True,
            "font_size": 12,
        }
    # Process the text content to identify different elements
    lines = text_content.split("\n")
    for line in lines:
        line = line.strip()
        if not line:
            continue
        # Check if line looks like a heading (starts with # or is in all caps)
        if line.startswith("#"):
            # Markdown-style heading
            level = len(line) - len(line.lstrip("#"))
            heading_text = line.lstrip("# ").strip()
            doc.add_heading(heading_text, level=min(level, 9))
        elif line.isupper() and len(line) < 100:
            # All caps line likely a heading
            doc.add_heading(line, level=1)
        else:
            # Regular paragraph
            paragraph = doc.add_paragraph()
            run = paragraph.add_run(line)
            run.font.size = Pt(formatting_instructions.get("font_size", 12))
            # Apply additional formatting based on instructions
            if formatting_instructions.get("bold_first_line", False):
                run.bold = True
    # Apply general document formatting
    apply_general_formatting(doc, formatting_instructions)
    # Save to BytesIO object
    doc_io = io.BytesIO()
    doc.save(doc_io)
    doc_io.seek(0)
    return doc_io


def apply_general_formatting(doc, formatting_instructions):
    """Apply general formatting to the document."""
    # Set page margins
    section = doc.sections[0]
    section.top_margin = Inches(1)
    section.bottom_margin = Inches(1)
    section.left_margin = Inches(1)
    section.right_margin = Inches(1)
    # Apply paragraph spacing if requested
    if formatting_instructions.get("paragraph_spacing", False):
        for paragraph in doc.paragraphs:
            paragraph.space_after = Pt(6)

    # Apply line spacing if requested
    line_spacing = formatting_instructions.get("line_spacing", 1.0)
    for paragraph in doc.paragraphs:
        paragraph.line_spacing = line_spacing


def parse_formatting_request(user_request):
    """
    Parse user's formatting request to extract formatting preferences.

    Args:
        user_request (str): User's request that 
        may contain formatting instructions
    Returns:
        dict: Parsed formatting instructions
    """
    formatting_instructions = {}
    # Look for font size requests
    font_size_match = re.search(
        r"(\d+)\s*(?:pt|point|points|размер)", user_request, re.IGNORECASE
    )
    if font_size_match:
        formatting_instructions["font_size"] = int(font_size_match.group(1))
    # Look for line spacing requests
    line_spacing_match = re.search(
        r"(?:line|spacing|между строками)\s*(\d+\.?\d*)",
        user_request,
        re.IGNORECASE,
    )
    if line_spacing_match:
        formatting_instructions["line_spacing"] = float(
            line_spacing_match.group(1)
        )
    # Look for bold first line requests
    if re.search(
        r"(?:жирный|bold|выделить)\s+(?:первую|first)",
        user_request,
        re.IGNORECASE,
    ):
        formatting_instructions["bold_first_line"] = True
    # Look for paragraph spacing requests
    if re.search(
        r"(?:spacing|между абзацами|абзац)", user_request, re.IGNORECASE
    ):
        formatting_instructions["paragraph_spacing"] = True
    # Look for heading requests
    if re.search(
        r"(?:заголовки|headings|titles)", user_request, re.IGNORECASE
    ):
        formatting_instructions["headings"] = True
    return formatting_instructions


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


def clean_content_for_docx(content):
    """
    Clean content by removing markdown formatting and unnecessary mentions
    of DOCX formatting capabilities.

    Args:
        content (str): The content to clean

    Returns:
        str: Cleaned content without markdown formatting
    """
    import re

    # Remove bold markers (**)
    cleaned = re.sub(r'\*\*(.*?)\*\*', r'\1', content)

    # Remove italic markers (* or _)
    cleaned = re.sub(r'(?<!\*)\*([^\*]+?)\*(?!\*)', r'\1', cleaned)
    cleaned = re.sub(r'(?<!_)_([^_]+?)_(?!_)', r'\1', cleaned)

    # Remove unnecessary mentions about DOCX formatting
    cleaned = re.sub(r'Если хотите, могу оформить это как \*\*готовый \.DOCX\*\*\.?', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'Могу оформить это в формате \*\*Word \.docx\*\*\.?', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'Я могу предоставить это в формате \*\*Word \.docx\*\*\.?', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'Вот ваш текст в формате \*\*Word \.docx\*\*\.?', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'При необходимости могу оформить это как \*\*Word \.docx\*\*\.?', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'Могу подготовить это в формате \*\*Word \.docx\*\*\.?', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'Могу оформить в формате \*\*Word \.docx\*\*\.?', '', cleaned, flags=re.IGNORECASE)

    # Remove extra whitespace that might result from removals
    cleaned = re.sub(r'\n\s*\n', '\n\n', cleaned)
    cleaned = cleaned.strip()

    return cleaned
