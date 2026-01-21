"""
Utility functions for creating and handling RTF files.
"""

import logging
import tempfile
import os
import datetime

# ---------------------------------------------------------
# Логирование
# ---------------------------------------------------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


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


def create_rtf_file(text: str) -> str:
    # Конвертируем Unicode → cp1251
    # Но RTF должен содержать специальные escape-слоты для не ASCII символов
    rtf_text = []

    for ch in text:
        if ord(ch) < 128:
            rtf_text.append(ch)  # ASCII можно напрямую
        else:
            # Не ASCII → RTF unicode escape
            # Например: \u1090?
            rtf_text.append(rf"\u{ord(ch)}?")

    rtf_body = "".join(rtf_text)
    rtf = (
        r"{\rtf1\ansi\ansicpg1251 "
        + rtf_body.replace("\n", r"\par ")
        + "}"
    )

    # Создаём временный файл
    filename = os.path.join(
        tempfile.gettempdir(),
        f"reply_{int(datetime.datetime.utcnow().timestamp())}.rtf"
    )

    # Важно: записываем ASCII, т.к. Unicode уже упакован в \uXXXX?
    with open(filename, "w", encoding="ascii", errors="ignore") as f:
        f.write(rtf)

    return filename


async def send_rtf_response(update, reply, image_url=None):
    try:
        # Создаем временный RTF-файл
        timestamp = int(datetime.datetime.utcnow().timestamp())
        temp_dir = tempfile.gettempdir()
        file_path = os.path.join(temp_dir, f"reply_{timestamp}.rtf")

        file_path = create_rtf_file(reply)

        # Отправка файла пользователю
        with open(file_path, "rb") as f:
            await update.message.reply_document(
                document=f,
                filename=os.path.basename(file_path),
                caption="Файл с ответом модели (RTF)"
            )

        logger.info(f"Файл отправлен: {file_path}")

    except Exception as e:
        logger.exception("Ошибка обработки сообщения")
        await update.message.reply_text(
            f"Произошла ошибка при обработке вашего запроса {e}."
        )
    finally:
        # Удалим временный файл
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.info(f"Временный файл удалён: {file_path}")
        except Exception:
            logger.warning(f"Не удалось удалить временный файл: {file_path}")
