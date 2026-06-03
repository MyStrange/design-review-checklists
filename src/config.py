"""Конфигурация проекта.

Все секреты берутся из переменных окружения (в GitHub Actions — из Secrets).
В коде ничего секретного не хранится.
"""
import os
import pathlib

# --- Почта (IMAP) ---
IMAP_HOST = os.environ.get("IMAP_HOST", "imap.yandex.ru")
IMAP_PORT = int(os.environ.get("IMAP_PORT", "993"))
YANDEX_USER = os.environ.get("YANDEX_USER", "")            # полный адрес ящика, напр. name@company.ru
YANDEX_APP_PASSWORD = os.environ.get("YANDEX_APP_PASSWORD", "")

# --- Фильтр писем ---
REVIEW_SENDER = os.environ.get("REVIEW_SENDER", "keeper@telemost.yandex.ru")
SUBJECT_MUST_CONTAIN = os.environ.get("SUBJECT_MUST_CONTAIN", "Ревью Записи")
SEARCH_SINCE_DAYS = int(os.environ.get("SEARCH_SINCE_DAYS", "45"))

# --- LLM ---
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "gemini")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

# --- Пути / страница ---
ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA_FILE = ROOT / "data" / "checklists.json"
DOCS_DIR = ROOT / "docs"
SITE_TITLE = os.environ.get("SITE_TITLE", "Дизайн-ревью — чек-листы")

# Короткие отображаемые имена: полное имя из конспекта -> как показывать на странице.
# Полные имена в данных остаются; здесь только подпись. Добавляй новых людей по мере появления.
NAME_MAP = {
    "Маслянников Константин Андреевич": "Костя",
    "Григорьева Анна Сергеевна": "Аня",
    "Ткачева Надежда Сергеевна": "Надя",
    "Бобыльков Глеб Викторович": "Глеб",
    "Петрикова Ксения Дмитриевна": "Ксюша",
    "Вакуленко Юлия Юрьевна": "Юля",
    "Лисунова Карина Игоревна": "Кариша",
    "Петухов Глеб Игоревич": "Глеб П.",
}

# --- Яндекс Мессенджер (уведомления бота) ---
YANDEX_BOT_TOKEN = os.environ.get("YANDEX_BOT_TOKEN", "")
YANDEX_BOT_CHAT_ID = os.environ.get("YANDEX_BOT_CHAT_ID", "")
SITE_URL = os.environ.get("SITE_URL", "")
