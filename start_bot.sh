#!/bin/bash
#
# start_bot.sh — Скрипт запуска бота с очередями Redis
#
# Использование:
#   ./start_bot.sh          — запуск всех компонентов
#   ./start_bot.sh stop     — остановка всех компонентов
#   ./start_bot.sh status   — показать статус
#   ./start_bot.sh logs     — показать логи
#   ./start_bot.sh attach   — прицепиться к сессии tmux
#

set -e

# ==================== Конфигурация ====================

# Имя сессии tmux
SESSION="bot"

# Путь к проекту (текущая директория)
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Путь к виртуальному окружению (если есть)
VENV_DIR="$PROJECT_DIR/venv"

# Количество воркеров
NUM_WORKERS=4

# Python executable
if [ -d "$VENV_DIR" ]; then
    PYTHON="$VENV_DIR/bin/python"
else
    PYTHON="python3"
fi

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# ==================== Функции ====================

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[OK]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_tmux() {
    if ! command -v tmux &> /dev/null; then
        log_error "tmux не найден. Установите: sudo apt install tmux -y"
        exit 1
    fi
}

check_python() {
    if ! $PYTHON --version &> /dev/null; then
        log_error "Python не найден. Проверьте установку."
        exit 1
    fi
}

check_redis() {
    # Проверяем, включён ли Redis в .env
    if grep -q "USE_REDIS=true" "$PROJECT_DIR/.env" 2>/dev/null; then
        log_info "Redis включён в конфигурации"
    else
        log_warning "Redis выключен (USE_REDIS=false). Бот будет работать в локальном режиме."
    fi
}

session_exists() {
    tmux has-session -t $SESSION 2>/dev/null
}

stop_session() {
    if session_exists; then
        log_info "Остановка сессии $SESSION..."
        tmux kill-session -t $SESSION
        log_success "Сессия остановлена"
    else
        log_info "Сессия не запущена"
    fi
}

start_session() {
    log_info "Запуск бота в tmux..."
    log_info "Проект: $PROJECT_DIR"
    log_info "Python: $PYTHON"
    log_info "Воркеры: $NUM_WORKERS"
    
    # Проверяем зависимости
    check_tmux
    check_python
    check_redis
    
    # Если сессия уже есть — убиваем
    if session_exists; then
        log_warning "Сессия уже запущена. Перезапускаю..."
        stop_session
    fi
    
    # Создаём новую сессию
    log_info "Создание сессии tmux..."
    
    # Окно 0: Воркеры (разделено на панели)
    tmux new-session -d -s $SESSION -n workers
    
    # Создаём панели для воркеров (2x2 для 4 воркеров)
    if [ $NUM_WORKERS -ge 2 ]; then
        tmux split-window -h -t $SESSION:0.0
    fi
    if [ $NUM_WORKERS -ge 3 ]; then
        tmux split-window -v -t $SESSION:0.0
    fi
    if [ $NUM_WORKERS -ge 4 ]; then
        tmux split-window -v -t $SESSION:0.2
    fi
    
    # Запускаем воркеры
    for i in $(seq 0 $((NUM_WORKERS - 1))); do
        local pane=$i
        if [ $i -ge 2 ]; then
            pane=$((i - 2))
        fi
        tmux send-keys -t $SESSION:0.$pane \
            "cd $PROJECT_DIR && $PYTHON worker.py --id $i" Enter
        log_success "Воркер $i запущен"
    done
    
    # Окно 1: Listener
    tmux new-window -t $SESSION -n listener
    tmux send-keys -t $SESSION:1 \
        "cd $PROJECT_DIR && $PYTHON redis_listener.py" Enter
    log_success "Listener запущен"
    
    # Окно 2: Bot (ГЛАВНЫЙ КОМПОНЕНТ)
    tmux new-window -t $SESSION -n bot
    tmux send-keys -t $SESSION:2 \
        "cd $PROJECT_DIR && $PYTHON bot.py" Enter
    log_success "✅ Bot запущен"

    # Переключаемся на окно с ботом (чтобы видеть его логи при attach)
    tmux select-window -t $SESSION:2

    log_success "Все компоненты запущены!"
    echo ""
    echo -e "${GREEN}================================${NC}"
    echo -e "${GREEN}  Бот запущен в сессии tmux!${NC}"
    echo -e "${GREEN}================================${NC}"
    echo ""
    echo "Команды управления:"
    echo "  ./start_bot.sh attach   — прицепиться к сессии"
    echo "  ./start_bot.sh status   — показать статус"
    echo "  ./start_bot.sh logs     — показать логи"
    echo "  ./start_bot.sh stop     — остановить всё"
    echo ""
    echo "Внутри tmux:"
    echo "  Ctrl+B, W — список окон"
    echo "  Ctrl+B, D — отцепиться от сессии"
    echo ""
}

show_status() {
    echo -e "${BLUE}================================${NC}"
    echo -e "${BLUE}  Статус компонентов бота${NC}"
    echo -e "${BLUE}================================${NC}"
    echo ""

    if session_exists; then
        log_success "Сессия tmux запущена"
        echo ""
        echo "Окна:"
        tmux list-windows -t $SESSION
        echo ""
        echo "Панели:"
        tmux list-panes -t $SESSION
    else
        log_warning "Сессия не запущена"
    fi

    echo ""
    echo "Процессы Python:"
    ps aux | grep -E "(bot\.py|worker\.py|redis_listener\.py)" | grep -v grep || echo "  (нет активных процессов)"

    echo ""
    echo "=== Проверка компонентов ==="
    
    # Проверка бота
    if pgrep -f "python.*bot.py" > /dev/null 2>&1; then
        log_success "✅ bot.py работает"
    else
        log_error "❌ bot.py НЕ работает!"
        log_warning "Запустите: python bot.py"
    fi

    # Проверка воркеров
    echo ""
    echo "Воркеры:"
    for i in $(seq 0 $((NUM_WORKERS - 1))); do
        if pgrep -f "python.*worker.py --id $i" > /dev/null 2>&1; then
            log_success "  ✅ worker-$i работает"
        else
            log_warning "  ⚠️ worker-$i не работает"
        fi
    done

    # Проверка listener
    echo ""
    if pgrep -f "python.*redis_listener.py" > /dev/null 2>&1; then
        log_success "✅ redis_listener.py работает"
    else
        log_warning "⚠️ redis_listener.py не работает"
    fi
}

show_logs() {
    if ! session_exists; then
        log_error "Сессия не запущена"
        exit 1
    fi

    echo -e "${BLUE}================================${NC}"
    echo -e "${BLUE}  Логи компонентов${NC}"
    echo -e "${BLUE}================================${NC}"
    echo ""

    # Показываем последние строки из логов
    for logfile in worker.log redis_listener.log bot.log; do
        if [ -f "$PROJECT_DIR/$logfile" ]; then
            echo -e "${GREEN}=== $logfile (последние 30 строк) ===${NC}"
            tail -30 "$PROJECT_DIR/$logfile"
            echo ""
        fi
    done

    # Показываем логи из tmux буфера для каждого окна
    echo -e "${GREEN}=== tmux bot (окно 2) ===${NC}"
    tmux capture-pane -t $SESSION:2 -p 2>/dev/null | tail -30 || echo "Не удалось получить лог"

    echo ""
    echo -e "${GREEN}=== tmux listener (окно 1) ===${NC}"
    tmux capture-pane -t $SESSION:1 -p 2>/dev/null | tail -30 || echo "Не удалось получить лог"

    echo ""
    echo -e "${GREEN}=== tmux workers (окно 0, панель 0) ===${NC}"
    tmux capture-pane -t $SESSION:0.0 -p 2>/dev/null | tail -30 || echo "Не удалось получить лог"
}

attach_session() {
    if ! session_exists; then
        log_error "Сессия не запущена. Запустите: ./start_bot.sh"
        exit 1
    fi
    
    log_info "Подключение к сессии $SESSION..."
    tmux attach -t $SESSION
}

show_help() {
    echo "Использование: ./start_bot.sh [command]"
    echo ""
    echo "Команды:"
    echo "  (без команды)  — запустить все компоненты"
    echo "  stop           — остановить все компоненты"
    echo "  status         — показать статус"
    echo "  logs           — показать логи"
    echo "  attach         — прицепиться к сессии tmux"
    echo "  restart        — перезапустить всё"
    echo "  bot            — запустить только бот (для отладки)"
    echo "  help           — показать эту справку"
    echo ""
    echo "Примеры:"
    echo "  ./start_bot.sh              # Запуск"
    echo "  ./start_bot.sh attach       # Подключиться к сессии"
    echo "  ./start_bot.sh status       # Проверить статус"
    echo "  ./start_bot.sh stop         # Остановить"
    echo "  ./start_bot.sh bot          # Запустить только бота"
    echo ""
    echo "Структура сессии tmux:"
    echo "  Окно 0: Воркеры (4 панели)"
    echo "  Окно 1: Redis listener"
    echo "  Окно 2: Bot (главное окно)"
}

# ==================== Основная логика ====================

cd "$PROJECT_DIR"

case "${1:-start}" in
    start|"")
        start_session
        ;;
    stop)
        stop_session
        ;;
    restart)
        stop_session
        sleep 1
        start_session
        ;;
    status)
        show_status
        ;;
    logs)
        show_logs
        ;;
    attach)
        attach_session
        ;;
    bot)
        # Запуск только бота (для отладки без Redis)
        log_info "Запуск bot.py в режиме отладки..."
        check_python
        $PYTHON bot.py
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        log_error "Неизвестная команда: $1"
        show_help
        exit 1
        ;;
esac
