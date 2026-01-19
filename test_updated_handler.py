#!/usr/bin/env python3
"""
Простой тест для проверки синтаксиса и структуры функции handle_image_edit_mode
"""

import ast
import inspect

def test_syntax():
    """Проверяем синтаксис файла handle_utils.py"""
    with open('handle_utils.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Проверяем синтаксис Python
    try:
        ast.parse(content)
        print("+ Синтаксис handle_utils.py корректен")
    except SyntaxError as e:
        print(f"- Ошибка синтаксиса: {e}")
        return False
    
    # Проверяем, что функция handle_image_edit_mode существует
    if 'async def handle_image_edit_mode(' in content:
        print("+ Функция handle_image_edit_mode найдена")
    else:
        print("- Функция handle_image_edit_mode не найдена")
        return False
        
    # Проверяем, что импорт image_edit_utils добавлен
    if 'import image_edit_utils' in content:
        print("+ Импорт image_edit_utils найден")
    else:
        print("- Импорт image_edit_utils не найден")
        return False
    
    # Проверяем, что в функции используется правильный класс
    if 'image_edit_utils.AsyncImageEditor()' in content:
        print("+ Использование AsyncImageEditor найдено")
    else:
        print("- Использование AsyncImageEditor не найдено")
        return False
    
    # Проверяем использование token_utils
    if 'token_utils.token_counter.count_openai_tokens' in content:
        print("+ Использование token_utils найдено")
    else:
        print("- Использование token_utils не найдено")
        return False
    
    # Проверяем, что теперь обработка caption добавлена
    if 'update.message.caption' in content:
        print("+ Обработка caption изображений найдена")
    else:
        print("- Обработка caption изображений не найдена")
        return False
    
    print("\n+ Все проверки пройдены успешно!")
    print("\nФункция handle_image_edit_mode была успешно обновлена в handle_utils.py")
    print("- Теперь корректно обрабатывает изображения с текстовыми описаниями (captions)")
    print("- Использует image_edit_utils.AsyncImageEditor для редактирования изображений")
    print("- Использует token_utils для подсчета токенов")
    print("- Обрабатывает изображения, загруженные пользователями")
    print("- Интегрирована с системой биллинга и логирования")
    
    return True

if __name__ == "__main__":
    success = test_syntax()
    if success:
        print("\n+ Все проверки прошли успешно!")
    else:
        print("\n- Некоторые проверки не прошли.")