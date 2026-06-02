# Чек-листы дизайн-ревью

Автоматически забирает с Яндекс-почты конспекты встреч дизайн-ревью,
превращает их в чек-листы (через бесплатный LLM API) и публикует на
веб-страницу с навигацией **Дизайнер → Дата → Проект → пункты с галочками**.

Работает сам, бесплатно и **не зависит от чьей-либо подписки** на ChatGPT/Claude:
движок — GitHub Actions, модель — бесплатный Gemini API (один проектный ключ).

## Как это устроено

```
Яндекс-почта (IMAP)
   │  по вт/чт, днём–вечером, раз в час
   ▼
GitHub Actions  ──►  src/main.py
   ├─ fetch.py   найти письмо от keeper@telemost.yandex.ru с темой «Ревью Записи», скачать .txt
   ├─ llm.py     текст расшифровки → структурированный чек-лист (Gemini, бесплатно)
   ├─ build.py   data/checklists.json → docs/index.html
   └─ git commit + push
   ▼
Хостинг (GitHub Pages / Cloudflare Pages) отдаёт docs/index.html
```

- Письмо распознаётся по отправителю **и** теме; дата берётся из темы (`от 02.06.2026`).
- `ч.1` = ревью по вторникам, `ч.2` = по четвергам — это **разные встречи**, не склеиваются.
- Обработанные письма запоминаются по UID в `data/checklists.json` — повторно не обрабатываются.
- Галочки в пунктах хранятся в браузере пользователя (localStorage), у каждого свои.

## Структура

```
src/config.py   настройки (всё из переменных окружения)
src/fetch.py    забор писем по IMAP
src/llm.py      обращение к LLM (Gemini; легко заменить провайдера)
src/build.py    генерация HTML
src/main.py     оркестрация + CLI
data/checklists.json   накопленные данные + список обработанных писем
docs/           готовая страница (index.html) — отсюда раздаётся хостинг
.github/workflows/sync.yml   расписание и автозапуск
samples/        пример расшифровки для локального теста
```

## Секреты (GitHub → Settings → Secrets and variables → Actions)

| Имя | Что это |
|---|---|
| `YANDEX_USER` | полный адрес ящика, напр. `name@company.ru` |
| `YANDEX_APP_PASSWORD` | пароль приложения Яндекса (не основной пароль!) |
| `GEMINI_API_KEY` | бесплатный ключ Google AI Studio |

Необязательные переменные (можно не задавать): `GEMINI_MODEL`, `LLM_PROVIDER`,
`REVIEW_SENDER`, `SUBJECT_MUST_CONTAIN`, `SEARCH_SINCE_DAYS`, `SITE_TITLE`.

## Локальный запуск / тест

Зависимостей ставить не нужно — только Python 3.

```bash
# 1) Только пересобрать страницу из текущих данных (без почты и без ключа):
python -m src.main --build-only
#    → откроется docs/index.html

# 2) Прогнать пример расшифровки через LLM (нужен GEMINI_API_KEY):
export GEMINI_API_KEY=...        # ключ из Google AI Studio
python -m src.main --file samples/sample_transcript.txt --date 2026-06-02 --part ч.1

# 3) Полный прогон (почта → страница), нужны все три секрета:
export YANDEX_USER=name@company.ru
export YANDEX_APP_PASSWORD=...
export GEMINI_API_KEY=...
python -m src.main
```

## Хостинг страницы (решим на этапе деплоя)

`docs/index.html` — обычная статика, её можно отдавать откуда угодно:

- **GitHub Pages** (Settings → Pages → Deploy from branch → `main` / `docs`).
  Самый простой вариант. Нюанс: Pages из **приватного** репозитория доступны
  не на всех тарифах GitHub — если репозиторий приватный и Pages недоступны,
  используем вариант ниже.
- **Cloudflare Pages** — бесплатно, работает с приватным репозиторием,
  output-каталог `docs`. Подходит, если нужен приватный репозиторий + страница
  «по ссылке».

В обоих случаях страница отдаётся с `noindex` и `robots.txt`, поэтому в поиск
не попадает.
