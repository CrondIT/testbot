"""Simple example showing how to use the send_message_utils module."""
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

async def example_usage():
    """Example of how to use the send_message_utils module."""
    print("Creating message sender...")
    sender = TelegramMessageSender(BOT_TOKEN)
    
    # Example chat ID - replace with actual chat ID
    chat_id = input("Enter chat ID to send message to: ")
    
    try:
        # Example 1: Send a simple message
        print("\n1. Sending a simple message...")
        response = await sender.send_message(
            chat_id=chat_id,
            text="Hello from the send_message_utils module!",
            parse_mode=None
        )
        print(f"Message sent successfully! Message ID: {response.get('message_id', 'Unknown')}")
        
        # Example 2: Send a message with Markdown formatting
        print("\n2. Sending a formatted message...")
        formatted_text = "*Bold text* and _italic text_ using MarkdownV2"
        response = await sender.send_message(
            chat_id=chat_id,
            text=formatted_text,
            parse_mode="MarkdownV2"
        )
        print(f"Formatted message sent successfully! Message ID: {response.get('message_id', 'Unknown')}")
        
        # Example 3: Send a long message (will be split automatically)
        print("\n3. Sending a long message...")
        long_text = "This is a very long message. " * 500  # Creating a long text
        response = await sender.send_message(
            chat_id=chat_id,
            text=long_text,
            parse_mode=None
        )
        print(f"Long message sent successfully!")
        
        # Example 4: Using the convenience function
        print("\n4. Using convenience function...")
        response = await send_telegram_message(
            bot_token=BOT_TOKEN,
            chat_id=chat_id,
            text="This message was sent using the convenience function!",
            parse_mode=None
        )
        print(f"Convenience function message sent successfully! Message ID: {response.get('message_id', 'Unknown')}")
        
    except Exception as e:
        print(f"An error occurred: {e}")
        print("Make sure:")
        print("- Your bot token is correct")
        print("- The chat ID exists and the bot has permission to send messages there")
        print("- Your internet connection is working")

if __name__ == "__main__":
    asyncio.run(example_usage())