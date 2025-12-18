"""Utility functions for coin management and user balance operations."""

import dbbot
import models_config


def spend_coins(
    user_id: int,
    cost: int,
    coins: int,
    giftcoins: int,
    current_mode,
    user_message,
    reply,
):
    """--- ✅ Списываем монеты и записываем лог ---
    Если основных монет не хватило — списываем из подарочных
    """
    balance = coins + giftcoins
    remaining_cost = cost
    if coins >= remaining_cost:
        dbbot.change_all_coins(user_id, -remaining_cost, 0)
    else:
        # Сначала списываем с основных
        remaining_cost -= coins
        dbbot.change_all_coins(user_id, -coins, -remaining_cost)
    # --- ✅ СПИСАНИЕ ЗАВЕРШЕНО ---
    balance = balance - cost
    # LOGGING ====================
    log_text = f""" Запрос: {user_message}
        Ответ: {reply}
        """
    dbbot.log_action(user_id, current_mode, log_text, -cost, balance)


async def check_user_coins(user_id: int, current_mode: str, context) -> tuple:
    """
    Проверяет наличие монет у пользователя.
    Возвращает (user_data, coins, giftcoins, balance, cost)
    или (None, 0, 0, 0, 0) если проверка не пройдена.
    """
    # Определяем стоимость в зависимости от режима
    cost = models_config.COST_PER_MESSAGE.get(current_mode)
    # Получаем данные пользователя
    user_data = dbbot.get_user(user_id)
    if not user_data:
        return None, 0, 0, 0, 0

    # Считаем общее количество монет
    coins = user_data["coins"]
    giftcoins = user_data["giftcoins"]
    balance = coins + giftcoins
    # Проверяем, хватает ли монет
    if balance < cost:
        # LOGGING ====================
        log_text = f""" У пользователя недостаточно средств
            Режим: {current_mode}
            Стоимость: {cost}
            Баланс: {balance}
            """
        dbbot.log_action(user_id, current_mode, log_text, 0, balance)
        await context.bot.send_message(
            chat_id=user_id,
            text=(
                f"⚠️ У вас недостаточно монет. "
                f"Стоимость запроса: {cost} монет.\n"
                f"Ваш баланс: {balance} монет.\n"
                f"Пополните счёт в /billing"
            ),
        )
        # ❌ Прерываем выполнение, если монет не хватает
        return None, 0, 0, 0, 0

    return user_data, coins, giftcoins, balance, cost
