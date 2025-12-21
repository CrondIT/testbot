import token_utils

str = "hello gpt-5.1-mini"
print(str)
if "gpt-4" in str or "gpt-3.5" in str or "gpt-5" in str:
    print("yes")
else:
    print("no")

print(token_utils.get_token_limit("gpt-7.1"))
