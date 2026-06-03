"""Уведомления в Яндекс Мессенджер через Bot API.

При появлении нового чек-листа шлёт короткое сообщение в чат.
Только стандартная библиотека Python.
Док: https://yandex.com/support/yandex-360/business/admin/ru/messenger/bot-platform

Полезные команды для настройки:
  python -m src.notify --updates        # показать getUpdates (узнать chat_id чата)
  python -m src.notify --test "привет"  # отправить тестовое сообщение в chat_id
"""
import argparse
import json
import urllib.error
import urllib.request
from datetime import datetime

from . import config

API_BASE = "https://botapi.messenger.yandex.net/bot/v1"
RU_MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня",
             "июля", "августа", "сентября", "октября", "ноября", "декабря"]


def _post(path, payload):
    if not config.YANDEX_BOT_TOKEN:
        raise RuntimeError("Не задан YANDEX_BOT_TOKEN")
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        API_BASE + path, data=data,
        headers={"Authorization": "OAuth " + config.YANDEX_BOT_TOKEN,
                 "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status, r.read().decode("utf-8", "replace")


def send_text(text):
    """Отправляет текст в настроенный чат. Тихо пропускает, если бот не настроен."""
    if not config.YANDEX_BOT_TOKEN or not config.YANDEX_BOT_CHAT_ID:
        print("Мессенджер не настроен (нет токена/chat_id) — уведомление пропущено.")
        return False
    try:
        status, _ = _post("/messages/sendText/",
                           {"text": text, "chat_id": config.YANDEX_BOT_CHAT_ID})
        print("Мессенджер: отправлено (HTTP %s)" % status)
        return True
    except urllib.error.HTTPError as e:
        print("Мессенджер: ошибка HTTP %s: %s" % (e.code, e.read().decode("utf-8", "replace")))
    except Exception as e:
        print("Мессенджер: ошибка: %s" % e)
    return False


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
    ap = argparse.ArgumentParser(description="Уведомления в Яндекс Мессенджер")
    ap.add_argument("--updates", action="store_true",
                    help="показать getUpdates — чтобы узнать chat_id чата")
    ap.add_argument("--test", metavar="TEXT", help="отправить тестовое сообщение в chat_id")
    args = ap.parse_args()

    if args.updates:
        try:
            status, body = _post("/messages/getUpdates/", {"limit": 100, "offset": 0})
            print("HTTP", status)
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
