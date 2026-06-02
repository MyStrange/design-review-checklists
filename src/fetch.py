"""Забор писем-конспектов с Яндекс-почты по IMAP.

Ищем письма от нужного отправителя за последние N дней, фильтруем по теме и
наличию .txt-вложения, возвращаем только ещё не обработанные (по UID).
Только стандартная библиотека.
"""
import imaplib
import email
import re
from datetime import datetime, timedelta
from email.header import decode_header

from . import config


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


def fetch_new_reviews(processed_uids):
    """processed_uids: set[str]. Возвращает список новых писем-конспектов."""
    M = imaplib.IMAP4_SSL(config.IMAP_HOST, config.IMAP_PORT)
    try:
        M.login(config.YANDEX_USER, config.YANDEX_APP_PASSWORD)
        M.select("INBOX")

        since = (datetime.utcnow() - timedelta(days=config.SEARCH_SINCE_DAYS)).strftime("%d-%b-%Y")
        criteria = '(FROM "%s" SINCE %s)' % (config.REVIEW_SENDER, since)
        typ, data = M.uid("search", None, criteria)
        if typ != "OK" or not data or not data[0]:
            return []

        result = []
        for uid_b in data[0].split():
            uid = uid_b.decode()
            if uid in processed_uids:
                continue
            typ, msgdata = M.uid("fetch", uid_b, "(RFC822)")
            if typ != "OK" or not msgdata or msgdata[0] is None:
                continue
            msg = email.message_from_bytes(msgdata[0][1])
            subject = _decode_header(msg.get("Subject"))
            if config.SUBJECT_MUST_CONTAIN.lower() not in subject.lower():
                continue
            transcript = _extract_txt(msg)
            if not transcript.strip():
                continue
            date_iso, part = parse_subject_meta(subject)
            result.append(
                {
                    "uid": uid,
                    "subject": subject,
                    "date": date_iso,
                    "part": part,
                    "transcript": transcript,
                }
            )
        return result
    finally:
        try:
            M.logout()
        except Exception:
            pass
