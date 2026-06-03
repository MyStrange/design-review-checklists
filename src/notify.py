"""Уведомления о новом чек-листе в мессенджер.

По умолчанию — Telegram (бот создаётся без админа через @BotFather).
Можно переключить на Яндекс Мессенджер переменной NOTIFY_PROVIDER=yandex.
Только стандартная библиотека Python.

Полезные команды:
  python -m src.notify --updates        # показать getUpdates (узнать chat_id)
  python -m src.notify --test "привет"  # отправить тестовое сообщение
"""
import argparse
import json
import urllib.error
import urllib.request
from datetime import datetime

from . import config

RU_MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня",
             "июля", "августа", "сентября", "октября", "ноября", "декабря"]


def _http(url, payload=None, headers=None):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, headers=headers or {})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status, r.read().decode("utf-8", "replace")


# ---------- Telegram ----------
def _tg_url(method):
    return "https://api.telegram.org/bot%s/%s" % (config.TELEGRAM_BOT_TOKEN, method)


def _tg_send(text):
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        print("Telegram не настроен (нет токена/chat_id) — уведомление пропущено.")
        return False
    payload = {"chat_id": config.TELEGRAM_CHAT_ID, "text": text,
               "disable_web_page_preview": False}
    try:
        status, _ = _http(_tg_url("sendMessage"), payload, {"Content-Type": "application/json"})
        print("Telegram: отправлено (HTTP %s)" % status)
        return True
    except urllib.error.HTTPError as e:
        print("Telegram: ошибка HTTP %s: %s" % (e.code, e.read().decode("utf-8", "replace")))
    except Exception as e:
        print("Telegram: ошибка: %s" % e)
    return False


def _tg_updates():
    return _http(_tg_url("getUpdates"))


# ---------- Яндекс Мессенджер ----------
_YA_BASE = "https://botapi.messenger.yandex.net/bot/v1"


def _ya_headers():
    return {"Authorization": "OAuth " + config.YANDEX_BOT_TOKEN, "Content-Type": "application/json"}


def _ya_send(text):
    if not config.YANDEX_BOT_TOKEN or not config.YANDEX_BOT_CHAT_ID:
        print("Яндекс Мессенджер не настроен — уведомление пропущено.")
        return False
    try:
        status, _ = _http(_YA_BASE + "/messages/sendText/",
                          {"text": text, "chat_id": config.YANDEX_BOT_CHAT_ID}, _ya_headers())
        print("Яндекс Мессенджер: отправлено (HTTP %s)" % status)
        return True
    except urllib.error.HTTPError as e:
        print("Яндекс: ошибка HTTP %s: %s" % (e.code, e.read().decode("utf-8", "replace")))
    except Exception as e:
        print("Яндекс: ошибка: %s" % e)
    return False


def _ya_updates():
    return _http(_YA_BASE + "/messages/getUpdates/", {"limit": 100, "offset": 0}, _ya_headers())


# ---------- общий слой ----------
def _provider():
    return config.NOTIFY_PROVIDER.lower()


def send_text(text):
    return _ya_send(text) if _provider() == "yandex" else _tg_send(text)


def _fmt_date(iso):
    try:
        dt = datetime.strptime(iso, "%Y-%m-%d")
        return "%d %s" % (dt.day, RU_MONTHS[dt.month - 1])
    except Exception:
        return iso or ""


def notify_new_session(session):
    """Шлёт уведомление об одном новом разобранном ревью."""
    designers = session.get("designers", [])
    n_items = sum(len(p.get("items", [])) for d in designers for p in d.get("projects", []))
    head = "📋 Готов чек-лист ревью — %s" % _fmt_date(session.get("date", ""))
    extra = " · ".join([x for x in (session.get("part", ""), session.get("weekday", "")) if x])
    if extra:
        head += " (%s)" % extra
    lines = [head, "Дизайнеров: %d · правок: %d" % (len(designers), n_items)]
    if config.SITE_URL:
        lines.append(config.SITE_URL)
    send_text("\n".join(lines))


def _cli():
    ap = argparse.ArgumentParser(description="Уведомления о новом чек-листе")
    ap.add_argument("--updates", action="store_true", help="показать getUpdates (узнать chat_id)")
    ap.add_argument("--test", metavar="TEXT", help="отправить тестовое сообщение")
    args = ap.parse_args()

    if args.updates:
        try:
            status, body = _ya_updates() if _provider() == "yandex" else _tg_updates()
            print("provider:", _provider(), "| HTTP", status)
            try:
                print(json.dumps(json.loads(body), ensure_ascii=False, indent=2))
            except Exception:
                print(body)
        except urllib.error.HTTPError as e:
            print("Ошибка HTTP %s: %s" % (e.code, e.read().decode("utf-8", "replace")))
        return
    if args.test is not None:
        send_text(args.test)
        return
    ap.print_help()


if __name__ == "__main__":
    _cli()
