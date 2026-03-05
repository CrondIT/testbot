# Бот с очередями Redis — Инструкция по запуску в Ubuntu

## Быстрый старт

```bash
# 1. Установка зависимостей
./install.sh

# 2. Настройка конфигурации
cp .env.example .env
nano .env  # отредактируйте токены и настройки

# 3. Запуск бота
./start_bot.sh

# 4. Подключение к сессии tmux
./start_bot.sh attach
```

---

## Требования

- Ubuntu 20.04+ (или другой Linux)
- Python 3.8+
- Redis сервер (локальный или удалённый)
- PostgreSQL (для хранения данных пользователей)

---

## Установка

### 1. Автоматическая установка

```bash
chmod +x install.sh start_bot.sh
./install.sh
```

Скрипт:
- Проверит наличие Python
- Установит tmux (если нет)
- Создаст виртуальное окружение `.venv`
- Установит все зависимости из `requirements.txt`

### 2. Ручная установка

```bash
# Установите системные пакеты
sudo apt update
sudo apt install python3 python3-pip python3-venv tmux -y

# Создайте виртуальное окружение
python3 -m venv .venv

# Активируйте
source .venv/bin/activate

# Установите зависимости
pip install -r requirements.txt
```

---

## Настройка

### 1. Копирование .env

```bash
cp .env.example .env
```

### 2. Редактирование .env

Откройте `.env` и установите:

```env
# Telegram
TELEGRAM_TOKEN2=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
TELEGRAM_CHAT_ID=123456789

# OpenAI
OPENAI_API_KEY=sk-proj-xxxxxxxxxxxxx
OPENAI_API_KEY_IMAGE=sk-proj-yyyyyyyyyyyyy

# Google Gemini
GEMINI_API_KEY=AIzaSyxxxxxxxxxxxxxxxxx

# PostgreSQL
POSTGRES_DB=botdb
POSTGRES_USER=botuser
POSTGRES_PASSWORD=secret123
POSTGRES_HOST=localhost
POSTGRES_PORT=5432

# Redis (включить для очередей)
USE_REDIS=true
REDIS_HOST=192.168.1.100  # адрес вашего Redis сервера
REDIS_PORT=6379
REDIS_PASSWORD=          # если есть пароль
```

---

## Запуск

### Вариант 1: Через start_bot.sh (рекомендуется)

```bash
# Запуск всех компонентов
./start_bot.sh

# Показать статус
./start_bot.sh status

# Показать логи
./start_bot.sh logs

# Подключиться к сессии tmux
./start_bot.sh attach

# Отцепиться от сессии
# Внутри tmux: Ctrl+B, D

# Остановить всё
./start_bot.sh stop

# Перезапустить
./start_bot.sh restart
```

### Вариант 2: Ручной запуск в tmux

```bash
# Создать сессию
tmux new -s bot

# Запустить воркеры (в разных панелях)
python worker.py --id 0
python worker.py --id 1

# Запустить listener (в новом окне)
# Ctrl+B, C — новое окно
python redis_listener.py

# Запустить бот (в новом окне)
# Ctrl+B, C
python bot.py

# Отцепиться: Ctrl+B, D
```

### Вариант 3: Без Redis (локальный режим)

В `.env` установите:
```env
USE_REDIS=false
```

Запустите только бота:
```bash
python bot.py
```

---

## Структура проекта

```
bot/
├── bot.py              # Основной бот (Telegram polling)
├── worker.py           # Воркер обработки задач
├── redis_listener.py   # Слушатель результатов
├── redis_queue.py      # Модуль работы с очередями
├── redis_config.py     # Конфигурация Redis
├── global_state.py     # Состояние пользователей (Redis + память)
├── start_bot.sh        # Скрипт запуска
├── install.sh          # Скрипт установки
├── .env                # Конфигурация (не в git!)
├── .env.example        # Шаблон конфигурации
└── requirements.txt    # Зависимости Python
```

---

## Управление процессами

### start_bot.sh команды

| Команда | Описание |
|---------|----------|
| `./start_bot.sh` | Запуск всех компонентов |
| `./start_bot.sh stop` | Остановка |
| `./start_bot.sh restart` | Перезапуск |
| `./start_bot.sh status` | Показать статус |
| `./start_bot.sh logs` | Показать логи |
| `./start_bot.sh attach` | Подключиться к tmux |
| `./start_bot.sh help` | Справка |

### tmux команды

| Клавиши | Описание |
|---------|----------|
| `Ctrl+B, W` | Список окон |
| `Ctrl+B, N` | Следующее окно |
| `Ctrl+B, P` | Предыдущее окно |
| `Ctrl+B, %` | Разделить вертикально |
| `Ctrl+B, "` | Разделить горизонтально |
| `Ctrl+B, стрелки` | Переключение между панелями |
| `Ctrl+B, D` | Отцепиться от сессии |
| `Ctrl+B, [` | Режим копирования |

---

## Мониторинг

### Проверка процессов

```bash
# Процессы Python
ps aux | grep -E "(bot\.py|worker\.py|redis_listener\.py)"

# Сессии tmux
tmux list-sessions

# Окна в сессии
tmux list-windows -t bot
```

### Логи

```bash
# Логи файлов
tail -f worker.log
tail -f redis_listener.log

# Логи tmux (буфер)
tmux capture-pane -t bot:0 -p
```

### Redis

```bash
# Подключиться к Redis
redis-cli -h <host> -p <port> -a <password>

# Размер очереди
redis-cli LLEN bot:queue:chat

# Ключи пользователей
redis-cli KEYS "bot:user:*"

# Статистика
redis-cli INFO stats
```

---

## Troubleshooting

### Ошибка: "tmux not found"

```bash
sudo apt install tmux -y
```

### Ошибка: "ModuleNotFoundError: No module named 'redis'"

```bash
source .venv/bin/activate
pip install -r requirements.txt
```

### Ошибка: "Connection refused" к Redis

1. Проверьте доступность сервера:
   ```bash
   telnet <redis_host> 6379
   ```

2. Проверьте настройки в `.env`:
   ```env
   REDIS_HOST=<правильный_адрес>
   REDIS_PASSWORD=<правильный_пароль>
   ```

### Бот не отвечает

```bash
# Проверьте логи
./start_bot.sh logs

# Проверьте статус
./start_bot.sh status

# Перезапустите
./start_bot.sh restart
```

### Зависла сессия tmux

```bash
# Убить сессию
tmux kill-session -t bot

# Запустить заново
./start_bot.sh
```

---

## Автозапуск при загрузке (systemd)

См. `REDIS_QUEUE_README.md` для настройки systemd сервисов.

---

## Безопасность

1. **Не коммитьте `.env`** в git:
   ```bash
   echo ".env" >> .gitignore
   ```

2. **Используйте пароль для Redis**:
   ```env
   REDIS_PASSWORD=strong_password_here
   ```

3. **Ограничьте доступ к Redis** по IP в конфиге Redis:
   ```
   bind 127.0.0.1
   protected-mode yes
   ```

4. **Используйте SSL для Redis** (если удалённый):
   ```env
   REDIS_SSL=true
   ```

---

## Поддержка

- Документация: `REDIS_QUEUE_README.md`
- Логи: `worker.log`, `redis_listener.log`
