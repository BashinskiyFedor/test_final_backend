# Обёртка над Keitaro: создатель и редактор кампаний

Бэкенд на FastAPI + PostgreSQL, который ходит в [Keitaro Admin API](doc/openapi.yaml), и React-фронт
(`../test_vacancy_2_front`). Умеет:

1. **Создавать кампанию** по названию, гео-коду страны и офферу Keitaro.
2. **Редактировать офферы потоков** существующей кампании: добавлять, удалять, пинить веса,
   публиковать изменения в Keitaro или откатывать.

## Быстрый старт

Нужны Docker и Node.js 20+.

```bash
# 1. Бэкенд + Postgres
cp .env.example .env          # затем впишите KEITARO_URL и KEITARO_API_KEY
docker compose up --build     # API на http://localhost:8000, Swagger: /docs

# 2. Фронт (в другом терминале)
cd ../front
npm install
npm run dev                   # http://localhost:5173
```

Откройте http://localhost:5173: форма создания кампании, ниже список созданных; у каждой есть
ссылка «Редактировать».

### Настройки (`.env`)

| Переменная | Назначение |
|---|---|
| `KEITARO_URL` | Адрес трекера **без** `/admin_api`, например `https://tracker.example.com` |
| `KEITARO_API_KEY` | API-ключ из настроек Keitaro (уходит в заголовок `Api-Key`) |
| `CORS_ORIGINS` | Адреса фронта через запятую (по умолчанию `http://localhost:5173`) |
| `POSTGRES_*` | Доступы к БД в docker compose |
| `DATABASE_URL` | Только для запуска без Docker (по умолчанию SQLite `app.db`) |

После правки `.env` перезапустите контейнер: `docker compose up -d web`. Зависимости попадают в образ
при сборке, поэтому после изменения `requirements.txt` нужен `docker compose up --build`.

### Запуск без Docker

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
# в .env оставьте DATABASE_URL на SQLite или поднимите Postgres из compose: docker compose up -d db
uvicorn app.main:app --reload
```

### Тесты

```bash
pip install -r requirements-dev.txt
pytest
```

Тесты работают на SQLite в памяти и фейковом Keitaro (`tests/fake_keitaro.py`), доступ к трекеру не нужен.

## Как это устроено

```
app/
  api/            HTTP-слой: роуты, обработчик ошибок (доменная ошибка → статус)
  services/       бизнес-логика
    keitaro.py          клиент Keitaro (типизированные ответы, кэш офферов)
    campaign_service.py создание кампании (идемпотентно)
    stream_sync.py      «Fetch streams»: потоки из Keitaro → наша БД
    stream_editor.py    черновики: add/remove/restore/pin/cancel/push
    weights.py          пересчёт весов
  models/         SQLAlchemy: Campaign, Stream, StreamOffer
  schemas/        Pydantic-схемы API
  core/           настройки, доменные ошибки, KeyedLock
tests/            pytest
```

Слои: роут → сервис → клиент Keitaro / БД. Роуты только вызывают сервисы; ошибки (`NotFoundError`,
`ConflictError`, `InvalidInputError`, `KeitaroError`) превращаются в 404 / 409 / 422 / 502 в одном месте.

## Ключевые моменты

### Создание кампании
- `POST /api/campaigns` `{name, country, offer_id}` делает в Keitaro **кампанию + поток** (flow) с фильтром
  по стране (accept) и оффером на 100%. Одной кампании недостаточно: оффер и гео живут в потоке.
- **Идемпотентность.** Ключ — «название + гео + оффер». Из него строится детерминированный `alias`
  (уникален у нас и в Keitaro). Повторный запрос возвращает существующую кампанию (`200`,
  `already_exists: true`) и ничего не дублирует.
- **Надёжность записи.** Строка в БД резервируется (`pending`) до обращения к Keitaro. Если процесс упал
  после Keitaro, но до записи, повтор находит кампанию по alias и достраивает запись. Если Keitaro вернул
  ошибку, резерв снимается, а свежесозданная кампания без потока удаляется.
- Оффер проверяется по списку Keitaro: неизвестный ID даёт 422.

### Редактор потоков
Данные Keitaro и наши черновики хранятся раздельно (`StreamOffer`: желаемое состояние и состояние Keitaro).
Поток «жёлтый» (`dirty`), если они расходятся.

| Действие | Что происходит |
|---|---|
| Fetch streams | Потоки и офферы подтягиваются из Keitaro; наши черновики не затираются. Потоки без офферов показываются только карточкой. |
| Add offer | Оффер попадает в черновик, веса пересчитываются поровну. В Keitaro ничего не уходит. |
| Remove | Оффер серый, вес 0%. После push исчезает из Keitaro, но остаётся у нас в архиве. |
| Bring back | Возвращает оффер из архива (в черновик). |
| Pin | Вес запинен: остальные делят остаток поровну, сумма всегда 100%. |
| Cancel | Откат к состоянию Keitaro; добавленные черновиком офферы удаляются из нашей базы. |
| Push | `PUT /streams/{id}` с офферами и весами; требует сумму долей ровно 100%. |

Если оффер удалили прямо в Keitaro, при следующем Fetch он не пропадает, а уходит в архив (removed).

### Производительность
Keitaro часто отвечает медленно (1–5 с на запрос), поэтому лишние вызовы убраны:
- список офферов кэшируется на 5 минут; форма при открытии обновляет его (`/api/offers?refresh=true`);
- создание новой кампании делает всего два вызова Keitaro (кампания, поток) без перебора существующих кампаний.

## Ограничения
- Таблицы создаются через `create_all` при старте. Он **не меняет** уже существующие таблицы: после правки
  моделей пересоздайте таблицу вручную (или подключите Alembic).
- Блокировка одновременных запросов с одним alias работает в пределах одного процесса; между процессами
  защищают уникальный alias в БД и в Keitaro.
- При push в Keitaro отправляются только офферы потока; остальные поля потока не меняются.
- Потоки, удалённые в Keitaro, при Fetch удаляются и у нас вместе с архивом офферов.

## API

Swagger UI: http://localhost:8000/docs. Основные эндпоинты:

| Метод и путь | Описание |
|---|---|
| `GET /api/offers?q=&limit=&refresh=` | Офферы Keitaro, поиск по названию или ID |
| `POST /api/campaigns` | Создать кампанию |
| `GET /api/campaigns`, `GET /api/campaigns/{id}` | Созданные кампании |
| `GET /api/campaigns/{id}/streams` | Потоки из нашей БД |
| `POST /api/campaigns/{id}/streams/sync` | Fetch streams |
| `POST /api/streams/{id}/offers` | Добавить оффер `{offer_id}` |
| `DELETE /api/streams/{id}/offers/{pk}` | Remove |
| `POST /api/streams/{id}/offers/{pk}/restore` | Bring back |
| `PATCH /api/streams/{id}/offers/{pk}` | Pin/Unpin `{pinned}` |
| `POST /api/streams/{id}/cancel`, `/push` | Cancel / Push |
