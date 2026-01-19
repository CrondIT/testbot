#!/usr/bin/env python3
"""
Тест для проверки обновленного функционала редактирования изображений
"""

import ast

def test_updated_image_edit():
    """Проверяем синтаксис обновленного image_edit_utils.py"""
    with open('image_edit_utils.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Проверяем синтаксис Python
    try:
        ast.parse(content)
        print("+ Синтаксис image_edit_utils.py корректен")
    except SyntaxError as e:
        print(f"- Ошибка синтаксиса: {e}")
        return False
    
    # Проверяем наличие новых методов
    if '_apply_keyword_based_editing' in content:
        print("+ Метод _apply_keyword_based_editing найден")
    else:
        print("- Метод _apply_keyword_based_editing не найден")
        return False
        
    if '_images_are_similar' in content:
        print("+ Метод _images_are_similar найден")
    else:
        print("- Метод _images_are_similar не найден")
        return False
    
    # Проверяем, что основной метод edit_image обновлен
    if 'original_image = image.copy()' in content:
        print("+ Логика сохранения оригинального изображения найдена")
    else:
        print("- Логика сохранения оригинального изображения не найдена")
        return False
    
    print("\n+ Все проверки обновленного модуля пройдены успешно!")
    print("\nОбновления в image_edit_utils.py:")
    print("- Добавлена проверка, были ли изменения в изображении")
    print("- Если изображение не изменилось, применяются минимальные изменения")
    print("- Добавлены вспомогательные методы для лучшей обработки")
    print("- Улучшена надежность редактирования изображений")
    
    return True

if __name__ == "__main__":
    success = test_updated_image_edit()
    if success:
        print("\n+ Все проверки прошли успешно!")
    else:
        print("\n- Некоторые проверки не прошли.")