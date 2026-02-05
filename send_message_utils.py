"""Utility functions for sending messages to selected Telegram chats."""

import logging
from typing import Optional, Union
from telegram import Bot
from telegram.error import TelegramError
from telegram.constants import MessageLimit


logger = logging.getLogger(__name__)

# Define MAX_MESSAGE_LENGTH for backward compatibility
MAX_MESSAGE_LENGTH = MessageLimit.MAX_TEXT_LENGTH


class TelegramMessageSender:
    """Class for sending messages to Telegram chats."""

    def __init__(self, bot_token: str):
        """
        Initialize the message sender with bot token.

        Args:
            bot_token (str): Telegram bot token
        """
        self.bot = Bot(token=bot_token)

    async def send_message(
        self,
        chat_id: Union[int, str],
        text: str,
        parse_mode: Optional[str] = None,
        disable_web_page_preview: bool = False,
        disable_notification: bool = False,
        reply_to_message_id: Optional[int] = None,
        allow_sending_without_reply: bool = False,
    ) -> dict:
        """
        Send a message to a specific chat.

        Args:
            chat_id (Union[int, str]): Unique identifier for the target chat
            or username of the target channel
            text (str): Text of the message to be sent
            parse_mode (Optional[str]): Mode for parsing entities
            in the message text
            disable_web_page_preview (bool): Disables link previews
            for links in this message
            disable_notification (bool): Sends the message silently
            reply_to_message_id (Optional[int]): If the message is a reply,
            ID of the original message
            allow_sending_without_reply (bool): Pass True if the message
            should be sent even if the specified replied-to message
            is not found

        Returns:
            dict: Response from Telegram API
        """
        try:
            # Check if message exceeds Telegram's limit
            if len(text) > MAX_MESSAGE_LENGTH:
                # Split the message into chunks
                return await self._send_long_message(
                    chat_id=chat_id,
                    text=text,
                    parse_mode=parse_mode,
                    disable_web_page_preview=disable_web_page_preview,
                    disable_notification=disable_notification,
                    reply_to_message_id=reply_to_message_id,
                    allow_sending_without_reply=allow_sending_without_reply,
                )

            response = await self.bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=parse_mode,
                disable_web_page_preview=disable_web_page_preview,
                disable_notification=disable_notification,
                reply_to_message_id=reply_to_message_id,
                allow_sending_without_reply=allow_sending_without_reply,
            )
            return response.to_dict()

        except TelegramError as e:
            logger.error(f"Error sending message to chat {chat_id}: {e}")
            raise

    async def _send_long_message(
        self,
        chat_id: Union[int, str],
        text: str,
        parse_mode: Optional[str] = None,
        disable_web_page_preview: bool = False,
        disable_notification: bool = False,
        reply_to_message_id: Optional[int] = None,
        allow_sending_without_reply: bool = False,
    ) -> list:
        """
        Send a long message by splitting it into chunks
        that fit Telegram's limit.

        Args:
            chat_id (Union[int, str]): Unique identifier for the target chat
            or username of the target channel
            text (str): Text of the message to be sent
            parse_mode (Optional[str]): Mode for parsing entities
            in the message text
            disable_web_page_preview (bool): Disables link previews
            for links in this message
            disable_notification (bool): Sends the message silently
            reply_to_message_id (Optional[int]): If the message is a reply,
            ID of the original message
            allow_sending_without_reply (bool): Pass True if the message
            should be sent even if the specified replied-to message
            is not found

        Returns:
            list: List of responses from Telegram API for each chunk
        """
        responses = []

        # Split by paragraphs first to avoid breaking sentences
        paragraphs = text.split("\n")

        current_chunk = ""

        for paragraph in paragraphs:
            # Check if adding this paragraph would exceed the limit
            if len(current_chunk) + len(paragraph) + 1 <= MAX_MESSAGE_LENGTH:
                if current_chunk:
                    current_chunk += "\n" + paragraph
                else:
                    current_chunk = paragraph
            else:
                # Send the current chunk if it's not empty
                if current_chunk:
                    response = await self.bot.send_message(
                        chat_id=chat_id,
                        text=current_chunk,
                        parse_mode=parse_mode,
                        disable_web_page_preview=disable_web_page_preview,
                        disable_notification=disable_notification,
                        reply_to_message_id=reply_to_message_id,
                        allow_sending_without_reply=(
                            allow_sending_without_reply
                            ),
                    )
                    responses.append(response.to_dict())

                # If the single paragraph is too long, split it by sentences
                if len(paragraph) > MAX_MESSAGE_LENGTH:
                    sentences = paragraph.split(". ")
                    temp_chunk = ""

                    for sentence in sentences:
                        if (
                            len(temp_chunk) + len(sentence) + 2
                            <= MAX_MESSAGE_LENGTH
                        ):
                            if temp_chunk:
                                temp_chunk += ". " + sentence
                            else:
                                temp_chunk = sentence
                        else:
                            if temp_chunk:
                                response = await self.bot.send_message(
                                    chat_id=chat_id,
                                    text=temp_chunk + ".",
                                    parse_mode=parse_mode,
                                    disable_web_page_preview=(
                                        disable_web_page_preview
                                        ),
                                    disable_notification=disable_notification,
                                    reply_to_message_id=reply_to_message_id,
                                    allow_sending_without_reply=(
                                        allow_sending_without_reply
                                        ),
                                )
                                responses.append(response.to_dict())

                            temp_chunk = sentence

                    # Add the last part if there's anything left
                    if temp_chunk:
                        current_chunk = temp_chunk
                    else:
                        current_chunk = ""
                else:
                    current_chunk = paragraph

        # Send the remaining chunk if there's anything left
        if current_chunk:
            response = await self.bot.send_message(
                chat_id=chat_id,
                text=current_chunk,
                parse_mode=parse_mode,
                disable_web_page_preview=disable_web_page_preview,
                disable_notification=disable_notification,
                reply_to_message_id=reply_to_message_id,
                allow_sending_without_reply=allow_sending_without_reply,
            )
            responses.append(response.to_dict())

        return responses

    async def send_photo(
        self,
        chat_id: Union[int, str],
        photo: Union[str, bytes],
        caption: Optional[str] = None,
        parse_mode: Optional[str] = None,
        disable_notification: bool = False,
        reply_to_message_id: Optional[int] = None,
        allow_sending_without_reply: bool = False,
    ) -> dict:
        """
        Send a photo to a specific chat.

        Args:
            chat_id (Union[int, str]): Unique identifier for the target chat
            or username of the target channel
            photo (Union[str, bytes]): Photo to send.
            Pass a file_id as String to send a photo that exists
            on the Telegram servers, or pass an HTTP URL as a String
            for Telegram to get a photo from the Internet,
            or upload a new photo using multipart/form-data
            caption (Optional[str]): Photo caption
            parse_mode (Optional[str]): Mode for parsing entities
            in the caption disable_notification (bool): Sends the message
            silently reply_to_message_id (Optional[int]): If the message
            is a reply, ID of the original message allow_sending_without_reply
            (bool): Pass True if the message should be sent
            even if the specified replied-to message is not found

        Returns:
            dict: Response from Telegram API
        """
        try:
            response = await self.bot.send_photo(
                chat_id=chat_id,
                photo=photo,
                caption=caption,
                parse_mode=parse_mode,
                disable_notification=disable_notification,
                reply_to_message_id=reply_to_message_id,
                allow_sending_without_reply=allow_sending_without_reply,
            )
            return response.to_dict()
        except TelegramError as e:
            logger.error(f"Error sending photo to chat {chat_id}: {e}")
            raise

    async def send_document(
        self,
        chat_id: Union[int, str],
        document: Union[str, bytes],
        caption: Optional[str] = None,
        parse_mode: Optional[str] = None,
        disable_notification: bool = False,
        reply_to_message_id: Optional[int] = None,
        allow_sending_without_reply: bool = False,
    ) -> dict:
        """
        Send a document to a specific chat.

        Args:
            chat_id (Union[int, str]): Unique identifier for the target
            chat or username of the target channel document
            (Union[str, bytes]): File to send. Pass a file_id
            as String to send a file that exists on the Telegram servers,
            or upload a new file using multipart/form-data
            caption (Optional[str]): Document caption
            parse_mode (Optional[str]): Mode for parsing entities
            in the caption disable_notification (bool): Sends the message
            silently reply_to_message_id (Optional[int]): If the message
            is a reply, ID of the original message
            allow_sending_without_reply (bool): Pass True if the message
            should be sent even if the specified replied-to message
            is not found

        Returns:
            dict: Response from Telegram API
        """
        try:
            response = await self.bot.send_document(
                chat_id=chat_id,
                document=document,
                caption=caption,
                parse_mode=parse_mode,
                disable_notification=disable_notification,
                reply_to_message_id=reply_to_message_id,
                allow_sending_without_reply=allow_sending_without_reply,
            )
            return response.to_dict()
        except TelegramError as e:
            logger.error(f"Error sending document to chat {chat_id}: {e}")
            raise


# Convenience function for quick message sending
async def send_telegram_message(
    bot_token: str,
    chat_id: Union[int, str],
    text: str,
    parse_mode: Optional[str] = None,
    disable_web_page_preview: bool = False,
    disable_notification: bool = False,
    reply_to_message_id: Optional[int] = None,
    allow_sending_without_reply: bool = False,
) -> dict:
    """
    Convenience function to send a message to a Telegram chat.

    Args:
        bot_token (str): Telegram bot token
        chat_id (Union[int, str]): Unique identifier for the target chat
        or username of the target channel
        text (str): Text of the message to be sent
        parse_mode (Optional[str]): Mode for parsing entities
        in the message text disable_web_page_preview (bool): Disables link
        previews for links in this message disable_notification (bool):
        Sends the message silently reply_to_message_id (Optional[int]):
        If the message is a reply, ID of the original message
        allow_sending_without_reply (bool): Pass True if the message
        should be sent even if the specified replied-to message is not found

    Returns:
        dict: Response from Telegram API
    """
    sender = TelegramMessageSender(bot_token)
    return await sender.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode=parse_mode,
        disable_web_page_preview=disable_web_page_preview,
        disable_notification=disable_notification,
        reply_to_message_id=reply_to_message_id,
        allow_sending_without_reply=allow_sending_without_reply,
    )


# Async function to get chat information
async def get_chat_info(bot_token: str, chat_id: Union[int, str]) -> dict:
    """
    Get information about a specific chat.

    Args:
        bot_token (str): Telegram bot token
        chat_id (Union[int, str]): Unique identifier for the target chat
        or username of the target channel

    Returns:
        dict: Chat information from Telegram API
    """
    bot = Bot(token=bot_token)
    try:
        chat = await bot.get_chat(chat_id=chat_id)
        return chat.to_dict()
    except TelegramError as e:
        logger.error(f"Error getting chat info for {chat_id}: {e}")
        raise


# Async function to get chat members count
async def get_chat_members_count(
    bot_token: str, chat_id: Union[int, str]
) -> int:
    """
    Get the number of members in a chat.

    Args:
        bot_token (str): Telegram bot token
        chat_id (Union[int, str]): Unique identifier for the target chat
        or username of the target channel

    Returns:
        int: Number of members in the chat
    """
    bot = Bot(token=bot_token)
    try:
        count = await bot.get_chat_member_count(chat_id=chat_id)
        return count
    except TelegramError as e:
        logger.error(f"Error getting chat members count for {chat_id}: {e}")
        raise
