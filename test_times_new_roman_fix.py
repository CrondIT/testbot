#!/usr/bin/env python3
"""
Тест для проверки исправления ошибки с Times New Roman в PDF
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from pdf_utils import normalize_font_name, create_pdf_from_json
import io

def test_normalize_font_name():
    """Тестирование функции normalize_font_name"""
    print("Тестирование функции normalize_font_name...")
    
    # Тесты для различных вариантов Times New Roman
    test_cases = [
        "Times New Roman",
        "times new roman", 
        "TIMES NEW ROMAN",
        "TimesNewRoman",
        "times-new-roman",
        "Times",
        "times",
        "Arial",
        "Helvetica",
        "",
        None
    ]
    
    for test_case in test_cases:
        result = normalize_font_name(test_case)
        print(f"  '{test_case}' -> '{result}'")
    
    print("Тестирование завершено.\n")


def test_create_pdf_with_times_new_roman():
    """Тестирование создания PDF с Times New Roman в JSON"""
    print("Тестирование создания PDF с Times New Roman...")
    
    # JSON с Times New Roman в разных местах
    test_data = {
        "meta": {
            "title": "Учебный план по предмету «Астрономия» (72 часа, 2 семестра)"
        },
        "blocks": [
            {
                "type": "heading",
                "level": 1,
                "text": "Учебный план по астрономии",
                "font_name": "Times New Roman"  # Это должно быть исправлено
            },
            {
                "type": "paragraph",
                "text": "Это тестовый учебный план.",
                "font_name": "Times New Roman"  # Это тоже должно быть исправлено
            },
            {
                "type": "table",
                "headers": ["Название темы", "Количество часов", "Семестр"],
                "rows": [
                    ["Введение в астрономию", "4", "1"],
                    ["Небесная сфера", "6", "1"],
                    ["Лабораторные работы", "12", "1-2"]
                ],
                "params": {
                    "header_font_name": "Times New Roman Bold",  # Это тоже должно быть исправлено
                    "body_font_name": "Times New Roman"  # Это тоже должно быть исправлено
                }
            }
        ]
    }
    
    try:
        pdf_buffer = create_pdf_from_json(test_data)
        print("  Успешно создан PDF с Times New Roman!")
        
        # Проверим размер буфера
        pdf_buffer.seek(0, 2)  # Перейти в конец файла
        size = pdf_buffer.tell()
        print(f"  Размер PDF: {size} байт")
        
        return True
    except Exception as e:
        print(f"  Ошибка при создании PDF: {e}")
        return False


if __name__ == "__main__":
    print("Тестирование исправления ошибки с Times New Roman\n")
    
    test_normalize_font_name()
    success = test_create_pdf_with_times_new_roman()
    
    if success:
        print("\n✓ Все тесты пройдены успешно! Ошибка с Times New Roman исправлена.")
    else:
        print("\n✗ Тест не пройден. Ошибка все еще существует.")