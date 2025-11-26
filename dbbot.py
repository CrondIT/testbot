import os
import psycopg2
from datetime import datetime
from dotenv import load_dotenv

# Загрузить переменные из файла .env
load_dotenv()

DBNAME = os.getenv("POSTGRES_DB")
DBUSER = os.getenv("POSTGRES_USER")
DBPASSWORD = os.getenv("POSTGRES_PASSWORD")
DBPORT = os.getenv("POSTGRES_PORT")
DBHOST = os.getenv("POSTGRES_HOST")


def create_database():

    if not all([DBNAME, DBUSER, DBPASSWORD, DBPORT, DBHOST]):
        print("Ошибка: Не все переменные окружения установлены.")
        return

    try:
        # Подключение к существующей базе данных
        conn = psycopg2.connect(
            dbname=DBNAME,
            user=DBUSER,
            password=DBPASSWORD,
            host=DBHOST,
            port=DBPORT,
            client_encoding='utf8'
            )

        cur = conn.cursor()

        # Выполнение SQL-запроса
        cur.execute("SELECT version();")
        version = cur.fetchone()
        cur.execute('''
            CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            userid INTEGER UNIQUE NOT NULL,
            nickname VARCHAR(20),
            startdate TIMESTAMP,
            coindate TIMESTAMP,
            coins INTEGER,
            giftdate TIMESTAMP,
            giftcoins INTEGER
            );
        ''')
        conn.commit()

        # Получение результата запроса
        print(version)
        cur.close()
        conn.close()

    except psycopg2.OperationalError as e:
        print(f"Ошибка подключения к базе данных: {e}")
    except Exception as e:
        print(f"Произошла ошибка: {e}")


def check_user(userid):
    """
    Проверяет, существует ли пользователь с заданным userid в таблице users.
    Возвращает True, если пользователь найден, иначе False.
    """
    try:
        with psycopg2.connect(
            dbname=DBNAME,
            user=DBUSER,
            password=DBPASSWORD,
            host=DBHOST,
            port=DBPORT
        ) as conn:
            with conn.cursor() as cur:
                # Выполняем запрос: проверяем, есть ли запись с таким userid
                cur.execute(
                    "SELECT 1 FROM users WHERE userid = %s LIMIT 1;",
                    (userid,)
                    )
                result = cur.fetchone()
                # Если вернулась хотя бы одна строка — пользователь существует
                return result is not None

    except psycopg2.Error as e:
        print(f"Ошибка при работе с PostgreSQL: {e}")
        return False


def create_user(userid, nickname, coins, giftcoins):
    """
    Создаёт пользователя в таблице users.
    В поля startdate и giftdate заносится текущее время.
    Возвращает True при успехе, False — при ошибке.
    """
    try:
        with psycopg2.connect(
            dbname=DBNAME,
            user=DBUSER,
            password=DBPASSWORD,
            host=DBHOST,
            port=DBPORT
        ) as conn:
            with conn.cursor() as cur:
                # Текущее время
                now = datetime.now()

                # Вставляем новую запись
                cur.execute(
                    """
                    INSERT INTO users (
                        userid, startdate, giftdate, coindate,
                        nickname, coins, giftcoins
                        )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (userid, now, now, now, nickname, coins, giftcoins)
                )
                conn.commit()
                print(f"Пользователь {userid} успешно создан.")
                return True

    except psycopg2.IntegrityError as e:
        # Например, если пользователь с таким userid уже существует
        print(f"Ошибка: пользователь с userid={userid} уже существует. {e}")
        return False

    except psycopg2.Error as e:
        # Любая другая ошибка (проблемы с подключением, таблицей и т.д.)
        print(f"Ошибка при работе с базой данных: {e}")
        return False


def get_user(userid):
    """
    Извлекает данные пользователя из таблицы users по userid.
    Возвращает словарь с данными или None, если пользователь не найден.
    """
    if not check_user(userid):
        create_user(userid, "User", 0, 1)
    try:
        with psycopg2.connect(
            dbname=DBNAME,
            user=DBUSER,
            password=DBPASSWORD,
            host=DBHOST,
            port=DBPORT
        ) as conn:
            with conn.cursor() as cur:
                # Выполняем запрос
                cur.execute("""
                    SELECT id, userid, nickname, startdate, coindate,
                           coins, giftdate, giftcoins
                    FROM users
                    WHERE userid = %s;
                """, (userid,)
                )

                row = cur.fetchone()

                # Если пользователь найден — возвращаем данные в виде словаря
                if row:
                    return {
                        "id": row[0],
                        "userid": row[1],
                        "nickname": row[2],
                        "startdate": row[3],
                        "coindate": row[4],
                        "coins": row[5],
                        "giftdate": row[6],
                        "giftcoins": row[7]
                    }
                else:
                    return None  # Пользователь не найден

    except psycopg2.Error as e:
        print(f"Ошибка при работе с базой данных: {e}")
        return None


def add_coins(userid: int, coins_to_add: int) -> bool:
    """
    Обновляет количество coins и устанавливает coindate в текущее время
    для пользователя с заданным userid.
    Возвращает True при успехе, False — при ошибке.
    """
    try:
        with psycopg2.connect(
            dbname=DBNAME,
            user=DBUSER,
            password=DBPASSWORD,
            host=DBHOST,
            port=DBPORT
        ) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE users
                    SET coins = coins + %s,
                        coindate = %s
                    WHERE userid = %s;
                """, (coins_to_add, datetime.now(), userid))

                # Проверим, была ли обновлена хотя бы одна строка
                if cur.rowcount == 0:
                    print(f"Пользователь с userid={userid} не найден.")
                    return False

                conn.commit()
                print(f"Данные пользователя {userid} успешно обновлены.")
                return True

    except psycopg2.Error as e:
        print(f"Ошибка при обновлении данных: {e}")
        return False


def add_giftcoins(userid: int, coins_to_add: int) -> bool:
    """
    Обновляет количество coins и устанавливает coindate в текущее время
    для пользователя с заданным userid.
     Возвращает True при успехе, False — при ошибке.
    """
    try:
        with psycopg2.connect(
            dbname=DBNAME,
            user=DBUSER,
            password=DBPASSWORD,
            host=DBHOST,
            port=DBPORT
        ) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE users
                    SET giftcoins = giftcoins + %s,
                        giftdate = %s
                    WHERE userid = %s;
                """, (coins_to_add, datetime.now(), userid))

                # Проверим, была ли обновлена хотя бы одна строка
                if cur.rowcount == 0:
                    print(f"Пользователь с userid={userid} не найден.")
                    return False

                conn.commit()
                print(f"Данные пользователя {userid} успешно обновлены.")
                return True

    except psycopg2.Error as e:
        print(f"Ошибка при обновлении данных: {e}")
        return False


def get_user_coins(userid: int) -> dict:
    """
    Получает количество монет пользователя (обычные + подарочные).
    Возвращает словарь с информацией о монетах или None,
    если пользователь не найден.
    """
    user_data = get_user(userid)
    if user_data:
        return {
            "coins": user_data["coins"],
            "giftcoins": user_data["giftcoins"],
            "total": user_data["coins"] + user_data["giftcoins"],
            "coindate": user_data["coindate"]
        }
    return None
