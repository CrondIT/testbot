"""Test script to demonstrate sending messages to selected chats in the existing bot."""
import asyncio
import os
from dotenv import load_dotenv

from send_message_utils import TelegramMessageSender
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# Load environment variables
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")  # Use the same token as in bot.py

# Global variable to store the message sender instance
message_sender = None


async def initialize_sender():
    """Initialize the message sender with the bot token."""
    global message_sender
    if not message_sender and TELEGRAM_BOT_TOKEN:
        message_sender = TelegramMessageSender(TELEGRAM_BOT_TOKEN)


async def send_to_chat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Command handler to send a message to a specified chat.
    Usage: /send_to_chat <chat_id> <message>
    """
    user_id = update.effective_user.id
    
    # Check if user is admin or authorized to send messages to other chats
    # For this example, we'll allow any user to try, but in production you'd want to check permissions
    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "Usage: /send_to_chat <chat_id> <message>\n"
            "Example: /send_to_chat 123456789 Hello from bot!"
        )
        return
    
    try:
        # Extract chat_id and message from command arguments
        chat_id = int(context.args[0])
        message = " ".join(context.args[1:])
        
        # Initialize the message sender if not already done
        await initialize_sender()
        
        if not message_sender:
            await update.message.reply_text("Bot token not configured properly.")
            return
        
        # Send the message to the specified chat
        response = await message_sender.send_message(
            chat_id=chat_id,
            text=f"Message from user {user_id}: {message}",
            disable_notification=False
        )
        
        await update.message.reply_text(f"Message sent successfully to chat {chat_id}!")
        
    except ValueError:
        await update.message.reply_text("Invalid chat ID. Please provide a numeric chat ID.")
    except Exception as e:
        await update.message.reply_text(f"Error sending message: {str(e)}")


async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Command handler to send a message to multiple chats.
    Usage: /broadcast <message>
    """
    user_id = update.effective_user.id
    
    # For this example, we'll define a list of allowed chat IDs
    # In a real implementation, you might fetch this from a database
    allowed_broadcast_chats = [user_id]  # Only send to the command issuer for demo
    
    if not context.args:
        await update.message.reply_text(
            "Usage: /broadcast <message>\n"
            "This will send the message to predefined chats."
        )
        return
    
    message = " ".join(context.args)
    
    # Initialize the message sender if not already done
    await initialize_sender()
    
    if not message_sender:
        await update.message.reply_text("Bot token not configured properly.")
        return
    
    success_count = 0
    failed_chats = []
    
    for chat_id in allowed_broadcast_chats:
        try:
            await message_sender.send_message(
                chat_id=chat_id,
                text=f"Broadcast from user {user_id}: {message}",
                disable_notification=False
            )
            success_count += 1
        except Exception as e:
            failed_chats.append((chat_id, str(e)))
    
    response_msg = f"Broadcast completed. Sent to {success_count} chat(s)."
    if failed_chats:
        response_msg += f"\nFailed chats: {failed_chats}"
    
    await update.message.reply_text(response_msg)


def main():
    """Run the test bot with send_to_chat functionality."""
    if not TELEGRAM_BOT_TOKEN:
        print("TELEGRAM_BOT_TOKEN not found in environment variables.")
        return
    
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Add command handlers
    app.add_handler(CommandHandler("send_to_chat", send_to_chat_command))
    app.add_handler(CommandHandler("broadcast", broadcast_command))
    
    print("Test bot started with send_to_chat functionality!")
    print("Use /send_to_chat <chat_id> <message> to send messages to specific chats")
    print("Use /broadcast <message> to send messages to multiple chats")
    
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()