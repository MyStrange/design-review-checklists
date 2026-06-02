"""Извлечение чек-листа из расшифровки через бесплатный LLM API.

Провайдер по умолчанию — Google Gemini (бесплатный тир). Слой абстракции
позволяет добавить других провайдеров (Groq, OpenRouter и т.п.), поменяв
переменную окружения LLM_PROVIDER, без изменений в остальном коде.

Зависимостей нет — только стандартная библиотека Python.
"""
import json
import time
import urllib.request
import urllib.error

from . import config

# Схема ответа (OpenAPI-подмножество, которое понимает Gemini).
SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "designers": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "name": {"type": "STRING"},
                    "projects": {
                        "type": "ARRAY",
                        "items": {
                            "type": "OBJECT",
                            "properties": {
                                "name": {"type": "STRING"},
                                "items": {
                                    "type": "ARRAY",
                                    "items": {
                                        "type": "OBJECT",
                                        "properties": {
                                            "text": {"type": "STRING"},
                                            "tag": {"type": "STRING", "enum": ["ux", "dev", "product", "seo", "legal", "branding"]},
                                        },
                                        "required": ["text", "tag"],
                                    },
                                },
                            },
                            "required": ["name", "items"],
                        },
                    },
                },
                "required": ["name", "projects"],
            },
        }
    },
    "required": ["designers"],
}

PROMPT = """Ты — ассистент, который разбирает расшифровку встречи дизайн-ревью и составляет чек-листы правок.

На вход — текстовая расшифровка ОДНОЙ встречи. На ней один или несколько дизайнеров показывают свои проекты и получают фидбэк.

Задача: для КАЖДОГО дизайнера, который показывал работу, выдели:
- имя дизайнера (как его называют на встрече);
- проект(ы), которые он показывал (обычно один, иногда два);
- конкретные пункты фидбэка/правок по каждому проекту — короткие, по делу, в повелительном наклонении («Увеличить отступы между карточками», «Переписать заголовок на экране оплаты»). Каждый пункт = одно действие.

Для каждого пункта проставь тег (поле tag) — нужен ли тут другой специалист:
- "ux" — обычная правка по дизайну/интерфейсу (БОЛЬШИНСТВО правок, ставь по умолчанию);
- "dev" — нужна разработка или техническая реализация;
- "product" — нужно сходить к продакту: уточнить, согласовать, принять продуктовое решение;
- "seo" — вопрос к SEO-команде;
- "legal" — нужен юрист или юридические требования;
- "branding" — согласование с брендингом или гайдлайнами бренда.
Если это просто правка дизайна — ставь "ux".

Правила:
- Бери только конкретные правки и замечания, которые нужно учесть. Не включай приветствия, смолл-ток, обсуждение расписания и оргвопросов.
- Если имя дизайнера явно не названо — используй «Не указан».
- Если название проекта не прозвучало — используй «Без названия».
- Пиши пункты на русском, кратко и конкретно.
- НЕ используй круглые скобки. Если нужно уточнение или пример — впиши его в фразу или через тире «—», но скобок не ставь.
- Кавычки используй только «ёлочки» («вот так»). Не ставь прямые (") и английские кавычки.
- Ничего не выдумывай. Если правок по проекту нет — верни пустой список items.

Верни строго JSON по заданной схеме, без markdown и пояснений."""


def extract_checklist(transcript):
    """Возвращает dict вида {"designers": [...]}. Бросает исключение при ошибке."""
    provider = config.LLM_PROVIDER.lower()
    if provider == "gemini":
        return _gemini(transcript)
    raise ValueError("Неизвестный LLM-провайдер: %r" % config.LLM_PROVIDER)


def _gemini(transcript):
    if not config.GEMINI_API_KEY:
        raise RuntimeError("Не задан GEMINI_API_KEY")

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent?key=%s"
        % (config.GEMINI_MODEL, config.GEMINI_API_KEY)
    )
    payload = {
        "contents": [
            {"parts": [{"text": PROMPT + "\n\n=== РАСШИФРОВКА ===\n" + transcript}]}
        ],
        "generationConfig": {
            "temperature": 0.2,
            "responseMimeType": "application/json",
            "responseSchema": SCHEMA,
        },
    }
    body = json.dumps(payload).encode("utf-8")

    last_err = None
    for attempt in range(3):
        req = urllib.request.Request(
            url, data=body, headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                obj = json.loads(resp.read().decode("utf-8"))
            text = obj["candidates"][0]["content"]["parts"][0]["text"]
            result = json.loads(text)
            result.setdefault("designers", [])
            return result
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")
            last_err = "HTTP %s: %s" % (e.code, detail)
            if e.code in (429, 500, 503):  # перегрузка/лимит — подождём и повторим
                time.sleep(5 * (attempt + 1))
                continue
            break
        except Exception as e:  # сеть, парсинг и т.п.
            last_err = str(e)
            time.sleep(3)
            continue

    raise RuntimeError("Ошибка обращения к Gemini: %s" % last_err)
