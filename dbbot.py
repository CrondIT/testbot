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
            client_encoding="utf8",
        )

        cur = conn.cursor()

        # Создание таблицы users
        cur.execute("SELECT version();")
        version = cur.fetchone()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            userid INTEGER UNIQUE NOT NULL,
            nickname VARCHAR(20),
            startdate TIMESTAMP,
            coindate TIMESTAMP,
            coins INTEGER,
            giftdate TIMESTAMP,
            giftcoins INTEGER,
            note VARCHAR(100)
            );
        """
        )

        # ✅ Создание таблицы logs с внешним ключом
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS logs (
            id SERIAL PRIMARY KEY,
            userid BIGINT NOT NULL,
            datetime TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            mode VARCHAR(20),
            event VARCHAR(10),
            text TEXT NOT NULL,
            cost INTEGER,
            balance INTEGER,
            note VARCHAR(100),
            FOREIGN KEY (userid) REFERENCES users (userid) ON DELETE CASCADE
            );
        """
        )

        # Создание системного пользователя с userid=0, если он не существует
        cur.execute(
            """
            INSERT INTO users (
                userid, nickname, startdate, coindate,
                coins, giftdate, giftcoins, note
            )
            VALUES (
                0, 'System', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 0,
                CURRENT_TIMESTAMP, 0, 'System user for logging'
            )
            ON CONFLICT (userid) DO NOTHING;
        """
        )

        conn.commit()
        print("✅ Таблицы 'users' и 'logs' созданы или существуют. ", version)
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
            port=DBPORT,
        ) as conn:
            with conn.cursor() as cur:
                # Выполняем запрос: проверяем, есть ли запись с таким userid
                cur.execute(
                    "SELECT 1 FROM users WHERE userid = %s LIMIT 1;", (userid,)
                )
                result = cur.fetchone()
                # Если вернулась хотя бы одна строка — пользователь существует
                return result is not None

    except psycopg2.Error as e:
        print(f"Ошибка при работе с PostgreSQL: {e}")
        return False


def create_user(userid, nickname, coins, giftcoins, note=None):
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
            port=DBPORT,
        ) as conn:
            with conn.cursor() as cur:
                # Текущее время
                now = datetime.now()

                # Вставляем новую запись
                cur.execute(
                    """
                    INSERT INTO users (
                        userid, startdate, giftdate, coindate,
                        nickname, coins, giftcoins, note
                        )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (userid, now, now, now, nickname, coins, giftcoins, note),
                )
                conn.commit()
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
            port=DBPORT,
        ) as conn:
            with conn.cursor() as cur:
                # Выполняем запрос
                cur.execute(
                    """
                    SELECT id, userid, nickname, startdate, coindate,
                           coins, giftdate, giftcoins, note
                    FROM users
                    WHERE userid = %s;
                """,
                    (userid,),
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
                        "giftcoins": row[7],
                        "note": row[8],
                    }
                else:
                    return None  # Пользователь не найден

    except psycopg2.Error as e:
        print(f"Ошибка при работе с базой данных: {e}")
        return None


def change_all_coins(userid: int, coins: int, giftcoins: int) -> bool:
    """
    Обновляет количество coins giftcoins
    и устанавливает coindate в текущее время
    для пользователя с заданным userid.
    Возвращает True при успехе, False — при ошибке.
    """
    try:
        with psycopg2.connect(
            dbname=DBNAME,
            user=DBUSER,
            password=DBPASSWORD,
            host=DBHOST,
            port=DBPORT,
        ) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE users
                    SET coins = coins + %s,
                        giftcoins = giftcoins + %s,
                        coindate = %s
                    WHERE userid = %s;
                """,
                    (coins, giftcoins, datetime.now(), userid),
                )

                # Проверим, была ли обновлена хотя бы одна строка
                if cur.rowcount == 0:
                    return False

                conn.commit()
                return True

    except psycopg2.Error as e:
        print(f"Ошибка при обновлении данных: {e}")
        return False


def log_action(userid, mode, text, cost, balance, event="info", note=None):
    """
    Добавляет запись в таблицу logs.
    :param userid: ID пользователя
    :param text: Текст действия (например, "Запрос к ИИ",
    "Генерация изображения")
    """
    try:
        with psycopg2.connect(
            dbname=DBNAME,
            user=DBUSER,
            password=DBPASSWORD,
            host=DBHOST,
            port=DBPORT,
        ) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO logs (
                        userid, mode, event, text, cost, balance, note
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (userid, mode, event, text, cost, balance, note),
                )
                conn.commit()
    except psycopg2.Error as e:
        print(f"Ошибка при записи в лог: {e}")
