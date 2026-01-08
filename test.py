import token_utils

str = "hello gpt-5.1-mini"

print(token_utils.count_tokens(str, "gpt-3.5-turbo"))
