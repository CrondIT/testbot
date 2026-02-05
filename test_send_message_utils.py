"""Simple test for the send_message_utils module."""
import unittest
from unittest.mock import AsyncMock, patch
from send_message_utils import TelegramMessageSender


class TestTelegramMessageSender(unittest.IsolatedAsyncioTestCase):
    """Test cases for TelegramMessageSender class."""
    
    def setUp(self):
        """Set up test fixtures before each test method."""
        self.sender = TelegramMessageSender("fake_token")
    
    @patch('send_message_utils.Bot')
    async def test_send_message_success(self, mock_bot_class):
        """Test successful message sending."""
        # Mock the bot instance and its send_message method
        mock_bot_instance = AsyncMock()
        mock_response = AsyncMock()
        mock_response.to_dict.return_value = {'message_id': 123, 'text': 'Hello'}
        mock_bot_instance.send_message.return_value = mock_response
        mock_bot_class.return_value = mock_bot_instance
        
        # Call the method
        result = await self.sender.send_message(chat_id=12345, text="Hello")
        
        # Assertions
        self.assertEqual(result, {'message_id': 123, 'text': 'Hello'})
        mock_bot_instance.send_message.assert_called_once_with(
            chat_id=12345,
            text="Hello",
            parse_mode=None,
            disable_web_page_preview=False,
            disable_notification=False,
            reply_to_message_id=None,
            allow_sending_without_reply=False
        )
    
    @patch('send_message_utils.Bot')
    async def test_send_long_message(self, mock_bot_class):
        """Test sending a long message that needs to be split."""
        # Create a long text that exceeds Telegram's limit
        long_text = "A" * 5000  # More than 4096 characters
        
        # Mock the bot instance and its send_message method
        mock_bot_instance = AsyncMock()
        mock_response = AsyncMock()
        mock_response.to_dict.return_value = {'message_id': 123, 'text': 'Part'}
        mock_bot_instance.send_message.return_value = mock_response
        mock_bot_class.return_value = mock_bot_instance
        
        # Call the method
        result = await self.sender.send_message(chat_id=12345, text=long_text)
        
        # Check that send_message was called multiple times for the long message
        self.assertTrue(len(mock_bot_instance.send_message.call_args_list) > 1)
    
    @patch('send_message_utils.Bot')
    async def test_send_photo(self, mock_bot_class):
        """Test sending a photo."""
        # Mock the bot instance and its send_photo method
        mock_bot_instance = AsyncMock()
        mock_response = AsyncMock()
        mock_response.to_dict.return_value = {'message_id': 124, 'photo': 'photo_data'}
        mock_bot_instance.send_photo.return_value = mock_response
        mock_bot_class.return_value = mock_bot_instance
        
        # Call the method
        result = await self.sender.send_photo(chat_id=12345, photo="photo.jpg", caption="Nice photo")
        
        # Assertions
        self.assertEqual(result, {'message_id': 124, 'photo': 'photo_data'})
        mock_bot_instance.send_photo.assert_called_once_with(
            chat_id=12345,
            photo="photo.jpg",
            caption="Nice photo",
            parse_mode=None,
            disable_notification=False,
            reply_to_message_id=None,
            allow_sending_without_reply=False
        )


if __name__ == '__main__':
    unittest.main()