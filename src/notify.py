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
import random
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


# ---------- Журнал отправленных сообщений (чтобы потом их редактировать) ----------
SENT_FILE = config.ROOT / "data" / "sent_messages.json"


def _load_sent():
    try:
        return json.loads(SENT_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def _record_sent(chat_id, message_id, kind, text):
    """Запоминаем message_id отправленного боту сообщения — для будущего редактирования."""
    items = _load_sent()
    items.append({
        "chat_id": chat_id,
        "message_id": message_id,
        "kind": kind,
        "ts": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "preview": (text or "").strip().replace("\n", " ")[:80],
    })
    SENT_FILE.parent.mkdir(parents=True, exist_ok=True)
    SENT_FILE.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def last_sent(kind=None):
    """Последнее отправленное сообщение (опционально нужного типа) из журнала."""
    items = _load_sent()
    if kind:
        items = [m for m in items if m.get("kind") == kind] or items
    return items[-1] if items else None


# ---------- Telegram ----------
def _tg_url(method):
    return "https://api.telegram.org/bot%s/%s" % (config.TELEGRAM_BOT_TOKEN, method)


def _tg_send(text, parse_mode=None, silent=False, kind="message"):
    """Отправляет сообщение. Возвращает message_id (int) или None.
    silent=True — без звука/пуша. Каждый успешный отправленный id пишем в журнал."""
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        print("Telegram не настроен (нет токена/chat_id) — уведомление пропущено.")
        return None
    payload = {"chat_id": config.TELEGRAM_CHAT_ID, "text": text,
               "disable_web_page_preview": True}
    if parse_mode:
        payload["parse_mode"] = parse_mode
    if silent:
        payload["disable_notification"] = True
    try:
        status, body = _http(_tg_url("sendMessage"), payload, {"Content-Type": "application/json"})
        mid = None
        try:
            mid = json.loads(body).get("result", {}).get("message_id")
        except Exception:
            pass
        print("Telegram: отправлено (HTTP %s), message_id=%s" % (status, mid))
        if mid is not None:
            _record_sent(config.TELEGRAM_CHAT_ID, mid, kind, text)
        return mid
    except urllib.error.HTTPError as e:
        print("Telegram: ошибка HTTP %s: %s" % (e.code, e.read().decode("utf-8", "replace")))
    except Exception as e:
        print("Telegram: ошибка: %s" % e)
    return None


def _tg_updates():
    return _http(_tg_url("getUpdates"),
                 {"allowed_updates": ["message", "my_chat_member", "chat_member", "channel_post"],
                  "limit": 100},
                 {"Content-Type": "application/json"})


def _tg_extract_chats(body):
    """Вытаскивает chat_id и название чата из ответа Telegram getUpdates."""
    try:
        d = json.loads(body)
    except Exception:
        return []
    chats = {}
    for u in d.get("result", []):
        for key in ("message", "edited_message", "channel_post",
                    "my_chat_member", "chat_member", "chat_join_request"):
            obj = u.get(key)
            if isinstance(obj, dict):
                ch = obj.get("chat")
                if isinstance(ch, dict) and ch.get("id") is not None:
                    chats[ch["id"]] = ch.get("title") or ch.get("username") or ch.get("type") or ""
    return list(chats.items())


def _tg_get_me():
    """id самого бота — чтобы точно опознать его собственные сообщения."""
    try:
        _, body = _http(_tg_url("getMe"), None, {"Content-Type": "application/json"})
        return json.loads(body).get("result", {}).get("id")
    except Exception:
        return None


def _find_edit_target(updates_body, bot_id):
    """В ответах getUpdates ищем reply на сообщение-чеклист самого бота.
    Возвращает (chat_id, message_id) исходного поста бота или None.
    Берём самый свежий подходящий reply."""
    try:
        d = json.loads(updates_body)
    except Exception:
        return None
    target = None
    for u in d.get("result", []):
        msg = u.get("message") or u.get("edited_message") or {}
        rep = msg.get("reply_to_message")
        if not isinstance(rep, dict):
            continue
        frm = rep.get("from") or {}
        text = rep.get("text") or rep.get("caption") or ""
        is_bot = frm.get("is_bot") and (bot_id is None or frm.get("id") == bot_id)
        if is_bot or ("Чек-лист" in text):
            chat = rep.get("chat") or msg.get("chat") or {}
            if chat.get("id") is not None and rep.get("message_id") is not None:
                target = (chat["id"], rep["message_id"])  # перезаписываем — нужен последний
    return target


def _tg_edit(chat_id, message_id, text):
    payload = {"chat_id": chat_id, "message_id": message_id, "text": text,
               "disable_web_page_preview": True}
    try:
        status, body = _http(_tg_url("editMessageText"), payload,
                             {"Content-Type": "application/json"})
        print("Telegram editMessageText: HTTP %s" % status)
        return True
    except urllib.error.HTTPError as e:
        print("Telegram edit: ошибка HTTP %s: %s" % (e.code, e.read().decode("utf-8", "replace")))
    except Exception as e:
        print("Telegram edit: ошибка: %s" % e)
    return False


def edit_last_checklist(new_text):
    """Редактирует прошлое сообщение-чеклист бота. Чтобы найти его номер, нужно,
    чтобы кто-то ответил (reply) на тот пост в группе — этот reply виден боту."""
    bot_id = _tg_get_me()
    try:
        _, body = _tg_updates()
    except urllib.error.HTTPError as e:
        print("getUpdates HTTP %s: %s" % (e.code, e.read().decode("utf-8", "replace")))
        return False
    target = _find_edit_target(body, bot_id)
    if not target:
        print("Не нашёл reply на сообщение бота. Нужно ответить «.» на тот пост в группе и повторить.")
        return False
    cid, mid = target
    print("Цель найдена: chat_id=%s, message_id=%s" % (cid, mid))
    return _tg_edit(cid, mid, new_text)


def edit_stored(new_text, kind=None):
    """Редактирует последнее сообщение бота по СОХРАНЁННОМУ id из журнала —
    ничего отвечать в чате не нужно. Если в журнале пусто (старые сообщения,
    отправленные до появления журнала) — откатываемся на поиск по reply."""
    rec = last_sent(kind)
    if rec and rec.get("message_id") is not None:
        print("Редактирую по журналу: message_id=%s (%s)" % (rec["message_id"], rec.get("preview", "")))
        return _tg_edit(rec["chat_id"], rec["message_id"], new_text)
    print("В журнале нет сохранённых сообщений — пробую найти по ответу в чате.")
    return edit_last_checklist(new_text)


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


def send_text(text, parse_mode=None, silent=False, kind="message"):
    if _provider() == "yandex":
        return _ya_send(text)
    return _tg_send(text, parse_mode, silent=silent, kind=kind)


def _fmt_date(iso):
    try:
        dt = datetime.strptime(iso, "%Y-%m-%d")
        return "%d %s" % (dt.day, RU_MONTHS[dt.month - 1])
    except Exception:
        return iso or ""


# Фановые вступительные фразы — выбирается случайная при каждом уведомлении.
PHRASES = [
    "Хола, бандитос, подъехал чеклист! 🌮",
    "Котаны мяукают, но по списку делают 🐈",
    "Чайки наорали на чеклист, разбираем 🐦",
    "Свежие правки с пылу с жару 🔥",
    "Тук-тук, это ваши правочки 🚪",
    "Чеклист подвезли, встречайте 🚚",
    "Дизайнеры, по коням — правки ждут 🐎",
    "Дзынь-дзынь! Новый чеклист на проводе 🔔",
    "Так-так-так, что тут у нас за правки 🔍",
    "Пора кормить чеклист галочками ✅",
    "Новая пачка правок, налетай 🍪",
    "Лови апдейт: ревью разобрано ✨",
    "Готово! Список задач развёрнут 📜",
    "Правки приехали, разбираем по-братски 🤝",
    "Включаем режим «делаю по списку» 🤖",
    "Капитан Чеклист на связи, задачи внутри ⚓",
    "Утренний кофе и свежие правки ☕",
    "Прилетел свежачок — ваши правки 🛬",
    "Эй, креативные, разбираем правки 🎨",
    "Чеклист готов, а вы готовы? 💪",
    "Пссст… тут свежие правки завезли 🤫",
    "Внимание-внимание, говорит чеклист 📢",
    "Ну что, погнали по галочкам 🏁",
    "Свежеиспечённый список задач 🥐",
    "Барабанная дробь… ваши правки! 🥁",
    "Дизайн-ревью разобрано, налетай 🦅",
    "Чеклист вылупился 🐣",
    "Хьюстон, у нас новые правки 🚀",
    "Расчехляем фигму, правки прибыли 🛠",
    "Тадам! Список того, что подкрутить ✨",
    "Падаван, твои правки готовы 🧙",
    "Кто молодец? Чеклист молодец 🏆",
    "Кофеёк, плед, чеклист ☕",
    "Правки собраны, можно шуршать 🐹",
    "Свежий улов правок 🎣",
    "Дизайнеры на низком старте 🏃",
    "Ловите дозу полезных правок 💊",
    "Опять работать… но по красоте 💅",
    "Кушать поДано… то есть правки 🍽",
    "Дзынь! Прилетела пачка задач 📦",
    "Чеклист дозрел, можно собирать 🍅",
    "Тыдыщ! Ревью превратилось в список 💥",
    "Мур-мур, правки на месте 🐾",
    "Свистать всех наверх — правки 🛟",
    "Готовьте курсоры, правки пошли 🖱",
]


def _mentions(session):
    """@username тех дизайнеров, кто был на этом ревью (по карте логинов)."""
    out, seen = [], set()
    for d in session.get("designers", []):
        short = config.short_name(d.get("name", ""))
        uname = config.TELEGRAM_USERNAMES.get(short)
        if uname and uname not in seen:
            seen.add(uname)
            out.append(uname)
    return out


def notify_new_session(session):
    """Шлёт уведомление об одном новом разобранном ревью."""
    designers = session.get("designers", [])
    n_items = sum(len(p.get("items", [])) for d in designers for p in d.get("projects", []))
    head = "📋 Чек-лист ревью — %s" % _fmt_date(session.get("date", ""))
    extra = " · ".join([x for x in (session.get("part", ""), session.get("weekday", "")) if x])
    if extra:
        head += " (%s)" % extra
    lines = [random.choice(PHRASES), "", head,
             "Дизайнеров: %d · правок: %d" % (len(designers), n_items)]
    # Ссылка на актуальный сайт — обязательна в КАЖДОМ сообщении.
    # config.SITE_URL гарантированно непустой (есть значение по умолчанию).
    lines.append(config.SITE_URL or "https://design-review-checklists-git-main-shsbs.vercel.app")
    mentions = _mentions(session)
    if mentions:
        lines += ["", " ".join(mentions)]
    # kind="checklist" — чтобы потом можно было найти и отредактировать этот пост по id
    send_text("\n".join(lines), kind="checklist")


def _cli():
    ap = argparse.ArgumentParser(description="Уведомления о новом чек-листе")
    ap.add_argument("--updates", action="store_true", help="показать getUpdates (узнать chat_id)")
    ap.add_argument("--test", metavar="TEXT", help="отправить тестовое сообщение")
    ap.add_argument("--announce", action="store_true", help="отправить анонс с HTML-ссылкой")
    ap.add_argument("--edit-last", action="store_true",
                    help="отредактировать прошлый пост по сохранённому id (текст из trigger/edit-last.txt)")
    ap.add_argument("--send-silent", action="store_true",
                    help="отправить текст из trigger/send.txt без звука (disable_notification)")
    args = ap.parse_args()

    if args.edit_last:
        new_text = (config.ROOT / "trigger" / "edit-last.txt").read_text(encoding="utf-8").strip("\n")
        edit_stored(new_text, kind="checklist")
        return

    if args.send_silent:
        text = (config.ROOT / "trigger" / "send.txt").read_text(encoding="utf-8").strip("\n")
        send_text(text, silent=True, kind="manual")
        return

    if args.updates:
        try:
            status, body = _ya_updates() if _provider() == "yandex" else _tg_updates()
            print("provider:", _provider(), "| HTTP", status)
            try:
                print(json.dumps(json.loads(body), ensure_ascii=False, indent=2))
            except Exception:
                print(body)
            if _provider() != "yandex":
                print("\n=== НАЙДЕННЫЕ CHAT_ID ===")
                found = _tg_extract_chats(body)
                if found:
                    for cid, title in found:
                        print("  chat_id: %s  |  %s" % (cid, title))
                else:
                    print("  (пусто — напиши в группе сообщение со слэшем, напр. /id, и повтори)")
        except urllib.error.HTTPError as e:
            print("Ошибка HTTP %s: %s" % (e.code, e.read().decode("utf-8", "replace")))
        return
    if args.test is not None:
        send_text(args.test)
        return
    if args.announce:
        msg = ('йесссссс, <a href="%s">го чекать</a>, кто несёт корону по количеству встреч 👑\n'
               'буду присылать вам чеклисты дважды в неделю') % config.SITE_URL
        send_text(msg, parse_mode="HTML")
        return
    ap.print_help()


if __name__ == "__main__":
    _cli()
