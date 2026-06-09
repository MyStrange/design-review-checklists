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

# --- Уведомления о новом чек-листе ---
NOTIFY_PROVIDER = os.environ.get("NOTIFY_PROVIDER", "telegram")  # telegram | yandex
# .get(...) or default — чтобы пустой секрет SITE_URL в GitHub Actions
# не затирал адрес и ссылка всегда попадала в уведомление.
SITE_URL = os.environ.get("SITE_URL") or "https://design-review-checklists-git-main-shsbs.vercel.app"
# Telegram (создаётся без админа через @BotFather)
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "-4161949965")  # группа «Дизайн Записи»
# Яндекс Мессенджер (нужен админ Яндекс 360)
YANDEX_BOT_TOKEN = os.environ.get("YANDEX_BOT_TOKEN", "")
YANDEX_BOT_CHAT_ID = os.environ.get("YANDEX_BOT_CHAT_ID", "")

# Телеграм-логины дизайнеров (короткое имя -> @username) — для тегов в уведомлении.
# Кого нет в карте — просто не тегаем.
TELEGRAM_USERNAMES = {
    "Костя": "@kosmatos_fx",
    "Аня": "@anyagrigoreva",
    "Ксюша": "@ks_pks",
    "Глеб": "@bobilion",
    "Глеб П.": "@gleb_baster",
    "Кариша": "@karina_lisunova",
    "Надя": "@My_Strange",
}


# --- Устойчивое сопоставление имён ---
# Нейросеть может выдать имя в любом виде: «Григорьева Анна Сергеевна»,
# «Анна Григорьева», «Анна Сергеевна Григорьева». Чтобы один и тот же человек
# не плодился как несколько «дизайнеров», сопоставляем по набору значимых частей
# имени (фамилия + имя), игнорируя отчество и порядок слов.

def _is_patronymic(token):
    """Отчество: …вич / …вна / …чна. («Анна», «Карина» не считаются.)"""
    t = token.lower()
    return t.endswith("ич") or t.endswith("вна") or t.endswith("чна")


def _name_key(full_name):
    """Множество частей имени без отчества — одинаково при любом порядке слов."""
    parts = (full_name or "").replace(".", " ").split()
    return frozenset(p.lower() for p in parts if p and not _is_patronymic(p))


def _detect_gender(full_name):
    """Пол по отчеству, а если его нет — по окончанию фамилии."""
    parts = (full_name or "").replace(".", " ").split()
    for p in parts:
        pl = p.lower()
        if pl.endswith("вна") or pl.endswith("чна"):
            return "f"
        if pl.endswith("ич"):
            return "m"
    for p in parts:
        if p.lower().endswith(("ова", "ева", "ина", "ская", "ая")):
            return "f"
    return "m"


# Окончания фамилий — чтобы автоматически отличить фамилию от имени у новых людей.
_SURNAME_SUFFIXES = ("ов", "ёв", "ев", "ова", "ёва", "ева", "ин", "ын", "ина",
                     "ына", "ский", "ская", "цкий", "цкая", "ской", "енко",
                     "ук", "юк", "ян", "дзе", "швили", "iй")


def _derive_short(full_name):
    """Авто-короткое имя для тех, кого ещё нет в NAME_MAP: «Имя Ф.».
    Детерминированно (не зависит от порядка слов), чтобы один человек не двоился."""
    parts = [p for p in (full_name or "").replace(".", " ").split()
             if p and not _is_patronymic(p)]
    if not parts:
        return (full_name or "").strip()
    cap = lambda w: w[:1].upper() + w[1:]
    if len(parts) == 1:
        return cap(parts[0])
    # фамилия = самый длинный токен с «фамильным» окончанием, иначе просто самый длинный
    surn_cands = [p for p in parts if p.lower().endswith(_SURNAME_SUFFIXES)] or parts
    surname = max(surn_cands, key=len)
    given_cands = [p for p in parts if p != surname] or parts
    given = min(given_cands, key=len)
    return "%s %s." % (cap(given), surname[:1].upper())


# Индексы строятся из NAME_MAP (ключи — полные ФИО с отчеством, формат надёжный).
_SHORT_BY_KEY = {_name_key(full): short for full, short in NAME_MAP.items()}
_GENDER_BY_KEY = {_name_key(full): _detect_gender(full) for full in NAME_MAP}


def short_name(full_name):
    """Короткое отображаемое имя по любому варианту записи ФИО.
    Известных берём из NAME_MAP; новых — авто («Имя Ф.»), чтобы не было дублей
    и не требовалось ничего дописывать руками."""
    if not (full_name or "").strip() or full_name == "Не указан":
        return "Не указан"
    return (NAME_MAP.get(full_name)
            or _SHORT_BY_KEY.get(_name_key(full_name))
            or _derive_short(full_name))


def gender(full_name):
    """Пол ('f'/'m'). Для известных людей берём из справочника, иначе — эвристика."""
    return _GENDER_BY_KEY.get(_name_key(full_name)) or _detect_gender(full_name)
