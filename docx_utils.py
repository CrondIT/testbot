"""Utility functions for creating and handling DOCX files."""

from docx import Document
from docx.shared import Inches, Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.style import WD_STYLE_TYPE
from docx.oxml.ns import qn
import re
import io


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
