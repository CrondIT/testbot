#!/bin/bash
#
# install.sh — Установка зависимостей для бота
#
# Использование:
#   ./install.sh          — полная установка
#   ./install.sh --venv   — создать виртуальное окружение
#   ./install.sh --deps   — установить зависимости
#

set -e

# Цвета
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

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

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$PROJECT_DIR/.venv"

install_venv() {
    log_info "Создание виртуального окружения..."
    
    if [ -d "$VENV_DIR" ]; then
        log_warning "Виртуальное окружение уже существует"
        read -p "Удалить и создать заново? (y/n): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            rm -rf "$VENV_DIR"
        else
            return
        fi
    fi
    
    if command -v python3 &> /dev/null; then
        python3 -m venv "$VENV_DIR"
        log_success "Виртуальное окружение создано: $VENV_DIR"
    else
        log_error "Python3 не найден"
        exit 1
    fi
}

install_deps() {
    log_info "Установка зависимостей..."
    
    local pip_cmd="pip"
    
    if [ -d "$VENV_DIR" ]; then
        pip_cmd="$VENV_DIR/bin/pip"
        log_info "Использую pip из виртуального окружения"
    fi
    
    # Обновляем pip
    $pip_cmd install --upgrade pip
    
    # Устанавливаем зависимости
    if [ -f "$PROJECT_DIR/requirements.txt" ]; then
        $pip_cmd install -r "$PROJECT_DIR/requirements.txt"
        log_success "Зависимости установлены"
    else
        log_error "requirements.txt не найден"
        exit 1
    fi
}

install_tmux() {
    log_info "Проверка tmux..."
    
    if command -v tmux &> /dev/null; then
        log_success "tmux уже установлен"
    else
        log_warning "tmux не найден"
        
        if command -v apt &> /dev/null; then
            read -p "Установить tmux? (y/n): " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                sudo apt update && sudo apt install tmux -y
                log_success "tmux установлен"
            fi
        else
            log_error "Не удалось определить пакетный менеджер"
            log_info "Установите tmux вручную: sudo apt install tmux"
        fi
    fi
}

check_python() {
    log_info "Проверка Python..."
    
    if command -v python3 &> /dev/null; then
        local version=$(python3 --version)
        log_success "$version найден"
    else
        log_error "Python3 не найден"
        log_info "Установите: sudo apt install python3 python3-pip python3-venv"
        exit 1
    fi
}

show_config() {
    echo ""
    echo -e "${GREEN}================================${NC}"
    echo -e "${GREEN}  Установка завершена!${NC}"
    echo -e "${GREEN}================================${NC}"
    echo ""
    echo "Следующие шаги:"
    echo ""
    echo "1. Настройте .env:"
    echo "   cp .env.example .env"
    echo "   nano .env  # или ваш редактор"
    echo ""
    echo "2. Запустите бота:"
    echo "   ./start_bot.sh"
    echo ""
    echo "3. Или в ручном режиме:"
    echo "   source .venv/bin/activate"
    echo "   python bot.py"
    echo ""
}

# Основная логика
cd "$PROJECT_DIR"

case "${1:-all}" in
    --venv)
        check_python
        install_venv
        ;;
    --deps)
        install_deps
        ;;
    --tmux)
        install_tmux
        ;;
    all|"")
        log_info "Полная установка..."
        echo ""
        
        check_python
        echo ""
        
        install_tmux
        echo ""
        
        install_venv
        echo ""
        
        install_deps
        echo ""
        
        show_config
        ;;
    *)
        echo "Использование: ./install.sh [options]"
        echo ""
        echo "Опции:"
        echo "  (без опций)  — полная установка"
        echo "  --venv       — создать виртуальное окружение"
        echo "  --deps       — установить зависимости"
        echo "  --tmux       — установить tmux"
        echo "  --help       — показать эту справку"
        ;;
esac
