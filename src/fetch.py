"""Забор писем-конспектов с Яндекс-почты по IMAP.

Матчим письма по ДОМЕНУ отправителя (telemost.yandex.ru — любой адрес Телемоста),
по фразе в теме и по наличию .txt-вложения. Возвращаем только не обработанные.
Только стандартная библиотека.
"""
import email
import imaplib
import re
from datetime import datetime, timedelta
from email.header import decode_header

from . import config

# Из REVIEW_SENDER берём домен — матчим по нему, а не по точному адресу,
# чтобы не зависеть от точного имени ящика отправителя.
SENDER_DOMAIN = config.REVIEW_SENDER.split("@")[-1] if "@" in config.REVIEW_SENDER else config.REVIEW_SENDER
MAX_SCAN = 500  # сколько последних писем максимум смотрим в запасном режиме


def _decode_header(value):
    if value is None:
        return ""
    out = ""
    for text, enc in decode_header(value):
        if isinstance(text, bytes):
            out += text.decode(enc or "utf-8", errors="replace")
        else:
            out += text
    return out


def parse_subject_meta(subject):
    """Достаёт дату (ISO) и метку части (ч.1/ч.2) из темы письма."""
    date_iso = None
    m = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", subject)
    if m:
        d, mo, y = m.groups()
        date_iso = "%s-%s-%s" % (y, mo, d)
    part = None
    mp = re.search(r"ч\.?\s*(\d+)", subject, re.IGNORECASE)
    if mp:
        part = "ч.%s" % mp.group(1)
    return date_iso, part


def _extract_txt(msg):
    """Возвращает объединённый текст всех .txt-вложений письма (или '')."""
    chunks = []
    for part in msg.walk():
        filename = part.get_filename()
        if not filename:
            continue
        filename = _decode_header(filename)
        if not filename.lower().endswith(".txt"):
            continue
        payload = part.get_payload(decode=True) or b""
        text = None
        for enc in ("utf-8", "cp1251", "utf-16"):
            try:
                text = payload.decode(enc)
                break
            except Exception:
                continue
        if text is None:
            text = payload.decode("utf-8", errors="replace")
        chunks.append(text)
    return "\n\n".join(chunks)


def _search(M, criteria):
    typ, data = M.uid("search", None, criteria)
    if typ != "OK" or not data or not data[0]:
        return []
    return data[0].split()


def _headers(M, uid_b):
    typ, d = M.uid("fetch", uid_b, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT)])")
    if typ != "OK" or not d or d[0] is None:
        return "", ""
    msg = email.message_from_bytes(d[0][1])
    return _decode_header(msg.get("From")), _decode_header(msg.get("Subject"))


def fetch_new_reviews(processed_uids):
    """processed_uids: set[str]. Возвращает список новых писем-конспектов."""
    M = imaplib.IMAP4_SSL(config.IMAP_HOST, config.IMAP_PORT)
    try:
        M.login(config.YANDEX_USER, config.YANDEX_APP_PASSWORD)
        M.select("INBOX")

        since = (datetime.utcnow() - timedelta(days=config.SEARCH_SINCE_DAYS)).strftime("%d-%b-%Y")

        # Основной поиск — по домену отправителя на сервере.
        uids = _search(M, '(FROM "%s" SINCE %s)' % (SENDER_DOMAIN, since))
        mode = "по отправителю (%s)" % SENDER_DOMAIN
        if not uids:
            # Запасной режим: берём все письма за период и фильтруем в Python.
            uids = _search(M, "(SINCE %s)" % since)
            mode = "по дате (запасной режим)"

        uids = list(reversed(uids))[:MAX_SCAN]  # новые сверху, с ограничением
        print("Кандидатов %s: %d" % (mode, len(uids)))

        from_domain = 0
        result = []
        for uid_b in uids:
            uid = uid_b.decode()
            if uid in processed_uids:
                continue
            frm, subj = _headers(M, uid_b)
            if SENDER_DOMAIN.lower() not in frm.lower():
                continue
            from_domain += 1
            if config.SUBJECT_MUST_CONTAIN.lower() not in subj.lower():
                continue
            typ, md = M.uid("fetch", uid_b, "(RFC822)")
            if typ != "OK" or not md or md[0] is None:
                continue
            msg = email.message_from_bytes(md[0][1])
            transcript = _extract_txt(msg)
            if not transcript.strip():
                continue
            date_iso, part = parse_subject_meta(subj)
            result.append({
                "uid": uid,
                "subject": subj,
                "date": date_iso,
                "part": part,
                "transcript": transcript,
            })

        print("Писем от Телемоста: %d, из них новых конспектов с .txt: %d" % (from_domain, len(result)))
        return result
    finally:
        try:
            M.logout()
        except Exception:
            pass
