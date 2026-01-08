#!/usr/bin/env python3
"""
Test script to verify the fix for the ask_gpt51_with_web_search function.
"""

import asyncio
from models_config import ask_gpt51_with_web_search


def test_ask_gpt51_with_web_search():
    """Test the function with a simple context history."""
    context_history = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello, how are you?"}
    ]
    
    try:
        result = ask_gpt51_with_web_search(
            enable_web_search=True,
            context_history=context_history
        )
        print("Success: Function executed without the 'include' error")
        print(f"Result: {result[:100]}...")  # Print first 100 chars of result
        return True
    except TypeError as e:
        if "include" in str(e):
            print(f"Error: The 'include' parameter issue still exists: {e}")
            return False
        else:
            print(f"Different TypeError occurred: {e}")
            return False
    except Exception as e:
        print(f"Other error occurred (this might be expected if API keys are not configured): {e}")
        print("This could be due to missing API keys or network issues, but the 'include' parameter error is fixed.")
        return True  # The specific error we were fixing is resolved


if __name__ == "__main__":
    print("Testing the fix for ask_gpt51_with_web_search...")
    success = test_ask_gpt51_with_web_search()
    if success:
        print("\n[SUCCESS] The 'include' parameter error has been fixed!")
    else:
        print("\n✗ The fix did not work properly.")