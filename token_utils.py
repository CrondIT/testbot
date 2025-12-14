import tiktoken

# import google.generativeai as genai
from typing import List, Dict, Any


class TokenCounter:
    """
    Utility class to count tokens for different AI models
    """

    def __init__(self):
        # Initialize encoders for OpenAI models
        self.openai_encoders = {}

    def count_openai_tokens(
        self,
        text: str,
        model: str
    ) -> int:
        """
        Count tokens for OpenAI models using tiktoken
        """
        try:
            if model not in self.openai_encoders:
                self.openai_encoders[model] = tiktoken.encoding_for_model(
                    model
                )
            encoder = self.openai_encoders[model]
            return len(encoder.encode(text))
        except Exception as e:
            # Fallback: rough estimation (1 token ~ 4 characters)
            print(f"Ошибка count_openai_tokens: {e}")
            return len(text) // 4

    def count_openai_messages_tokens(
        self,
        messages: List[Dict],
        model: str
    ) -> int:
        try:
            # Для новых моделей использовать "cl100k_base"
            if "gpt-4" in model or "gpt-3.5" in model or "gpt-5" in model:
                encoding = tiktoken.get_encoding("cl100k_base")
            else:
                encoding = tiktoken.encoding_for_model(model)
        except Exception as e:
            print(f"Ошибка count_openai_messages_tokens: {e}")
            encoding = tiktoken.get_encoding("cl100k_base")

        tokens_per_message = 3  # <|start|>{role}|<|message|>{content}|<|end|>
        tokens_per_name = 1

        total_tokens = 0
        for message in messages:
            total_tokens += tokens_per_message
            for key, value in message.items():
                if isinstance(value, str):
                    total_tokens += len(encoding.encode(value))
                elif isinstance(value, list):
                    # Если content — список (например, текст + изображение)
                    for item in value:
                        if isinstance(item, dict):
                            if "text" in item:
                                total_tokens += len(
                                    encoding.encode(item["text"])
                                    )
                            # изображения: не кодируются напрямую
                if key == "name":
                    total_tokens += tokens_per_name
        total_tokens += 3  # <|end|> в конце
        return total_tokens

    def estimate_gemini_tokens(self, text: str) -> int:
        """
        Estimate tokens for Gemini models
        (Google doesn't provide exact count without API call)
        Using rough estimation: 1 token ~ 4 characters
        """
        return len(text) // 4

    def estimate_gemini_image_tokens(self, image_bytes: bytes) -> int:
        """
        Estimate tokens for images in Gemini (rough estimation)
        """
        # Images take more tokens, using a rough estimation
        return min(len(image_bytes) // 250, 200)  # Max 200 tokens for images


# Create a global instance
token_counter = TokenCounter()


def get_token_limit(model_name: str) -> int:
    """
    Get the maximum token limit for a specific model
    """
    limits = {
        # OpenAI models
        "gpt-5.1": 128000,
        "gpt-4o-mini": 128000,
        "gpt-4-turbo": 128000,
        "gpt-4o": 128000,
        "gpt-4": 8192,
        "gpt-3.5-turbo": 16385,
        # DALL-E models
        "dall-e-3": 4096,  # Prompt length limit
        # Gemini models
        "gemini-2.5-flash-preview-image": 1048576,
        "gemini-2.5-pro": 2097152,
        "gemini-2.0-flash-exp": 1048576,
        "gemini-1.5-pro": 1048576,
        "gemini-1.0-pro": 32768,
    }

    return limits.get(model_name, 4096)  # Default fallback


def truncate_messages_for_token_limit(
    messages: List[Dict[str, str]],
    model: str,
    max_tokens: int = None,
    reserve_tokens: int = 1000,
) -> List[Dict[str, str]]:
    """
    Truncate messages to fit within token limit
    """
    if max_tokens is None:
        max_tokens = get_token_limit(model)

    # Reserve some tokens for response
    available_tokens = max_tokens - reserve_tokens

    if available_tokens <= 0:
        return []

    # First check if the full message list fits
    total_tokens = token_counter.count_openai_messages_tokens(messages, model)

    if total_tokens <= available_tokens:
        return messages

    # If not, we need to truncate
    # Keep the system message if present,
    # and remove oldest user/assistant pairs
    if not messages:
        return []

    # Separate system message from conversation
    system_message = None
    conversation_messages = []

    for msg in messages:
        if msg.get("role") == "system":
            if system_message is None:
                system_message = msg
        else:
            conversation_messages.append(msg)

    # Count tokens in system message
    system_tokens = 0
    if system_message:
        system_tokens = token_counter.count_openai_messages_tokens(
            [system_message], model
        )

    available_for_conversation = available_tokens - system_tokens

    # Start from the end and keep the most recent messages
    truncated_conversation = []
    current_tokens = 0

    # Go through messages from newest to oldest
    for msg in reversed(conversation_messages):
        msg_tokens = token_counter.count_openai_messages_tokens([msg], model)

        if current_tokens + msg_tokens <= available_for_conversation:
            # Insert next string at beginning to maintain order
            truncated_conversation.insert(0, msg)
            current_tokens += msg_tokens
        else:
            break  # Can't fit more messages

    # Combine system message with truncated conversation
    result = []
    if system_message:
        result.append(system_message)
    result.extend(truncated_conversation)

    return result


def check_token_usage(
    messages: List[Dict[str, str]],
    model: str,
    max_tokens: int = None,
    reserve_tokens: int = 1000,
) -> Dict[str, Any]:
    """
    Check token usage and return information about it
    """
    if max_tokens is None:
        max_tokens = get_token_limit(model)

    available_tokens = max_tokens - reserve_tokens
    total_tokens = token_counter.count_openai_messages_tokens(messages, model)

    return {
        "total_tokens": total_tokens,
        "max_tokens": max_tokens,
        "available_tokens": available_tokens,
        "reserve_tokens": reserve_tokens,
        "is_within_limit": total_tokens <= available_tokens,
        "excess_tokens": max(0, total_tokens - available_tokens),
    }
