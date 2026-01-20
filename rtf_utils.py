#!/usr/bin/env python3
"""
Utility functions for creating and handling RTF files.
"""

import io
import json


# Alternative RTF writer implementation
class RtfBuilder:
    """Simple RTF builder class to create RTF documents."""

    def __init__(self):
        self.content = []
        self.headers = []
        self.footers = []
        self.styles = {}

    def add_header(self, text, alignment="left"):
        """Add header to RTF document."""
        self.headers.append({"text": text, "alignment": alignment})

    def add_footer(self, text, alignment="left"):
        """Add footer to RTF document."""
        self.footers.append({"text": text, "alignment": alignment})

    def add_heading(self, text, level=1, alignment="left", bold=True):
        """Add heading to RTF document."""
        heading_styles = {
            1: r"\b\fs32",  # Large bold
            2: r"\b\fs28",  # Medium bold
            3: r"\b\fs24",  # Small bold
        }
        style = heading_styles.get(level, r"\b\fs20")
        self.content.append(
            {
                "type": "heading",
                "text": text,
                "level": level,
                "alignment": alignment,
                "style": style,
            }
        )

    def add_paragraph(
        self, text, alignment="left", italic=False, bold=False, underline=False
    ):
        """Add paragraph to RTF document."""
        style_parts = []
        if bold:
            style_parts.append("\\b")
        if italic:
            style_parts.append("\\i")
        if underline:
            style_parts.append("\\ul")

        style = " ".join(style_parts) if style_parts else ""
        self.content.append(
            {
                "type": "paragraph",
                "text": text,
                "alignment": alignment,
                "style": style,
            }
        )

    def add_list(self, items, ordered=False):
        """Add list to RTF document."""
        self.content.append(
            {"type": "list", "items": items, "ordered": ordered}
        )

    def add_table(self, headers, rows):
        """Add table to RTF document."""
        self.content.append(
            {"type": "table", "headers": headers, "rows": rows}
        )

    def add_math(self, formula, caption="", alignment="center"):
        """Add mathematical formula to RTF document."""
        self.content.append(
            {
                "type": "math",
                "formula": formula,
                "caption": caption,
                "alignment": alignment,
            }
        )

    def add_function_graph(
        self, function, title="", caption="", alignment="center"
    ):
        """Add function graph to RTF document (as placeholder text)."""
        self.content.append(
            {
                "type": "function_graph",
                "function": function,
                "title": title,
                "caption": caption,
                "alignment": alignment,
            }
        )

    def add_toc(self, title="Table of Contents", entries=None):
        """Add table of contents to RTF document."""
        if entries is None:
            entries = []
        self.content.append(
            {"type": "toc", "title": title, "entries": entries}
        )

    def to_rtf(self):
        """Convert internal representation to RTF string."""
        rtf_content = []

        # RTF header
        rtf_content.append(r"{\rtf1\ansi\deff0")
        rtf_content.append(r"{\fonttbl{\f0\fnil\fcharset0 Arial;}}")
        rtf_content.append(
            r"{\colortbl;\red0\green0\blue0;\red255\green0\blue0;}"
        )

        # Add headers
        for header in self.headers:
            alignment_code = self._get_alignment_code(header["alignment"])
            rtf_content.append(
                f"{alignment_code}{{\\b {self._escape_text(header['text'])}}}\\par"
            )

        # Add content
        for item in self.content:
            item_type = item["type"]

            if item_type == "heading":
                alignment_code = self._get_alignment_code(item["alignment"])
                rtf_content.append(
                    f"{alignment_code}{item['style']} {self._escape_text(item['text'])}\\b0\\fs20\\par"
                )

            elif item_type == "paragraph":
                alignment_code = self._get_alignment_code(item["alignment"])
                rtf_content.append(
                    f"{alignment_code}{item['style']} {self._escape_text(item['text'])}"
                )
                if "\\b" in item["style"]:
                    rtf_content[-1] += "\\b0"
                if "\\i" in item["style"]:
                    rtf_content[-1] += "\\i0"
                if "\\ul" in item["style"]:
                    rtf_content[-1] += "\\ul0"
                rtf_content[-1] += "\\par"

            elif item_type == "list":
                for i, list_item in enumerate(item["items"], 1):
                    bullet = f"{i}." if item["ordered"] else "\\bullet"
                    rtf_content.append(
                        f"\\ql {bullet} {self._escape_text(list_item)}\\par"
                    )

            elif item_type == "table":
                # Simple table representation
                rtf_content.append("\\ql\\b Table:\\b0\\par")
                # Add headers
                header_row = " | ".join(item["headers"])
                rtf_content.append(
                    f"\\ql {self._escape_text(header_row)}\\par"
                )
                # Add separator
                separator = "-" * len(header_row)
                rtf_content.append(f"\\ql {separator}\\par")
                # Add data rows
                for row in item["rows"]:
                    row_text = " | ".join(str(cell) for cell in row)
                    rtf_content.append(
                        f"\\ql {self._escape_text(row_text)}\\par"
                    )

            elif item_type == "math":
                alignment_code = self._get_alignment_code(item["alignment"])
                rtf_content.append(
                    f"{alignment_code}Formula: {self._escape_text(item['formula'])}\\par"
                )
                if item["caption"]:
                    rtf_content.append(
                        f"\\qc [{self._escape_text(item['caption'])}]\\par"
                    )

            elif item_type == "function_graph":
                alignment_code = self._get_alignment_code(item["alignment"])
                rtf_content.append(
                    f"{alignment_code}Graph of: {self._escape_text(item['function'])}\\par"
                )
                if item["title"]:
                    rtf_content.append(
                        f"\\b {self._escape_text(item['title'])}\\b0\\par"
                    )
                if item["caption"]:
                    rtf_content.append(
                        f"\\qc [{self._escape_text(item['caption'])}]\\par"
                    )

            elif item_type == "toc":
                rtf_content.append(
                    f"\\qc\\b {self._escape_text(item['title'])}\\b0\\par"
                )
                for entry in item["entries"]:
                    level = entry.get("level", 1)
                    text = entry["text"]
                    page = entry.get("page", "?")
                    indent = "  " * (level - 1)
                    rtf_content.append(
                        f"\\ql {indent}{self._escape_text(text)} .... {page}\\par"
                    )

        # Add footers
        for footer in self.footers:
            alignment_code = self._get_alignment_code(footer["alignment"])
            rtf_content.append(
                f"{alignment_code}{{\\i {self._escape_text(footer['text'])}}}\\par"
            )

        rtf_content.append("}")  # Close RTF document

        return "\n".join(rtf_content)

    def _get_alignment_code(self, alignment):
        """Get RTF alignment code."""
        alignment_map = {
            "left": "\\ql",  # Left align
            "center": "\\qc",  # Center align
            "right": "\\qr",  # Right align
            "justify": "\\qj",  # Justify
        }
        return alignment_map.get(alignment, "\\ql")  # Default to left

    def _escape_text(self, text):
        """Escape special RTF characters."""
        if text is None:
            return ""
        # Escape backslashes, braces, and other RTF special characters
        text = str(text)
        text = text.replace("\\", "\\\\")
        text = text.replace("{", "\\{")
        text = text.replace("}", "\\}")
        # Replace newlines with RTF paragraph breaks
        text = text.replace("\n", "\\par ")
        return text


class RtfRenderer:
    """RTF document renderer that follows 
        the same interface as other renderers.
    """

    def __init__(self):
        pass

    def render(self, data: dict, output):
        """
        Render JSON data to RTF document.
        :param data: dict with keys "meta", "header", "footer" and "blocks"
        :param output: path or BytesIO
        """
        builder = RtfBuilder()

        # Process meta information
        meta = data.get("meta", {})
        title = meta.get("title", "")
        hide_title = meta.get("hide_title", False)

        # Add title if not hidden and exists
        if title and not hide_title:
            builder.add_heading(title, level=1, alignment="center")

        # Process header
        header_data = data.get("header", {})
        if header_data:
            header_content = header_data.get("content", "")
            if header_content:
                header_alignment = header_data.get("alignment", "left")
                builder.add_header(header_content, header_alignment)

        # Process footer
        footer_data = data.get("footer", {})
        if footer_data:
            footer_content = footer_data.get("content", "")
            if footer_content:
                footer_alignment = footer_data.get("alignment", "left")
                builder.add_footer(footer_content, footer_alignment)

        # Process blocks
        for block in data.get("blocks", []):
            self._render_block(builder, block)

        # Generate RTF content
        rtf_content = builder.to_rtf()

        # Write to output
        if isinstance(output, io.BytesIO):
            output.write(rtf_content.encode("utf-8"))
            output.seek(0)
        else:
            with open(output, "w", encoding="utf-8") as f:
                f.write(rtf_content)

    def _render_block(self, builder, block: dict):
        """Render individual block to RTF."""
        block_type = block.get("type")

        if block_type == "heading":
            level = block.get("level", 1)
            text = block.get("text", "")
            alignment = block.get("alignment", "left")
            bold = block.get("bold", True)
            builder.add_heading(text, level, alignment, bold)

        elif block_type == "paragraph":
            text = block.get("text", "")
            alignment = block.get("alignment", "left")
            bold = block.get("bold", False)
            italic = block.get("italic", False)
            underline = block.get("underline", False)
            builder.add_paragraph(text, alignment, italic, bold, underline)

        elif block_type == "list":
            items = block.get("items", [])
            ordered = block.get("ordered", False)
            builder.add_list(items, ordered)

        elif block_type == "table":
            headers = block.get("headers", [])
            rows = block.get("rows", [])
            builder.add_table(headers, rows)

        elif block_type == "math":
            formula = block.get("formula", "")
            caption = block.get("caption", "")
            alignment = block.get("alignment", "center")
            builder.add_math(formula, caption, alignment)

        elif block_type == "function_graph":
            function = block.get("function", "")
            title = block.get("title", "")
            caption = block.get("caption", "")
            alignment = block.get("alignment", "center")
            builder.add_function_graph(function, title, caption, alignment)

        elif block_type == "toc":
            title = block.get("title", "Table of Contents")
            entries = block.get("entries", [])
            builder.add_toc(title, entries)

        else:
            raise ValueError(f"Unknown block type: {block_type}")


def create_rtf_from_json(data: dict) -> io.BytesIO:
    """
    Create RTF document from JSON data.
    :param data: JSON data dictionary
    :return: BytesIO with RTF content
    """
    output = io.BytesIO()
    renderer = RtfRenderer()
    renderer.render(data, output)
    output.seek(0)
    return output


def check_user_wants_rtf_format(user_message):
    """
    Check if user wants to receive description in RTF format.

    Args:
        user_message (str): The message from user to analyze

    Returns:
        bool: True if user wants RTF format, False otherwise
    """
    message = user_message.lower()

    # First check if there are any negative phrases 
    # that suggest they DON'T want RTF
    negative_patterns = [
        "not interested in rtf",
        "not interested in rtf format",
        "don't want rtf",
        "no need for rtf",
        "not rtf",
        "without rtf",
    ]

    for neg_pattern in negative_patterns:
        if neg_pattern in message:
            return False

    # Then check for positive indicators of wanting RTF
    positive_indicators = [
        "rtf",
        "формат rtf",
        "rich text format",
        "в rtf",
        "в формате rtf",
        "в формате rich text",
        "rtf документ",
        "документ rtf",
        "в формате документа rtf",
        "в rtf формате",
        "в rich text format",
        "в формате rich text",
    ]

    for indicator in positive_indicators:
        if indicator in message:
            return True

    return False


async def send_rtf_response(update, reply, image_url=None):
    """
    Send RTF content as text message to user.
    Args:
        update: Telegram update object
        reply: Response from model to convert to RTF
    """
    try:
        # Check if reply is empty
        if not reply or reply.strip() == "":
            raise ValueError("Empty response from model")

        # Clean up markdown-style code blocks
        cleaned_reply = reply.strip()
        if cleaned_reply.startswith("```json"):
            cleaned_reply = cleaned_reply[7:]  # Remove '```json'
        elif cleaned_reply.startswith("```"):
            cleaned_reply = cleaned_reply[3:]  # Remove '```'

        if cleaned_reply.endswith("```"):
            cleaned_reply = cleaned_reply[:-3]  # Remove closing '```'

        cleaned_reply = cleaned_reply.strip()

        data = json.loads(cleaned_reply)

        # Create RTF content
        builder = RtfBuilder()

        # Process meta information
        meta = data.get("meta", {})
        title = meta.get("title", "")
        hide_title = meta.get("hide_title", False)

        # Add title if not hidden and exists
        if title and not hide_title:
            builder.add_heading(title, level=1, alignment="center")

        # Process header
        header_data = data.get("header", {})
        if header_data:
            header_content = header_data.get("content", "")
            if header_content:
                header_alignment = header_data.get("alignment", "left")
                builder.add_header(header_content, header_alignment)

        # Process footer
        footer_data = data.get("footer", {})
        if footer_data:
            footer_content = footer_data.get("content", "")
            if footer_content:
                footer_alignment = footer_data.get("alignment", "left")
                builder.add_footer(footer_content, footer_alignment)

        # Process blocks
        for block in data.get("blocks", []):
            block_type = block.get("type")

            if block_type == "heading":
                level = block.get("level", 1)
                text = block.get("text", "")
                alignment = block.get("alignment", "left")
                bold = block.get("bold", True)
                builder.add_heading(text, level, alignment, bold)

            elif block_type == "paragraph":
                text = block.get("text", "")
                alignment = block.get("alignment", "left")
                bold = block.get("bold", False)
                italic = block.get("italic", False)
                underline = block.get("underline", False)
                builder.add_paragraph(text, alignment, italic, bold, underline)

            elif block_type == "list":
                items = block.get("items", [])
                ordered = block.get("ordered", False)
                builder.add_list(items, ordered)

            elif block_type == "table":
                headers = block.get("headers", [])
                rows = block.get("rows", [])
                builder.add_table(headers, rows)

            elif block_type == "math":
                formula = block.get("formula", "")
                caption = block.get("caption", "")
                alignment = block.get("alignment", "center")
                builder.add_math(formula, caption, alignment)

            elif block_type == "function_graph":
                function = block.get("function", "")
                title = block.get("title", "")
                caption = block.get("caption", "")
                alignment = block.get("alignment", "center")
                builder.add_function_graph(function, title, caption, alignment)

            elif block_type == "toc":
                title = block.get("title", "Table of Contents")
                entries = block.get("entries", [])
                builder.add_toc(title, entries)

        # Generate RTF content
        rtf_content = builder.to_rtf()

        # Create the message with RTF content
        message = f"""Ниже приведён **готовый RTF‑документ**.
Скопируй **весь текст целиком**, вставь в файл и сохрани с расширением **`.rtf`** (например, `Учебный_план_Астрономия.rtf`). Документ корректно откроется в **Microsoft Word / LibreOffice Writer** со всем форматированием.

```
{rtf_content}
```
"""

        # Send the message to the user
        from message_utils import send_long_message
        await send_long_message(update, message, parse_mode="MarkdownV2")

        return message

    except json.JSONDecodeError as e:
        # If response is not valid JSON, return as plain text
        from message_utils import send_long_message
        from telegram.helpers import escape_markdown

        safe_reply = escape_markdown(reply, version=2)
        await send_long_message(update, safe_reply, parse_mode="MarkdownV2")
        print(f"Error parsing JSON for RTF creation: {e}")
        return None
    except ValueError as e:
        # If response is empty
        from message_utils import send_long_message
        from telegram.helpers import escape_markdown

        safe_reply = escape_markdown(reply, version=2)
        await send_long_message(update, safe_reply, parse_mode="MarkdownV2")
        print(f"Error with RTF creation: {e}")
        return None
    except Exception as e:
        # General error handling
        from message_utils import send_long_message
        from telegram.helpers import escape_markdown

        safe_reply = escape_markdown(reply, version=2)
        await send_long_message(update, safe_reply, parse_mode="MarkdownV2")
        print(f"Error creating RTF content: {e}")
        return None
