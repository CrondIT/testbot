"""Example script demonstrating how to use the send_message_utils module."""
import asyncio
import os
from dotenv import load_dotenv
from send_message_utils import TelegramMessageSender, send_telegram_message

# Load environment variables
load_dotenv()

# Get bot token from environment variable
BOT_TOKEN = os.getenv("TELEGRAM_TOKEN2")

if not BOT_TOKEN:
    print("Error: TELEGRAM_TOKEN2 environment variable not set.")
    print("Please add your bot token to the .env file as TELEGRAM_TOKEN2='your_bot_token'")
    exit(1)

# Example chat ID - replace with actual chat ID
CHAT_ID = "YOUR_CHAT_ID_HERE"  # Can be user ID, group ID, or @channel_username


async def main():
    """Main function demonstrating the usage of the message sending utilities."""
    
    # Method 1: Using the TelegramMessageSender class
    print("Method 1: Using TelegramMessageSender class")
    sender = TelegramMessageSender(BOT_TOKEN)
    
    try:
        # Send a simple message
        response = await sender.send_message(
            chat_id=CHAT_ID,
            text="Hello from TelegramMessageSender class!",
            parse_mode=None
        )
        print(f"Message sent successfully: {response['message_id']}")
    except Exception as e:
        print(f"Error sending message: {e}")
    
    # Method 2: Using the convenience function
    print("\nMethod 2: Using send_telegram_message function")
    try:
        response = await send_telegram_message(
            bot_token=BOT_TOKEN,
            chat_id=CHAT_ID,
            text="Hello from convenience function!",
            parse_mode=None
        )
        print(f"Message sent successfully: {response['message_id']}")
    except Exception as e:
        print(f"Error sending message: {e}")
    
    # Method 3: Sending a long message
    print("\nMethod 3: Sending a long message")
    long_text = "This is a very long message. " * 500  # Creating a long text
    try:
        responses = await sender.send_message(
            chat_id=CHAT_ID,
            text=long_text,
            parse_mode=None
        )
        if isinstance(responses, list):
            print(f"Long message sent in {len(responses)} parts")
        else:
            print(f"Long message sent successfully: {responses['message_id']}")
    except Exception as e:
        print(f"Error sending long message: {e}")
    
    # Method 4: Sending a message with Markdown formatting
    print("\nMethod 4: Sending a message with Markdown formatting")
    try:
        response = await sender.send_message(
            chat_id=CHAT_ID,
            text="*Bold text* and _italic text_ using MarkdownV2",
            parse_mode="MarkdownV2"
        )
        print(f"Formatted message sent successfully: {response['message_id']}")
    except Exception as e:
        print(f"Error sending formatted message: {e}")
    
    # Method 5: Getting chat information
    print("\nMethod 5: Getting chat information")
    try:
        from send_message_utils import get_chat_info, get_chat_members_count
        
        chat_info = await get_chat_info(BOT_TOKEN, CHAT_ID)
        print(f"Chat info: {chat_info}")
        
        # Only get member count for groups/channels
        if chat_info.get('type') in ['group', 'supergroup']:
            members_count = await get_chat_members_count(BOT_TOKEN, CHAT_ID)
            print(f"Members count: {members_count}")
    except Exception as e:
        print(f"Error getting chat info: {e}")


if __name__ == "__main__":
    # Replace 'YOUR_CHAT_ID_HERE' with an actual chat ID before running
    if CHAT_ID == "YOUR_CHAT_ID_HERE":
        print("Please replace 'YOUR_CHAT_ID_HERE' with an actual chat ID before running this script.")
        print("You can get your chat ID by:")
        print("1. Sending a message to @userinfobot in Telegram")
        print("2. Or by using the bot to get updates from a group/channel")
        print("3. Or by checking the chat ID in your bot logs")
    else:
        asyncio.run(main())