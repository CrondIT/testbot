import os
import requests
from datetime import datetime
from dotenv import load_dotenv

# Загрузить переменные из файла .env
load_dotenv()

# Настройки
API_KEY = os.getenv("OPENAI_API_KEY")


def get_billing_usage():
    url = "https://api.openai.com/v1/usage"
    headers = {
        "Authorization": f"Bearer {API_KEY}"
    }
    # Расчет периода (начало текущего месяца до текущего дня)
    today = datetime.now()
    start_date = today.replace(day=1).strftime("%Y-%m-%d")
    end_date = today.strftime("%Y-%m-%d")
    params = {
        "start_date": start_date,
        "end_date": end_date
    }
    response = requests.get(url, headers=headers, params=params)
    if response.status_code == 200:
        data = response.json()
        total_usage = 0
        # Суммируем использование в долларах
        for day in data.get("data", []):
            total_usage += day.get("total_usage_usd", 0)
        return total_usage
    else:
        raise Exception(
            f"Ошибка запроса: {response.status_code} - {response.text}"
            )


def get_subscription_info():
    url = "https://api.openai.com/v1/dashboard/billing/subscription"
    headers = {
        "Authorization": f"Bearer {API_KEY}"
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json()
    else:
        raise Exception(
            f"Ошибка запроса: {response.status_code} - {response.text}"
            )


def main():
    # Получаем информацию о подписке
    subscription = get_subscription_info()
    hard_limit_usd = subscription.get("hard_limit_usd", 0)  # Общий лимит
    # soft_limit_usd = subscription.get("soft_limit_usd", 0)  # Текущий порог

    # Получаем текущее использование
    current_usage = get_billing_usage()
    remaining_balance = max(0, hard_limit_usd - current_usage)

    print(f"Текущий лимит: ${hard_limit_usd:.2f}")
    print(f"Использовано: ${current_usage:.2f}")
    print(f"Остаток средств: ${remaining_balance:.2f}")


if __name__ == "__main__":
    main()
