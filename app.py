import tkinter as tk
from tkinter import scrolledtext, messagebox, simpledialog, Menu, ttk, filedialog
import pyperclip
import webbrowser
import json
import os
from pystray import MenuItem as TrayMenuItem, Icon
from PIL import Image, ImageTk
import threading
import re
import qrcode
from io import BytesIO
import chardet
import subprocess
from pydub import AudioSegment
from collections import Counter
import sys
import win32clipboard
import win32con
import win32gui
import keyboard
import time
from datetime import datetime
import shutil
import tempfile
import mimetypes
import imageio
from moviepy.editor import VideoFileClip
import math
import ctypes
from ctypes import cast, POINTER
from comtypes import CLSCTX_ALL
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

try:
    from moviepy.editor import VideoFileClip
except ImportError:
    VideoFileClip = None


class VolumeControl:
    """Класс для управления громкостью системы"""

    def __init__(self):
        self.devices = AudioUtilities.GetSpeakers()
        self.interface = self.devices.Activate(
            IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        self.volume = cast(self.interface, POINTER(IAudioEndpointVolume))

    def get_volume(self):
        """Получаем текущую громкость"""
        return self.volume.GetMasterVolumeLevelScalar()

    def set_volume(self, level):
        """Устанавливаем громкость (0.0 - 1.0)"""
        self.volume.SetMasterVolumeLevelScalar(level, None)

    def increase_volume(self, increment=0.05):
        """Увеличиваем громкость на указанное значение"""
        current = self.get_volume()
        new_level = min(1.0, current + increment)
        self.set_volume(new_level)
        return new_level


class TextEditorApp:
    def __init__(self, root):
        self.root = root
        root.title("Advanced Text Editor")
        root.geometry("800x650")
        root.protocol("WM_DELETE_WINDOW", self.minimize_to_tray)

        # Загрузка истории и избранного
        self.history = self.load_data("history.json", max_items=50)
        self.favorites = self.load_data("favorites.json")

        # Создаем панель вкладок
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Вкладка основного редактора
        self.editor_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.editor_frame, text="Редактор")

        # Создаем текстовое поле с прокруткой
        self.text_area = scrolledtext.ScrolledText(
            self.editor_frame,
            wrap=tk.WORD,
            width=90,
            height=25,
            font=("Arial", 12)
        )
        self.text_area.pack(padx=15, pady=15, fill=tk.BOTH, expand=True)

        # Привязываем обработчик изменений текста
        self.text_area.bind("<<Modified>>", self.on_text_modified)
        self.text_area.bind("<FocusOut>", self.on_focus_out)

        # Загружаем настройки горячих клавиш
        self.hotkeys = self.load_hotkeys()

        # Создаем контекстное меню
        self.create_context_menu()

        # Привязываем горячие клавиши
        self.bind_hotkeys()

        # Создаем фрейм для кнопок
        button_frame = tk.Frame(self.editor_frame)
        button_frame.pack(fill=tk.X, padx=10, pady=5)

        # Кнопки операций
        buttons = [
            ("📋 Вставить", self.paste_from_clipboard),
            ("📄 Копировать", self.copy_to_clipboard),
            ("📂 Открыть файл", self.open_file),
            ("💾 Сохранить", self.save_file),
            ("🔍 Найти/Заменить", self.find_replace),
            ("📊 Статистика", self.show_stats),
            ("🗑️ Удалить смайлы", self.remove_emojis),
            ("🔣 QR-код", self.generate_qrcode),
            ("🔄 Сменить раскладку", self.change_layout),
            ("🌍 Перевести", self.translate_text),
            ("⚙️ Настройки", self.open_settings),
            ("🔄 Конвертер", self.open_file_converter),
            ("🧮 Калькулятор", self.open_calculator)
        ]

        # Располагаем кнопки в 4 ряда
        frames = [tk.Frame(button_frame) for _ in range(4)]
        for frame in frames:
            frame.pack(fill=tk.X)

        for i, (text, command) in enumerate(buttons):
            frame_idx = i // 4  # 4 кнопки в ряду
            btn = tk.Button(
                frames[frame_idx],
                text=text,
                command=command,
                padx=5,
                pady=3
            )
            btn.pack(side=tk.LEFT, padx=2, pady=2, fill=tk.X, expand=True)

        # Инициализируем словари для смены раскладки
        self.init_layout_dicts()

        # Создаем вкладки истории и избранного
        self.create_history_favorites_tabs()

        # Статусная строка
        self.status_var = tk.StringVar()
        status_bar = tk.Label(
            root,
            textvariable=self.status_var,
            bd=1,
            relief=tk.SUNKEN,
            anchor=tk.W
        )
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)

        # Переменная для отслеживания изменений
        self.last_history_text = ""

        # Переменные для работы с треем
        self.tray_icon = None
        self.tray_thread = None
        self.tray_active = False

        # Глобальные горячие клавиши
        self.hotkey_enabled = True
        self.hotkey_combination = "ctrl+alt+e"  # Менее конфликтное сочетание
        self.register_global_hotkey()

        # Проверяем наличие ffmpeg
        self.check_ffmpeg()

        self.update_status("Готов к работе")

    def create_context_menu(self):
        """Создаем контекстное меню для текстового поля с новой функцией"""
        self.context_menu = Menu(self.root, tearoff=0)
        self.context_menu.add_command(label="Вырезать", command=self.cut_text)
        self.context_menu.add_command(label="Копировать", command=self.copy_text)
        self.context_menu.add_command(label="Вставить", command=self.paste_text)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Вычислить выражение", command=self.calculate_selection)
        self.context_menu.add_command(label="Статистика выделенного", command=self.show_selected_stats)
        self.context_menu.add_command(label="Удалить все", command=self.clear_text)

        # Привязываем контекстное меню к текстовому полю
        self.text_area.bind("<Button-3>", self.show_context_menu)

    def show_context_menu(self, event):
        """Показываем контекстное меню с учетом выделения"""
        try:
            # Очищаем старое меню
            self.context_menu.delete(0, 'end')

            # Стандартные пункты
            self.context_menu.add_command(label="Вырезать", command=self.cut_text)
            self.context_menu.add_command(label="Копировать", command=self.copy_text)
            self.context_menu.add_command(label="Вставить", command=self.paste_text)
            self.context_menu.add_separator()

            # Проверяем, есть ли выделенный текст
            if self.text_area.tag_ranges("sel"):
                selected_text = self.text_area.get("sel.first", "sel.last")

                # Добавляем пункт с результатом вычисления
                if self.is_math_expression(selected_text):
                    try:
                        # Вычисляем выражение
                        result = self.calculate_expression(selected_text)
                        # Добавляем пункт с результатом (не активный)
                        self.context_menu.add_command(
                            label=f"Результат: {selected_text} = {result}",
                            state=tk.DISABLED
                        )
                        self.context_menu.add_separator()
                    except Exception as e:
                        pass  # Если не вычислилось, просто пропускаем

                # Добавляем вычисление и статистику
                self.context_menu.add_command(label="Вычислить выражение", command=self.calculate_selection)
                self.context_menu.add_command(label="Статистика выделенного", command=self.show_selected_stats)
                self.context_menu.add_separator()

            # Общие пункты
            self.context_menu.add_command(label="Удалить все", command=self.clear_text)

            # Показываем меню
            self.context_menu.tk_popup(event.x_root, event.y_root)
        except Exception as e:
            print(f"Ошибка при показе контекстного меню: {e}")

    def check_ffmpeg(self):
        """Проверяем наличие ffmpeg в системе"""
        if not shutil.which("ffmpeg"):
            self.update_status("Внимание: ffmpeg не установлен! Конвертация видео/аудио может не работать")
            print("FFmpeg не найден. Установите ffmpeg для работы конвертера.")

    def show_context_menu(self, event):
        """Показываем контекстное меню с учетом выделения"""
        try:
            # Очищаем старое меню
            self.context_menu.delete(0, 'end')

            # Стандартные пункты
            self.context_menu.add_command(label="Вырезать", command=self.cut_text)
            self.context_menu.add_command(label="Копировать", command=self.copy_text)
            self.context_menu.add_command(label="Вставить", command=self.paste_text)
            self.context_menu.add_separator()

            # Проверяем, есть ли выделенный текст
            if self.text_area.tag_ranges("sel"):
                selected_text = self.text_area.get("sel.first", "sel.last")

                # Добавляем пункт с результатом вычисления
                if self.is_math_expression(selected_text):
                    try:
                        # Вычисляем выражение
                        result = self.calculate_expression(selected_text)
                        # Добавляем пункт с результатом (не активный)
                        self.context_menu.add_command(
                            label=f"Результат: {selected_text} = {result}",
                            state=tk.DISABLED
                        )
                        self.context_menu.add_separator()
                    except Exception as e:
                        pass  # Если не вычислилось, просто пропускаем

                # Добавляем вычисление и статистику
                self.context_menu.add_command(label="Вычислить выражение", command=self.calculate_selection)
                self.context_menu.add_command(label="Статистика выделенного", command=self.show_selected_stats)
                self.context_menu.add_separator()

            # Общие пункты
            self.context_menu.add_command(label="Удалить все", command=self.clear_text)

            # Показываем меню
            self.context_menu.tk_popup(event.x_root, event.y_root)
        except Exception as e:
            print(f"Ошибка при показе контекстного меню: {e}")

    def is_math_expression(self, text):
        """Проверяем, является ли текст математическим выражением"""
        # Удаляем пробелы для упрощения проверки
        clean_text = text.replace(" ", "")

        # Проверяем наличие математических операторов
        operators = ['+', '-', '*', '/', '^', '%', '(', ')']
        if any(op in clean_text for op in operators):
            # Проверяем, что остальные символы допустимы
            allowed_chars = "0123456789.+-*/^%()eπ"
            return all(c in allowed_chars for c in clean_text)
        return False

    def calculate_selection(self):
        """Вычисляем математическое выражение в выделенном тексте"""
        try:
            # Получаем выделенный текст
            selected_text = self.text_area.get("sel.first", "sel.last")

            if not selected_text:
                messagebox.showinfo("Информация", "Нет выделенного текста")
                return

            # Вычисляем выражение
            result = self.calculate_expression(selected_text)

            # Заменяем выделенный текст на результат
            self.text_area.delete("sel.first", "sel.last")
            self.text_area.insert("sel.first", str(result))

            self.update_status(f"Вычислено: {selected_text} = {result}")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось вычислить выражение: {str(e)}")
            self.update_status(f"Ошибка вычисления: {str(e)}")


    def calculate_expression(self, expression):
        """Вычисляем математическое выражение"""
        try:
            # Заменяем символы для вычисления
            expr = expression.replace('^', '**').replace('π', 'math.pi').replace('%', '/100')
            # Вычисляем выражение
            result = eval(expr, {"__builtins__": None}, {"math": math})
            return round(result, 4)  # Округляем до 4 знаков после запятой
        except Exception as e:
            raise ValueError(f"Не удалось вычислить выражение: {str(e)}")

    def open_calculator(self):
        """Открываем встроенный калькулятор (увеличенный)"""
        calc_win = tk.Toplevel(self.root)
        calc_win.title("Встроенный калькулятор")
        calc_win.geometry("400x500")
        calc_win.resizable(False, False)
        calc_win.grab_set()

        # Переменные
        self.calc_input = tk.StringVar()
        self.calc_history = []

        # Поле ввода
        input_frame = tk.Frame(calc_win)
        input_frame.pack(fill=tk.X, padx=10, pady=10)

        input_entry = tk.Entry(
            input_frame,
            textvariable=self.calc_input,
            font=("Arial", 16),
            justify=tk.RIGHT,
            state='readonly'
        )
        input_entry.pack(fill=tk.X, ipady=10)

        # История вычислений
        history_frame = tk.LabelFrame(calc_win, text="История вычислений")
        history_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        scrollbar = tk.Scrollbar(history_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.history_list = tk.Listbox(
            history_frame,
            yscrollcommand=scrollbar.set,
            font=("Arial", 12)
        )
        self.history_list.pack(fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.history_list.yview)

        # Кнопки калькулятора
        buttons_frame = tk.Frame(calc_win)
        buttons_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Конфигурация кнопок
        button_grid = [
            ['7', '8', '9', '/', 'C'],
            ['4', '5', '6', '*', '←'],
            ['1', '2', '3', '-', '('],
            ['0', '.', '=', '+', ')'],
            ['π', '%', '^', '√', '']
        ]

        # Создаем кнопки с использованием grid
        for i, row in enumerate(button_grid):
            for j, btn_text in enumerate(row):
                if btn_text:  # Пропускаем пустые кнопки
                    btn = tk.Button(
                        buttons_frame,
                        text=btn_text,
                        font=("Arial", 14),
                        command=lambda t=btn_text: self.calc_button_click(t)
                    )
                    btn.grid(row=i, column=j, sticky="nsew", padx=2, pady=2)

        # Настраиваем расширение столбцов
        for j in range(5):
            buttons_frame.columnconfigure(j, weight=1)
        for i in range(5):
            buttons_frame.rowconfigure(i, weight=1)

    def calc_button_click(self, button_text):
        """Обработчик нажатия кнопок калькулятора"""
        current_text = self.calc_input.get()

        if button_text == 'C':
            self.calc_input.set('')
        elif button_text == '←':
            self.calc_input.set(current_text[:-1])
        elif button_text == '=':
            try:
                # Заменяем символы для вычисления
                expression = current_text.replace('^', '**').replace('π', 'math.pi').replace('%', '/100')

                # Вычисляем выражение
                result = eval(expression, {"__builtins__": None}, {"math": math})

                # Сохраняем в историю
                history_entry = f"{current_text} = {result}"
                self.calc_history.append(history_entry)
                self.history_list.insert(tk.END, history_entry)
                self.history_list.see(tk.END)

                # Устанавливаем результат
                self.calc_input.set(str(result))
            except Exception as e:
                self.calc_input.set("Ошибка")
        elif button_text == '√':
            try:
                # Вычисляем квадратный корень
                value = float(current_text) if current_text else 0.0
                result = math.sqrt(value)
                self.calc_input.set(str(result))
            except Exception as e:
                self.calc_input.set("Ошибка")
        else:
            self.calc_input.set(current_text + button_text)

    def register_global_hotkey(self):
        """Регистрируем глобальную горячую клавишу"""
        try:
            # Удаляем старую горячую клавишу, если она была
            if hasattr(self, 'hotkey_registered'):
                keyboard.remove_hotkey(self.hotkey_combination)

            keyboard.add_hotkey(self.hotkey_combination, self.global_hotkey_pressed)
            self.hotkey_registered = True
            self.update_status(f"Горячая клавиша: {self.hotkey_combination.upper()}")
        except Exception as e:
            error_msg = f"Не удалось зарегистрировать горячую клавишу: {str(e)}"
            if hasattr(self, 'status_var'):
                self.update_status(error_msg)
            else:
                print(error_msg)

    def global_hotkey_pressed(self):
        """Обработчик нажатия глобальной горячей клавиши (без изменения громкости)"""
        if not self.hotkey_enabled:
            return

        try:
            # Получаем выделенный текст напрямую через Win32 API
            selected_text = self.get_selected_text()

            # Если есть выделенный текст - устанавливаем его
            if selected_text:
                self.set_text(selected_text)

            # Показываем приложение
            self.restore_from_tray()
            self.root.lift()
            self.root.focus_force()

            self.update_status("Активировано горячей клавишей")
        except Exception as e:
            self.update_status(f"Ошибка горячей клавиши: {str(e)}")

    def get_selected_text(self):
        """Получаем выделенный текст с помощью Win32 API (без имитации клавиш)"""
        try:
            # Сохраняем текущий буфер обмена
            win32clipboard.OpenClipboard()
            try:
                original_clipboard = win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
            except:
                original_clipboard = ""
            win32clipboard.CloseClipboard()

            # Копируем выделенный текст в буфер обмена
            win32clipboard.OpenClipboard()
            win32clipboard.EmptyClipboard()

            # Получаем активное окно
            hwnd = win32gui.GetForegroundWindow()

            # Отправляем сообщение о копировании
            win32gui.SendMessage(hwnd, win32con.WM_COPY, 0, 0)

            # Даем время на обработку
            time.sleep(0.1)

            # Получаем текст из буфера обмена
            try:
                selected_text = win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
            except:
                selected_text = ""

            win32clipboard.CloseClipboard()

            # Восстанавливаем оригинальный буфер обмена
            win32clipboard.OpenClipboard()
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardText(original_clipboard, win32con.CF_UNICODETEXT)
            win32clipboard.CloseClipboard()

            return selected_text
        except Exception as e:
            print(f"Ошибка при получении выделенного текста: {e}")
            return ""

    def on_text_modified(self, event):
        """Обработчик изменения текста"""
        if self.text_area.edit_modified():
            current_text = self.get_text()
            if current_text != self.last_history_text:
                self.add_to_history(current_text)
                self.last_history_text = current_text
            self.text_area.edit_modified(False)

    def on_focus_out(self, event):
        """Обработчик потери фокуса"""
        current_text = self.get_text()
        if current_text != self.last_history_text:
            self.add_to_history(current_text)
            self.last_history_text = current_text

    # Методы для работы с данными
    def load_data(self, filename, max_items=None):
        """Загружаем данные из JSON-файла"""
        data = []
        if os.path.exists(filename):
            try:
                with open(filename, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if max_items and len(data) > max_items:
                        data = data[-max_items:]
            except:
                pass
        return data

    def save_data(self, filename, data):
        """Сохраняем данные в JSON-файл"""
        try:
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось сохранить данные: {str(e)}")

    # Методы для работы с горячими клавишами
    def load_hotkeys(self):
        """Загружаем настройки горячих клавиш из файла"""
        # Стандартные горячие клавиши
        default_hotkeys = {
            "F1": "Вставить из буфера",
            "F2": "Копировать в буфер",
            "F3": "Удалить слова",
            "F4": "Удалить буквы",
            "F5": "Удалить цифры",
            "F6": "Удалить ВСЕ цифры",
            "F7": "Удалить ВСЕ буквы",
            "F8": "Верхний регистр",
            "F9": "Нижний регистр",
            "F10": "Сменить раскладку",
            "F11": "Перевести",
            "F12": "Свернуть в трей"
        }

        # Пытаемся загрузить из файла
        if os.path.exists("hotkeys.json"):
            try:
                with open("hotkeys.json", "r", encoding="utf-8") as f:
                    return json.load(f)
            except:
                # В случае ошибки возвращаем значения по умолчанию
                return default_hotkeys
        return default_hotkeys

    def save_hotkeys(self):
        """Сохраняем настройки горячих клавиш в файл"""
        try:
            with open("hotkeys.json", "w", encoding="utf-8") as f:
                json.dump(self.hotkeys, f, ensure_ascii=False, indent=2)
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось сохранить настройки: {str(e)}")

    def bind_hotkeys(self):
        """Привязываем горячие клавиши к функциям"""
        self.root.bind("<F1>", lambda e: self.paste_from_clipboard())
        self.root.bind("<F2>", lambda e: self.copy_to_clipboard())
        self.root.bind("<F3>", lambda e: self.delete_words())
        self.root.bind("<F4>", lambda e: self.delete_letters())
        self.root.bind("<F5>", lambda e: self.delete_digits())
        self.root.bind("<F6>", lambda e: self.remove_all_digits())
        self.root.bind("<F7>", lambda e: self.remove_all_letters())
        self.root.bind("<F8>", lambda e: self.to_uppercase())
        self.root.bind("<F9>", lambda e: self.to_lowercase())
        self.root.bind("<F10>", lambda e: self.change_layout())
        self.root.bind("<F11>", lambda e: self.translate_text())
        self.root.bind("<F12>", lambda e: self.minimize_to_tray())

    # Методы интерфейса
    def create_context_menu(self):
        """Создаем контекстное меню для текстового поля с новой функцией"""
        self.context_menu = Menu(self.root, tearoff=0)
        self.context_menu.add_command(label="Вырезать", command=self.cut_text)
        self.context_menu.add_command(label="Копировать", command=self.copy_text)
        self.context_menu.add_command(label="Вставить", command=self.paste_text)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Вычислить выражение", command=self.calculate_selection)
        self.context_menu.add_command(label="Статистика выделенного", command=self.show_selected_stats)
        self.context_menu.add_command(label="Удалить все", command=self.clear_text)

        # Привязываем контекстное меню к текстовому полю
        self.text_area.bind("<Button-3>", self.show_context_menu)


    def show_context_menu(self, event):
        """Показываем контекстное меню с учетом выделения"""
        try:
            # Очищаем старое меню
            self.context_menu.delete(0, 'end')

            # Стандартные пункты
            self.context_menu.add_command(label="Вырезать", command=self.cut_text)
            self.context_menu.add_command(label="Копировать", command=self.copy_text)
            self.context_menu.add_command(label="Вставить", command=self.paste_text)
            self.context_menu.add_separator()

            # Проверяем, есть ли выделенный текст
            if self.text_area.tag_ranges("sel"):
                selected_text = self.text_area.get("sel.first", "sel.last")

                # Добавляем пункт с результатом вычисления
                if self.is_math_expression(selected_text):
                    try:
                        # Вычисляем выражение
                        result = self.calculate_expression(selected_text)
                        # Добавляем пункт с результатом (не активный)
                        self.context_menu.add_command(
                            label=f"Результат: {selected_text} = {result}",
                            state=tk.DISABLED
                        )
                        self.context_menu.add_separator()
                    except Exception as e:
                        pass  # Если не вычислилось, просто пропускаем

                # Добавляем вычисление и статистику
                self.context_menu.add_command(label="Вычислить выражение", command=self.calculate_selection)
                self.context_menu.add_command(label="Статистика выделенного", command=self.show_selected_stats)
                self.context_menu.add_separator()

            # Общие пункты
            self.context_menu.add_command(label="Удалить все", command=self.clear_text)

            # Показываем меню
            self.context_menu.tk_popup(event.x_root, event.y_root)
        except Exception as e:
            print(f"Ошибка при показе контекстного меню: {e}")

    def show_selected_stats(self):
        """Показываем статистику выделенного текста"""
        try:
            # Получаем выделенный текст
            selected_text = self.text_area.get("sel.first", "sel.last")

            if not selected_text:
                messagebox.showinfo("Информация", "Нет выделенного текста")
                return

            # Создаем диалоговое окно
            dialog = tk.Toplevel(self.root)
            dialog.title("Статистика выделенного текста")
            dialog.geometry("300x200")

            # Подсчет статистики
            chars = len(selected_text)
            words = len(selected_text.split())
            lines = selected_text.count('\n') + 1
            digits = sum(c.isdigit() for c in selected_text)
            letters = sum(c.isalpha() for c in selected_text)

            # Отображение статистики
            stats = [
                f"Символов: {chars}",
                f"Слов: {words}",
                f"Строк: {lines}",
                f"Цифр: {digits}",
                f"Букв: {letters}"
            ]

            for i, stat in enumerate(stats):
                tk.Label(dialog, text=stat, anchor=tk.W).pack(fill=tk.X, padx=20, pady=5)

            # Кнопка закрытия
            tk.Button(dialog, text="Закрыть", command=dialog.destroy).pack(pady=10)

        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось получить статистику: {str(e)}")

    def open_file_converter(self):
        """Открываем окно конвертера файлов"""
        converter_win = tk.Toplevel(self.root)
        converter_win.title("Конвертер файлов")
        converter_win.geometry("600x400")
        converter_win.grab_set()

        # Основной фрейм
        main_frame = ttk.Frame(converter_win)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        # Выбор типа конвертации
        ttk.Label(main_frame, text="Тип конвертации:").grid(row=0, column=0, sticky=tk.W, pady=5)

        self.conversion_type = tk.StringVar(value="video_to_audio")
        conversion_options = [
            ("Видео в аудио", "video_to_audio"),
            ("Изображение в PNG", "image_to_png"),
            ("Изображение в JPG", "image_to_jpg"),
            ("Аудио в MP3", "audio_to_mp3")
        ]

        for i, (text, mode) in enumerate(conversion_options):
            rb = ttk.Radiobutton(
                main_frame,
                text=text,
                variable=self.conversion_type,
                value=mode
            )
            rb.grid(row=i + 1, column=0, sticky=tk.W, pady=2)

        # Выбор исходного файла
        ttk.Label(main_frame, text="Исходный файл:").grid(row=0, column=1, sticky=tk.W, pady=5)
        self.source_file = tk.StringVar()
        ttk.Entry(main_frame, textvariable=self.source_file, width=30).grid(
            row=1, column=1, sticky=tk.EW, padx=5, pady=2
        )
        ttk.Button(
            main_frame,
            text="Обзор...",
            command=lambda: self.browse_file(self.source_file)
        ).grid(row=1, column=2, padx=5, pady=2)

        # Выбор папки назначения
        ttk.Label(main_frame, text="Папка назначения:").grid(row=2, column=1, sticky=tk.W, pady=5)
        self.dest_folder = tk.StringVar(value=os.getcwd())
        ttk.Entry(main_frame, textvariable=self.dest_folder, width=30).grid(
            row=3, column=1, sticky=tk.EW, padx=5, pady=2
        )
        ttk.Button(
            main_frame,
            text="Обзор...",
            command=lambda: self.browse_folder(self.dest_folder)
        ).grid(row=3, column=2, padx=5, pady=2)

        # Имя выходного файла
        ttk.Label(main_frame, text="Имя выходного файла:").grid(row=4, column=1, sticky=tk.W, pady=5)
        self.output_name = tk.StringVar(value="converted_file")
        ttk.Entry(main_frame, textvariable=self.output_name, width=30).grid(
            row=5, column=1, sticky=tk.EW, padx=5, pady=2
        )

        # Статус конвертации
        self.convert_status = tk.StringVar(value="Готов к конвертации")
        ttk.Label(main_frame, textvariable=self.convert_status).grid(
            row=6, column=0, columnspan=3, pady=10
        )

        # Кнопки
        btn_frame = ttk.Frame(main_frame)
        btn_frame.grid(row=7, column=0, columnspan=3, pady=10)

        ttk.Button(btn_frame, text="Конвертировать", command=self.convert_file).pack(
            side=tk.LEFT, padx=10
        )
        ttk.Button(btn_frame, text="Закрыть", command=converter_win.destroy).pack(
            side=tk.LEFT, padx=10
        )

        # Настройка сетки
        main_frame.columnconfigure(1, weight=1)

    def browse_file(self, target_var):
        """Открываем диалог выбора файла"""
        file_path = filedialog.askopenfilename()
        if file_path:
            target_var.set(file_path)

    def browse_folder(self, target_var):
        """Открываем диалог выбора папки"""
        folder_path = filedialog.askdirectory()
        if folder_path:
            target_var.set(folder_path)

    def convert_file(self):
        """Выполняем конвертацию файла"""
        source = self.source_file.get()
        dest_folder = self.dest_folder.get()
        output_name = self.output_name.get()
        conversion_type = self.conversion_type.get()

        if not source or not os.path.exists(source):
            messagebox.showerror("Ошибка", "Пожалуйста, выберите исходный файл")
            return

        if not dest_folder or not os.path.exists(dest_folder):
            messagebox.showerror("Ошибка", "Пожалуйста, выберите папку назначения")
            return

        try:
            self.convert_status.set("Конвертация...")
            self.root.update()

            # Определяем расширение в зависимости от типа конвертации
            ext_map = {
                "video_to_audio": ".mp3",
                "image_to_png": ".png",
                "image_to_jpg": ".jpg",
                "audio_to_mp3": ".mp3"
            }

            output_ext = ext_map.get(conversion_type, "")
            output_path = os.path.join(dest_folder, f"{output_name}{output_ext}")

            # Выполняем конвертацию в зависимости от типа
            if conversion_type == "video_to_audio":
                self.convert_video_to_audio(source, output_path)
            elif conversion_type.startswith("image_to_"):
                self.convert_image(source, output_path)
            elif conversion_type == "audio_to_mp3":
                self.convert_audio_to_mp3(source, output_path)

            self.convert_status.set(f"Конвертация завершена: {os.path.basename(output_path)}")
            messagebox.showinfo("Успех", f"Файл успешно сконвертирован:\n{output_path}")

        except Exception as e:
            self.convert_status.set("Ошибка конвертации")
            messagebox.showerror("Ошибка", f"Не удалось выполнить конвертацию: {str(e)}")
            print(f"Ошибка конвертации: {e}")

    def convert_video_to_audio(self, input_path, output_path):
        """Конвертируем видео в аудио (MP3)"""
        try:
            # Используем moviepy для конвертации
            video = VideoFileClip(input_path)
            audio = video.audio
            audio.write_audiofile(output_path, verbose=False, logger=None)
            audio.close()
            video.close()
        except Exception as e:
            # Fallback: используем ffmpeg если moviepy не доступен
            try:
                if not shutil.which("ffmpeg"):
                    raise Exception("FFmpeg не установлен")

                cmd = [
                    "ffmpeg", "-i", input_path,
                    "-vn", "-acodec", "libmp3lame",
                    "-ab", "192k", output_path,
                    "-y"
                ]
                subprocess.run(cmd, check=True, capture_output=True)
            except Exception as fallback_error:
                raise Exception(f"Ошибка при конвертации видео: {fallback_error}")

    def convert_image(self, input_path, output_path):
        """Конвертируем изображения между форматами"""
        try:
            img = Image.open(input_path)

            # Конвертируем в RGB для JPG
            if output_path.lower().endswith(('.jpg', '.jpeg')):
                if img.mode in ("RGBA", "P"):
                    img = img.convert("RGB")

            img.save(output_path)
        except Exception as e:
            raise Exception(f"Ошибка при конвертации изображения: {str(e)}")

    def convert_audio_to_mp3(self, input_path, output_path):
        """Конвертируем аудио в MP3"""
        try:
            # Используем pydub для конвертации
            audio = AudioSegment.from_file(input_path)
            audio.export(output_path, format="mp3")
        except Exception as e:
            # Fallback: используем ffmpeg
            try:
                if not shutil.which("ffmpeg"):
                    raise Exception("FFmpeg не установлен")

                cmd = [
                    "ffmpeg", "-i", input_path,
                    "-codec:a", "libmp3lame", "-qscale:a", "2",
                    output_path, "-y"
                ]
                subprocess.run(cmd, check=True, capture_output=True)
            except Exception as fallback_error:
                raise Exception(f"Ошибка при конвертации аудио: {fallback_error}")

    def cut_text(self):
        """Вырезаем текст"""
        self.text_area.event_generate("<<Cut>>")

    def copy_text(self):
        """Копируем текст"""
        self.text_area.event_generate("<<Copy>>")

    def paste_text(self):
        """Вставляем текст"""
        self.text_area.event_generate("<<Paste>>")

    def clear_text(self):
        """Очищаем текстовое поле"""
        self.text_area.delete("1.0", tk.END)

    # Методы для работы с текстом
    def get_text(self):
        """Получаем текст из текстового поля"""
        return self.text_area.get("1.0", tk.END).strip()

    def set_text(self, text):
        """Устанавливаем текст в текстовое поле"""
        self.text_area.delete("1.0", tk.END)
        self.text_area.insert("1.0", text)
        self.add_to_history(text)

    def paste_from_clipboard(self):
        """Вставляем текст из буфера обмена"""
        try:
            text = pyperclip.paste()
            self.set_text(text)
            self.update_status("Текст вставлен из буфера")
        except:
            messagebox.showerror("Ошибка", "Не удалось получить текст из буфера обмена")
            self.update_status("Ошибка вставки из буфера")

    def copy_to_clipboard(self):
        """Копируем текст в буфер обмена"""
        text = self.get_text()
        if text:
            pyperclip.copy(text)
            self.update_status("Текст скопирован в буфер обмена")
        else:
            messagebox.showwarning("Предупреждение", "Текст для копирования пуст")
            self.update_status("Нет текста для копирования")

    def delete_words(self):
        """Удаляем выбранные слова"""
        words = simpledialog.askstring("Удаление слов", "Введите слова через запятую:")
        if not words:
            return

        text = self.get_text()
        for word in words.split(','):
            cleaned_word = word.strip()
            if cleaned_word:
                text = text.replace(cleaned_word, '')
        self.set_text(text)
        self.update_status("Слова удалены")

    def delete_letters(self):
        """Удаляем выбранные буквы"""
        letters = simpledialog.askstring("Удаление букв", "Введите буквы без разделителей:")
        if not letters:
            return

        text = self.get_text()
        for letter in letters:
            text = text.replace(letter, '')
        self.set_text(text)
        self.update_status("Буквы удалены")

    def delete_digits(self):
        """Удаляем выбранные цифры"""
        digits = simpledialog.askstring("Удаление цифр", "Введите цифры без разделителей:")
        if not digits:
            return

        text = self.get_text()
        for digit in digits:
            text = text.replace(digit, '')
        self.set_text(text)
        self.update_status("Цифры удалены")

    def remove_all_digits(self):
        """Удаляем все цифры"""
        text = self.get_text()
        text = ''.join(c for c in text if not c.isdigit())
        self.set_text(text)
        self.update_status("Все цифры удалены")

    def remove_all_letters(self):
        """Удаляем все буквы"""
        text = self.get_text()
        text = ''.join(c for c in text if not c.isalpha())
        self.set_text(text)
        self.update_status("Все буквы удалены")

    def to_uppercase(self):
        """Преобразуем текст в верхний регистр"""
        text = self.get_text()
        self.set_text(text.upper())
        self.update_status("Текст преобразован в верхний регистр")

    def to_lowercase(self):
        """Преобразуем текст в нижний регистр"""
        text = self.get_text()
        self.set_text(text.lower())
        self.update_status("Текст преобразован в нижний регистр")

    def init_layout_dicts(self):
        """Инициализируем словари для смены раскладки"""
        en_lower = "qwertyuiop[]asdfghjkl;'zxcvbnm,."
        ru_lower = "йцукенгшщзхъфывапролджэячсмитьбю"
        en_upper = "QWERTYUIOP{}ASDFGHJKL:\"ZXCVBNM<>"
        ru_upper = "ЙЦУКЕНГШЩЗХЪФЫВАПРОЛДЖЭЯЧСМИТЬБЮ"

        # Создаем словари для преобразования
        self.en_to_ru = dict(zip(en_lower + en_upper, ru_lower + ru_upper))
        self.ru_to_en = dict(zip(ru_lower + ru_upper, en_lower + en_upper))

    def change_layout(self):
        """Меняем раскладку текста"""
        text = self.get_text()
        converted = []
        for char in text:
            if char in self.en_to_ru:
                converted.append(self.en_to_ru[char])
            elif char in self.ru_to_en:
                converted.append(self.ru_to_en[char])
            else:
                converted.append(char)
        self.set_text(''.join(converted))
        self.update_status("Раскладка изменена")

    def translate_text(self):
        """Открываем перевод текста в Google Translate"""
        text = self.get_text()
        if text:
            # Формируем URL для Google Translate
            url = f"https://translate.google.com/?sl=auto&tl=en&text={text}"
            webbrowser.open(url)
            self.update_status("Открыт переводчик Google")
        else:
            messagebox.showwarning("Предупреждение", "Нет текста для перевода")
            self.update_status("Нет текста для перевода")

    def open_settings(self):
        """Открываем окно настроек горячих клавиш"""
        settings_win = tk.Toplevel(self.root)
        settings_win.title("Настройки горячих клавиш")
        settings_win.geometry("500x400")
        settings_win.grab_set()

        tk.Label(settings_win, text="Настройте горячие клавиши:", font=("Arial", 12, "bold")).pack(pady=10)

        frame = tk.Frame(settings_win)
        frame.pack(padx=20, pady=10, fill=tk.BOTH, expand=True)

        # Создаем поля для ввода
        entries = {}
        for i, (hotkey, description) in enumerate(self.hotkeys.items()):
            row = tk.Frame(frame)
            row.pack(fill=tk.X, pady=2)

            lbl = tk.Label(row, text=f"{description}:", width=25, anchor=tk.W)
            lbl.pack(side=tk.LEFT)

            ent = tk.Entry(row, width=10)
            ent.insert(0, hotkey)
            ent.pack(side=tk.LEFT, padx=5)
            entries[description] = ent

        # Настройки глобальной горячей клавиши
        tk.Label(settings_win, text="Глобальная горячая клавиша:", font=("Arial", 10, "bold")).pack(pady=10,
                                                                                                    anchor=tk.W)

        hotkey_frame = tk.Frame(settings_win)
        hotkey_frame.pack(fill=tk.X, padx=20, pady=5)

        tk.Label(hotkey_frame, text="Сочетание клавиш:").pack(side=tk.LEFT)
        hotkey_entry = tk.Entry(hotkey_frame, width=20)
        hotkey_entry.insert(0, self.hotkey_combination)
        hotkey_entry.pack(side=tk.LEFT, padx=5)

        # Кнопки сохранения/отмены
        btn_frame = tk.Frame(settings_win)
        btn_frame.pack(pady=15)

        def save_all_settings():
            self.save_settings(entries, settings_win)
            new_hotkey = hotkey_entry.get().strip().lower()
            if new_hotkey and new_hotkey != self.hotkey_combination:
                try:
                    keyboard.remove_hotkey(self.hotkey_combination)
                    self.hotkey_combination = new_hotkey
                    keyboard.add_hotkey(self.hotkey_combination, self.global_hotkey_pressed)
                    self.update_status(f"Горячая клавиша изменена на: {self.hotkey_combination.upper()}")
                except Exception as e:
                    messagebox.showerror("Ошибка", f"Не удалось изменить глобальную горячую клавишу: {str(e)}")

        tk.Button(btn_frame, text="Сохранить", command=save_all_settings).pack(side=tk.LEFT, padx=10)
        tk.Button(btn_frame, text="Отмена", command=settings_win.destroy).pack(side=tk.LEFT, padx=10)

    def save_settings(self, entries, window):
        """Сохраняем настройки из формы"""
        new_hotkeys = {}
        for description, entry in entries.items():
            hotkey = entry.get().strip()
            if hotkey:
                new_hotkeys[hotkey] = description

        if new_hotkeys:
            self.hotkeys = new_hotkeys
            self.save_hotkeys()
            messagebox.showinfo("Успех", "Настройки сохранены!\nПерезапустите приложение для применения изменений.")
            window.destroy()

    # Методы для работы с треем
    def create_tray_icon(self):
        """Создаем иконку для системного трея"""
        # Создаем временное изображение для иконки
        image = Image.new('RGB', (64, 64), 'white')

        # Меню для иконки в трее
        menu = (
            TrayMenuItem('Открыть', self.restore_from_tray),
            TrayMenuItem('Выход', self.exit_app)
        )

        self.tray_icon = Icon("text_editor", image, "Текстовый редактор", menu)

    def minimize_to_tray(self):
        """Сворачиваем окно в системный трей"""
        if not self.tray_active:
            self.create_tray_icon()
            self.tray_thread = threading.Thread(target=self.tray_icon.run, daemon=True)
            self.tray_thread.start()
            self.tray_active = True
        self.root.withdraw()  # Скрываем главное окно

    def restore_from_tray(self):
        """Восстанавливаем окно из трея"""
        if self.tray_active and self.tray_icon:
            self.tray_icon.stop()
            self.tray_active = False
        self.root.deiconify()  # Показываем главное окно
        self.root.lift()
        self.root.focus_force()

    def exit_app(self):
        """Полностью выходим из приложения"""
        if self.tray_active and self.tray_icon:
            self.tray_icon.stop()
        self.root.destroy()

    # Методы для истории и избранного
    def create_history_favorites_tabs(self):
        """Создаем вкладки истории и избранного"""
        # Вкладка истории
        self.history_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.history_frame, text="История")
        self.setup_history_ui()

        # Вкладка избранного
        self.favorites_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.favorites_frame, text="Избранное")
        self.setup_favorites_ui()

    def setup_history_ui(self):
        """Настраиваем UI для истории"""
        # Очищаем фрейм истории
        for widget in self.history_frame.winfo_children():
            widget.destroy()

        # Поисковая строка
        search_frame = tk.Frame(self.history_frame)
        search_frame.pack(fill=tk.X, padx=10, pady=5)

        self.history_search_var = tk.StringVar()
        search_entry = tk.Entry(search_frame, textvariable=self.history_search_var, width=40)
        search_entry.pack(side=tk.LEFT, padx=5)
        search_entry.bind("<KeyRelease>", self.filter_history)

        tk.Button(search_frame, text="Поиск", command=self.filter_history).pack(side=tk.LEFT, padx=5)
        tk.Button(search_frame, text="Очистить", command=self.clear_history_search).pack(side=tk.LEFT, padx=5)

        # Фрейм для списка с прокруткой
        list_frame = tk.Frame(self.history_frame)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # Полоса прокрутки
        scrollbar = tk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Список истории
        self.history_listbox = tk.Listbox(
            list_frame,
            yscrollcommand=scrollbar.set,
            width=100,
            height=20
        )
        self.history_listbox.pack(fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.history_listbox.yview)

        # Кнопки действий
        btn_frame = tk.Frame(self.history_frame)
        btn_frame.pack(fill=tk.X, padx=10, pady=5)

        tk.Button(btn_frame, text="Восстановить", command=self.restore_from_history).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="В избранное", command=self.add_to_favorites_from_history).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Удалить", command=self.delete_from_history).pack(side=tk.LEFT, padx=5)

        # Заполняем историю
        self.populate_history()

    def setup_favorites_ui(self):
        """Настраиваем UI для избранного"""
        # Очищаем фрейм избранного
        for widget in self.favorites_frame.winfo_children():
            widget.destroy()

        # Поисковая строка
        search_frame = tk.Frame(self.favorites_frame)
        search_frame.pack(fill=tk.X, padx=10, pady=5)

        self.favorites_search_var = tk.StringVar()
        search_entry = tk.Entry(search_frame, textvariable=self.favorites_search_var, width=40)
        search_entry.pack(side=tk.LEFT, padx=5)
        search_entry.bind("<KeyRelease>", self.filter_favorites)

        tk.Button(search_frame, text="Поиск", command=self.filter_favorites).pack(side=tk.LEFT, padx=5)
        tk.Button(search_frame, text="Очистить", command=self.clear_favorites_search).pack(side=tk.LEFT, padx=5)

        # Фрейм для списка с прокруткой
        list_frame = tk.Frame(self.favorites_frame)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # Полоса прокрутки
        scrollbar = tk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Список избранного
        self.favorites_listbox = tk.Listbox(
            list_frame,
            yscrollcommand=scrollbar.set,
            width=100,
            height=20
        )
        self.favorites_listbox.pack(fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.favorites_listbox.yview)

        # Кнопки действий
        btn_frame = tk.Frame(self.favorites_frame)
        btn_frame.pack(fill=tk.X, padx=10, pady=5)

        tk.Button(btn_frame, text="Копировать", command=self.copy_from_favorites).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Удалить", command=self.delete_from_favorites).pack(side=tk.LEFT, padx=5)

        # Заполняем избранное
        self.populate_favorites()

    def populate_history(self):
        """Заполняем список истории"""
        self.history_listbox.delete(0, tk.END)
        for item in reversed(self.history):
            preview = item['text'][:100] + "..." if len(item['text']) > 100 else item['text']
            self.history_listbox.insert(tk.END, f"{item['timestamp']}: {preview}")
            self.history_listbox.itemconfig(tk.END, {'fg': 'gray'})

    def populate_favorites(self):
        """Заполняем список избранного"""
        self.favorites_listbox.delete(0, tk.END)
        for item in self.favorites:
            preview = item['text'][:100] + "..." if len(item['text']) > 100 else item['text']
            self.favorites_listbox.insert(tk.END, f"{item['timestamp']}: {preview}")
            self.favorites_listbox.itemconfig(tk.END, {'fg': 'blue'})

    def filter_history(self, event=None):
        """Фильтруем историю по поисковому запросу"""
        query = self.history_search_var.get().lower()
        self.history_listbox.delete(0, tk.END)

        for item in reversed(self.history):
            if query in item['text'].lower():
                preview = item['text'][:100] + "..." if len(item['text']) > 100 else item['text']
                self.history_listbox.insert(tk.END, f"{item['timestamp']}: {preview}")
                self.history_listbox.itemconfig(tk.END, {'fg': 'gray'})

    def filter_favorites(self, event=None):
        """Фильтруем избранное по поисковому запросу"""
        query = self.favorites_search_var.get().lower()
        self.favorites_listbox.delete(0, tk.END)

        for item in self.favorites:
            if query in item['text'].lower():
                preview = item['text'][:100] + "..." if len(item['text']) > 100 else item['text']
                self.favorites_listbox.insert(tk.END, f"{item['timestamp']}: {preview}")
                self.favorites_listbox.itemconfig(tk.END, {'fg': 'blue'})

    def clear_history_search(self):
        """Очищаем поиск в истории"""
        self.history_search_var.set("")
        self.populate_history()

    def clear_favorites_search(self):
        """Очищаем поиск в избранном"""
        self.favorites_search_var.set("")
        self.populate_favorites()

    def add_to_history(self, text):
        """Добавляем текст в историю"""
        # Не добавляем пустые или повторные записи
        if not text or (self.history and self.history[-1]['text'] == text):
            return

        self.history.append({
            "text": text,
            "timestamp": self.get_current_time()
        })
        self.save_data("history.json", self.history)

        # Обновляем список если вкладка активна
        if self.notebook.index(self.notebook.select()) == 1:
            self.populate_history()

    def restore_from_history(self):
        """Восстанавливаем текст из истории"""
        selected_index = self.history_listbox.curselection()
        if not selected_index:
            return

        index = selected_index[0]
        # Получаем реальный индекс в истории (с учетом реверса)
        real_index = len(self.history) - 1 - index
        if 0 <= real_index < len(self.history):
            self.set_text(self.history[real_index]['text'])

    def add_to_favorites_from_history(self):
        """Добавляем в избранное из истории"""
        selected_index = self.history_listbox.curselection()
        if not selected_index:
            return

        index = selected_index[0]
        # Получаем реальный индекс в истории (с учетом реверса)
        real_index = len(self.history) - 1 - index
        if 0 <= real_index < len(self.history):
            self.add_to_favorites(self.history[real_index]['text'])

    def delete_from_history(self):
        """Удаляем запись из истории"""
        selected_index = self.history_listbox.curselection()
        if not selected_index:
            return

        index = selected_index[0]
        # Получаем реальный индекс в истории (с учетом реверса)
        real_index = len(self.history) - 1 - index
        if 0 <= real_index < len(self.history):
            del self.history[real_index]
            self.save_data("history.json", self.history)
            self.populate_history()

    def copy_from_favorites(self):
        """Копируем текст из избранного"""
        selected_index = self.favorites_listbox.curselection()
        if not selected_index:
            return

        index = selected_index[0]
        if 0 <= index < len(self.favorites):
            text = self.favorites[index]['text']
            pyperclip.copy(text)
            self.update_status("Текст из избранного скопирован в буфер")

    def delete_from_favorites(self):
        """Удаляем запись из избранного"""
        selected_index = self.favorites_listbox.curselection()
        if not selected_index:
            return

        index = selected_index[0]
        if 0 <= index < len(self.favorites):
            del self.favorites[index]
            self.save_data("favorites.json", self.favorites)
            self.populate_favorites()

    def add_to_favorites(self, text):
        """Добавляем текст в избранное"""
        # Проверяем, нет ли уже такого текста в избранном
        for item in self.favorites:
            if item['text'] == text:
                messagebox.showinfo("Информация", "Текст уже в избранном")
                return

        self.favorites.append({
            "text": text,
            "timestamp": self.get_current_time()
        })
        self.save_data("favorites.json", self.favorites)
        self.populate_favorites()
        messagebox.showinfo("Успех", "Текст добавлен в избранное")

    def get_current_time(self):
        """Получаем текущее время в формате строки"""
        from datetime import datetime
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Методы для работы с файлами
    def open_file(self):
        """Открываем текстовый файл"""
        file_path = filedialog.askopenfilename(
            filetypes=[
                ("Текстовые файлы", "*.txt"),
                ("CSV файлы", "*.csv"),
                ("JSON файлы", "*.json"),
                ("XML файлы", "*.xml"),
                ("Все файлы", "*.*")
            ]
        )

        if not file_path:
            return

        try:
            # Определяем кодировку
            with open(file_path, 'rb') as f:
                raw_data = f.read()
                encoding = chardet.detect(raw_data)['encoding'] or 'utf-8'

            # Читаем файл
            with open(file_path, 'r', encoding=encoding) as f:
                content = f.read()
                self.set_text(content)
                self.update_status(f"Файл загружен: {file_path}")

        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось открыть файл: {str(e)}")
            self.update_status(f"Ошибка загрузки файла: {str(e)}")

    def save_file(self):
        """Сохраняем текст в файл"""
        file_path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[
                ("Текстовые файлы", "*.txt"),
                ("Все файлы", "*.*")
            ]
        )

        if not file_path:
            return

        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(self.get_text())
            self.update_status(f"Файл сохранен: {file_path}")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось сохранить файл: {str(e)}")
            self.update_status(f"Ошибка сохранения файла: {str(e)}")

    # Методы для работы с текстом (продолжение)
    def find_replace(self):
        """Открываем диалог поиска и замены"""
        dialog = tk.Toplevel(self.root)
        dialog.title("Найти и заменить")
        dialog.geometry("400x250")
        dialog.grab_set()

        tk.Label(dialog, text="Найти:").grid(row=0, column=0, padx=10, pady=5, sticky=tk.W)
        find_entry = tk.Entry(dialog, width=30)
        find_entry.grid(row=0, column=1, padx=10, pady=5, sticky=tk.EW)

        tk.Label(dialog, text="Заменить на:").grid(row=1, column=0, padx=10, pady=5, sticky=tk.W)
        replace_entry = tk.Entry(dialog, width=30)
        replace_entry.grid(row=1, column=1, padx=10, pady=5, sticky=tk.EW)

        case_var = tk.IntVar()
        tk.Checkbutton(dialog, text="Учитывать регистр", variable=case_var).grid(row=2, column=0, columnspan=2, padx=10,
                                                                                 pady=5, sticky=tk.W)

        whole_word_var = tk.IntVar()
        tk.Checkbutton(dialog, text="Слово целиком", variable=whole_word_var).grid(row=3, column=0, columnspan=2,
                                                                                   padx=10, pady=5, sticky=tk.W)

        # Функции замены
        def find_next():
            text = self.text_area.get("1.0", tk.END)
            pattern = find_entry.get()

            if not pattern:
                return

            if whole_word_var.get():
                pattern = r"\b" + re.escape(pattern) + r"\b"

            flags = 0 if case_var.get() else re.IGNORECASE
            match = re.search(pattern, text, flags)

            if match:
                start_index = f"1.0 + {match.start()} chars"
                end_index = f"1.0 + {match.end()} chars"
                self.text_area.tag_remove("highlight", "1.0", tk.END)
                self.text_area.tag_add("highlight", start_index, end_index)
                self.text_area.tag_config("highlight", background="yellow")
                self.text_area.focus()
                self.text_area.see(start_index)

        def replace_one():
            if self.text_area.tag_ranges("highlight"):
                self.text_area.delete("highlight.first", "highlight.last")
                self.text_area.insert("highlight.first", replace_entry.get())
                self.text_area.tag_remove("highlight", "1.0", tk.END)
            find_next()

        def replace_all():
            text = self.text_area.get("1.0", tk.END)
            pattern = find_entry.get()
            replace_with = replace_entry.get()

            if not pattern:
                return

            if whole_word_var.get():
                pattern = r"\b" + re.escape(pattern) + r"\b"

            flags = 0 if case_var.get() else re.IGNORECASE
            new_text = re.sub(pattern, replace_with, text, flags=flags)
            self.set_text(new_text)
            dialog.destroy()

        # Кнопки
        btn_frame = tk.Frame(dialog)
        btn_frame.grid(row=4, column=0, columnspan=2, pady=10)

        tk.Button(btn_frame, text="Найти", command=find_next).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Заменить", command=replace_one).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Заменить все", command=replace_all).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Отмена", command=dialog.destroy).pack(side=tk.LEFT, padx=5)

    def show_stats(self):
        """Показываем статистику текста"""
        text = self.get_text()
        dialog = tk.Toplevel(self.root)
        dialog.title("Статистика текста")
        dialog.geometry("300x250")

        # Подсчет статистики
        chars = len(text)
        chars_no_space = len(text.replace(" ", ""))
        words = len(text.split())
        lines = text.count('\n') + 1
        digits = sum(c.isdigit() for c in text)
        letters = sum(c.isalpha() for c in text)
        special = chars - digits - letters - text.count(' ') - text.count('\n')

        # Отображение статистики
        stats = [
            f"Символов: {chars}",
            f"Символов (без пробелов): {chars_no_space}",
            f"Слов: {words}",
            f"Строк: {lines}",
            f"Цифр: {digits}",
            f"Букв: {letters}",
            f"Спецсимволов: {special}"
        ]

        for i, stat in enumerate(stats):
            tk.Label(dialog, text=stat, anchor=tk.W).pack(fill=tk.X, padx=20, pady=5)

        # Частота символов
        tk.Label(dialog, text="\nЧастота символов:", font=("Arial", 9, "bold")).pack(anchor=tk.W, padx=20)

        from collections import Counter
        char_counter = Counter(text)
        top_chars = char_counter.most_common(5)

        for char, count in top_chars:
            if char == '\n':
                char = "\\n"
            elif char == ' ':
                char = "Пробел"
            tk.Label(dialog, text=f"'{char}': {count} раз", anchor=tk.W).pack(fill=tk.X, padx=30, pady=2)

    def remove_emojis(self):
        """Удаляем смайлы и эмодзи из текста"""
        text = self.get_text()

        # Удаление эмодзи и смайлов
        emoji_pattern = re.compile("["
                                   u"\U0001F600-\U0001F64F"  # emoticons
                                   u"\U0001F300-\U0001F5FF"  # symbols & pictographs
                                   u"\U0001F680-\U0001F6FF"  # transport & map symbols
                                   u"\U0001F1E0-\U0001F1FF"  # flags (iOS)
                                   u"\U00002500-\U00002BEF"  # chinese char
                                   u"\U00002702-\U000027B0"
                                   u"\U00002702-\U000027B0"
                                   u"\U000024C2-\U0001F251"
                                   u"\U0001f926-\U0001f937"
                                   u"\U00010000-\U0010ffff"
                                   u"\u2640-\u2642"
                                   u"\u2600-\u2B55"
                                   u"\u200d"
                                   u"\u23cf"
                                   u"\u23e9"
                                   u"\u231a"
                                   u"\ufe0f"  # dingbats
                                   u"\u3030"
                                   "]+", flags=re.UNICODE)

        # Удаляем классические текстовые смайлы
        text_smiles = [":\)", ":D", ":\(=", ":P", ";\)", ":\|", ":\/", ":O", ":\*", ":'\("]
        for smile in text_smiles:
            text = re.sub(re.escape(smile), "", text)

        # Удаляем эмодзи
        clean_text = emoji_pattern.sub(r'', text)

        self.set_text(clean_text)
        self.update_status("Смайлы и эмодзи удалены")

    def generate_qrcode(self):
        """Генерируем QR-код для текста"""
        text = self.get_text()
        if not text:
            messagebox.showwarning("Предупреждение", "Нет текста для генерации QR-кода")
            self.update_status("Нет текста для QR-кода")
            return

        try:
            # Создаем QR-код
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(text)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")

            # Конвертируем в формат, который может отобразить Tkinter
            img_tk = ImageTk.PhotoImage(img)

            # Создаем диалоговое окно
            dialog = tk.Toplevel(self.root)
            dialog.title("QR-код текста")

            # Отображаем QR-код
            label = tk.Label(dialog, image=img_tk)
            label.image = img_tk  # сохраняем ссылку
            label.pack(padx=20, pady=10)

            # Кнопки
            btn_frame = tk.Frame(dialog)
            btn_frame.pack(pady=10)

            tk.Button(btn_frame, text="Копировать", command=lambda: self.copy_qrcode(img)).pack(side=tk.LEFT, padx=10)
            tk.Button(btn_frame, text="Закрыть", command=dialog.destroy).pack(side=tk.LEFT, padx=10)

            self.update_status("QR-код сгенерирован")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось создать QR-код: {str(e)}")
            self.update_status(f"Ошибка генерации QR-кода: {str(e)}")

    def copy_qrcode(self, img):
        """Копируем QR-код в буфер обмена"""
        # Для Windows
        if os.name == 'nt':
            try:
                # Конвертируем в BMP
                output = BytesIO()
                img.save(output, format="BMP")
                data = output.getvalue()[14:]  # Пропускаем заголовок BMP
                output.close()

                # Копируем в буфер обмена
                win32clipboard.OpenClipboard()
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardData(win32clipboard.CF_DIB, data)
                win32clipboard.CloseClipboard()
                self.update_status("QR-код скопирован в буфер обмена")
            except Exception as e:
                self.update_status(f"Ошибка копирования: {str(e)}")
        else:
            # Для других ОС просто сохраняем в файл
            try:
                file_path = "qrcode.png"
                img.save(file_path)
                pyperclip.copy(file_path)
                self.update_status(f"QR-код сохранен в {file_path}")
            except Exception as e:
                self.update_status(f"Ошибка копирования: {str(e)}")

    # Вспомогательные методы
    def update_status(self, message):
        """Обновляем статусную строку"""
        self.status_var.set(f"Статус: {message}")


if __name__ == "__main__":
    root = tk.Tk()
    app = TextEditorApp(root)
    root.mainloop()
