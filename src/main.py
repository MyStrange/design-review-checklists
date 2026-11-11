"""Точка входа: забрать новые письма → разобрать через LLM → пересобрать страницу.

Использование:
  python -m src.main                         # обычный прогон (почта → страница)
  python -m src.main --build-only            # только пересобрать HTML из data
  python -m src.main --file samples/x.txt --date 2026-06-02 --part ч.1
                                             # прогнать локальный .txt без почты (для теста)
"""
import argparse
import hashlib
import json
import sys
from datetime import datetime, timedelta

from . import build, config, fetch, llm, notify

WEEKDAYS = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]


def load_data():
    if config.DATA_FILE.exists():
        return json.loads(config.DATA_FILE.read_text(encoding="utf-8"))
    return {"processed_uids": [], "sessions": []}


def save_data(data):
    config.DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.DATA_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def weekday_label(date_iso):
    try:
        return WEEKDAYS[datetime.strptime(date_iso, "%Y-%m-%d").weekday()]
    except Exception:
        return ""


# Теги правок: к кому идти с пунктом. Совпадают с enum в схеме LLM и со
# стилями .tag на странице — новый тег добавляется сразу в трёх местах.
TAGS = ("ux", "dev", "product", "seo", "legal", "branding")
# «discuss» — старое название продуктового тега, встречается в уже разобранных
# встречах; на странице он и так показывается как «Продакт».
_TAG_ALIASES = {"discuss": "product"}


def _item_id(date_iso, designer, project, idx, text):
    raw = "%s|%s|%s|%s|%s" % (date_iso, designer, project, idx, text)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


# Обезличенные подписи вместо имени: читателю непонятно, кто это, — выбрасываем.
_ROLE_WORDS = {"ведущий", "ведущая", "модератор", "модератора", "участник",
               "участница", "спикер", "докладчик", "не указан", "неизвестно"}


def _fun_author(raw_author):
    """Имя автора номинации или '' — если это роль, пусто или непонятно кто."""
    author = (raw_author or "").strip()
    if not author or author.lower() in _ROLE_WORDS:
        return ""
    return config.short_name(author)[:40]


def _shorten(text, limit):
    """Обрезает по границе слова — чтобы цитата не обрывалась на полуслове."""
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0].rstrip(" ,;:—-")
    return (cut or text[:limit].rstrip()) + "…"


def _clean_fun(raw):
    """Шуточные номинации встречи: оставляем только заполненные и подрезаем длину.
    Имя автора приводим к короткому — чтобы совпадало с остальной страницей."""
    out = {}
    for key in ("weird_word", "catch_phrase", "smart_comment", "filler_word"):
        nom = (raw or {}).get(key) or {}
        if not isinstance(nom, dict):
            continue
        if key == "filler_word":
            items = _clean_filler_items(nom)
            if items:
                out[key] = {"items": items}
            continue
        text = (nom.get("text") or "").strip()
        if not text:
            continue
        # умную мысль не режем совсем: обрезанная цитата бессмысленна,
        # на странице она просто печатается кеглем помельче
        item = {"text": " ".join(text.split()) if key == "smart_comment"
                        else _shorten(text, 120)}
        item["author"] = _fun_author(nom.get("author"))
        if key == "catch_phrase":
            # сколько раз фраза прозвучала за встречу — идёт рядом с автором;
            # счётчик необязателен: без него рубрика просто покажется без числа
            try:
                count = int(nom.get("count") or 0)
            except (TypeError, ValueError):
                count = 0
            if count > 0:
                item["count"] = count
        out[key] = item
    return out


def _clean_filler_items(nom):
    """Топ-5 паразитов: пары слово-число, по убыванию, без пустых и дублей."""
    raw_items = nom.get("items")
    if not isinstance(raw_items, list):
        # запас на старый формат: один паразит в полях text/count
        raw_items = [nom] if (nom.get("text") or "").strip() else []
    items, seen = [], set()
    for it in raw_items:
        if not isinstance(it, dict):
            continue
        text = " ".join((it.get("text") or "").split())[:40]
        if not text or text.lower() in seen:
            continue
        try:
            count = int(it.get("count") or 0)
        except (TypeError, ValueError):
            count = 0
        seen.add(text.lower())
        items.append({"text": text, "count": count} if count > 0 else {"text": text})
    items.sort(key=lambda x: x.get("count", 0), reverse=True)
    return items[:5]


def build_session(item, extracted):
    date_iso = item.get("date") or ""
    designers = []
    for d in extracted.get("designers", []):
        name = (d.get("name") or "Не указан").strip() or "Не указан"
        projects = []
        for p in d.get("projects", []):
            pname = (p.get("name") or "Без названия").strip() or "Без названия"
            items = []
            for idx, raw in enumerate(p.get("items", [])):
                if isinstance(raw, dict):
                    text = (raw.get("text") or "").strip()
                    tag = (raw.get("tag") or "ux").strip().lower()
                else:  # запас на случай старого формата (просто строка)
                    text = (raw or "").strip()
                    tag = "ux"
                if not text:
                    continue
                tag = _TAG_ALIASES.get(tag, tag)
                if tag not in TAGS:
                    tag = "ux"
                items.append({"id": _item_id(date_iso, name, pname, idx, text),
                              "text": text, "tag": tag})
            projects.append({"name": pname, "items": items})
        designers.append({"name": name, "projects": projects})
    return {
        "uid": item["uid"],
        "date": date_iso,
        "weekday": weekday_label(date_iso),
        "part": item.get("part") or "",
        "subject": item.get("subject") or "",
        "designers": designers,
        "fun": _clean_fun(extracted.get("fun")),
    }


def process(item, data):
    extracted = llm.extract_checklist(item["transcript"])
    session = build_session(item, extracted)
    data["sessions"].append(session)
    if item["uid"] not in data["processed_uids"]:
        data["processed_uids"].append(item["uid"])
    n = sum(len(p["items"]) for d in session["designers"] for p in d["projects"])
    print("    дизайнеров: %d, пунктов: %d" % (len(session["designers"]), n))
    return session


def run_refill_fun(force=False):
    """Добирает недостающие рубрики по уже разобранным встречам.

    С force=True рубрики пересобираются заново даже там, где они уже есть —
    нужно, когда поменялись правила: например, умный комментарий теперь
    чистится от слов-паразитов и дописывается до законченной мысли.

    Расшифровки в data не хранятся, поэтому берём письма тех встреч, где рубрик
    меньше четырёх, и спрашиваем модель только про недостающие. Чек-листы,
    отметки и уведомления не трогаем — меняется только блок fun.
    Письма старше SEARCH_SINCE_DAYS в ящике уже не ищутся: такие встречи
    пропускаем с понятным сообщением.
    """
    data = load_data()
    # письма старше SEARCH_SINCE_DAYS в ящике уже не ищутся — такие встречи
    # добрать нечем, в цель не берём
    cutoff = (datetime.utcnow() - timedelta(days=config.SEARCH_SINCE_DAYS)).strftime("%Y-%m-%d")
    targets, too_old = {}, 0
    for s in data["sessions"]:
        if not s.get("uid") or (not force and not llm.missing_fun(s.get("fun"))):
            continue
        if (s.get("date") or "") < cutoff:
            too_old += 1
            continue
        targets[str(s["uid"])] = s
    if too_old:
        print("Встреч старше %d дней без полного блока рубрик: %d — письма не достать, пропускаем"
              % (config.SEARCH_SINCE_DAYS, too_old))
    if not targets:
        print("Добирать нечего: у всех свежих встреч по четыре рубрики.")
        return
    print("Встреч в работе: %d%s" % (len(targets), " (пересобираем все рубрики)" if force else ""))

    # письма целевых встреч снова считаются «новыми», всё остальное пропускаем
    skip = {str(u) for u in data["processed_uids"]} - set(targets)
    by_uid = {str(item["uid"]): item for item in fetch.fetch_new_reviews(skip)}

    changed = 0
    for uid, session in targets.items():
        label = "%s %s" % (session.get("date") or "?", session.get("part") or "")
        item = by_uid.get(uid)
        if not item:
            print("  %s — письма в ящике нет, пропускаем" % label.strip())
            continue
        current = session.get("fun") or {}
        before = len(current)
        # при force спрашиваем все четыре заново, прежние ответы не подставляем
        fun = llm.complete_fun(item["transcript"], {} if force else current)
        if force:
            # модель могла не ответить по части рубрик — старое оставляем как было,
            # иначе один таймаут Gemini стирает уже собранный блок
            merged = dict(current)
            merged.update({k: v for k, v in fun.items()
                           if isinstance(v, dict) and (v.get("text") or "").strip()})
            fun = merged
        session["fun"] = _clean_fun(fun)
        after = len(session["fun"])
        if session["fun"] != current:
            changed += 1
        print("  %s — рубрик было %d, стало %d" % (label.strip(), before, after))

    if not changed:
        print("Ничего добрать не удалось — данные не трогаем.")
        return
    save_data(data)
    build.build_site(data)
    print("Встреч, где рубрик стало больше: %d" % changed)


def run_fetch():
    data = load_data()
    # корона ДО новых встреч — чтобы заметить, если лидер сменится
    before_counts, _ = notify.standings(data["sessions"])
    new_items = fetch.fetch_new_reviews(set(data["processed_uids"]))
    print("Новых писем-конспектов: %d" % len(new_items))
    new_sessions = []
    for item in new_items:
        print("  UID %s — %s" % (item["uid"], item["subject"]))
        new_sessions.append(process(item, data))
    save_data(data)  # сразу фиксируем обработанные письма (чтобы не разобрать повторно)
    build.build_site(data)
    # корона ПОСЛЕ — если сменилась, добавим классную строку в последнее уведомление
    after_counts, genders = notify.standings(data["sessions"])
    crown_note = notify.crown_change_note(before_counts, after_counts, genders)
    late = notify.is_late_now()
    for i, s in enumerate(new_sessions):
        note = crown_note if i == len(new_sessions) - 1 else None
        if late:
            # после 18:00 — не дёргаем вечером, откладываем на 10:00 следующего дня
            notify.enqueue_pending(data, s, note)
            print("    поздно (после 18:00 МСК) — уведомление отложено на завтра 10:00")
        else:
            notify.notify_new_session(s, crown_note=note)
    save_data(data)  # сохраняем после возможной постановки в очередь
    print("Готово.")


def run_send_pending():
    """Утренний прогон: разослать отложенные с вечера уведомления (со звуком и тегами)."""
    data = load_data()
    n = notify.send_pending(data)
    if n:
        save_data(data)
    print("Отправлено отложенных уведомлений: %d" % n)


def run_local(path, date_iso, part):
    data = load_data()
    with open(path, encoding="utf-8") as f:
        transcript = f.read()
    item = {
        "uid": "local:%s:%s" % (date_iso, part or ""),
        "subject": "(локальный файл) Ревью Записи %s от %s" % (part or "", date_iso),
        "date": date_iso,
        "part": part,
        "transcript": transcript,
    }
    print("Прогон локального файла: %s" % path)
    process(item, data)
    save_data(data)
    build.build_site(data)
    print("Готово (локальный файл).")


def main():
    ap = argparse.ArgumentParser(description="Дизайн-ревью → чек-листы")
    ap.add_argument("--file", help="локальный .txt с расшифровкой (для теста)")
    ap.add_argument("--date", help="дата ревью YYYY-MM-DD (для --file)")
    ap.add_argument("--part", default="", help="метка части, напр. ч.1 (для --file)")
    ap.add_argument("--build-only", action="store_true", help="только пересобрать HTML")
    ap.add_argument("--send-pending", action="store_true",
                    help="разослать отложенные на утро уведомления")
    ap.add_argument("--refill-fun", action="store_true",
                    help="добрать недостающие рубрики по уже разобранным встречам")
    ap.add_argument("--force", action="store_true",
                    help="с --refill-fun: пересобрать рубрики заново, даже если они есть")
    args = ap.parse_args()

    if args.build_only:
        build.build_site(load_data())
        print("Страница пересобрана.")
        return
    if args.send_pending:
        run_send_pending()
        return
    if args.refill_fun:
        run_refill_fun(force=args.force)
        return
    if args.file:
        if not args.date:
            print("Для --file нужен --date YYYY-MM-DD", file=sys.stderr)
            sys.exit(1)
        run_local(args.file, args.date, args.part)
        return
    run_fetch()


if __name__ == "__main__":
    main()
