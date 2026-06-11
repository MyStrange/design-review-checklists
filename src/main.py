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
from datetime import datetime

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


def _item_id(date_iso, designer, project, idx, text):
    raw = "%s|%s|%s|%s|%s" % (date_iso, designer, project, idx, text)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


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
                if tag not in ("ux", "dev", "discuss"):
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
    save_data(data)
    build.build_site(data)
    # корона ПОСЛЕ — если сменилась, добавим классную строку в последнее уведомление
    after_counts, genders = notify.standings(data["sessions"])
    crown_note = notify.crown_change_note(before_counts, after_counts, genders)
    for i, s in enumerate(new_sessions):
        note = crown_note if i == len(new_sessions) - 1 else None
        notify.notify_new_session(s, crown_note=note)
    print("Готово.")


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
    args = ap.parse_args()

    if args.build_only:
        build.build_site(load_data())
        print("Страница пересобрана.")
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
