# sputnic-llc — файлообменник (Fullstack)

MVP файлообменника: загрузка файлов, асинхронная проверка на подозрительный
контент (Celery/Redis) и лента алертов. Бэкенд — FastAPI + SQLAlchemy
(asyncpg/psycopg) + PostgreSQL + Alembic; фронтенд — Next.js (App Router) +
react-bootstrap.

---

## Запуск (dev)

```bash
docker compose -f docker-compose.dev.yml up --build
docker exec -it backend alembic upgrade head
```

- Фронтенд: http://localhost:3000/test
- Бэкенд API / Swagger: http://localhost:8000/docs
- PostgreSQL с хоста: `localhost:5433` (`postgres` / `postgres`, база `test`)
- При первом запуске Postgres инициализируется сам (healthcheck'и настроены).

### Тесты

Бэкенд (не требует внешних сервисов — SQLite in-memory):

```bash
docker compose -f docker-compose.dev.yml run --rm backend python -m pytest
```

Фронтенд (Vitest + Testing Library):

```bash
cd frontend
npm ci
npm test
```

---

## Что было сделано

### 1. Рефакторинг бэкенда (слои вместо «сервиса-швейцарского ножа»)

Было: один модуль `service.py` смешивал конфигурацию (чтение `os.environ` на
импорте, `mkdir`), движок БД, файловые операции, сессии, HTTP-исключения и
зависел от FastAPI (`UploadFile`, `HTTPException`); `tasks.py` создавал второй
движок и импортировал FastAPI-модуль в Celery.

Стало:

```
backend/src/
├── config.py      # Settings (pydantic-settings), сборка DSN
├── db.py          # фабрики async/sync engine + session
├── errors.py      # доменные ошибки (без HTTP)
├── models.py      # ORM (StoredFile, Alert; FK с ON DELETE CASCADE)
├── schemas.py     # Pydantic DTO + валидация
├── storage.py     # потоковая запись с лимитом, атомарный commit
├── scanner.py     # чистые правила скана + потоковые счётчики метаданных
├── services.py    # прикладной слой (use-cases файлов и алертов)
├── main.py        # фабрика FastAPI-приложения (DI через app.state)
├── api/           # роуты и зависимости (тонкий слой)
└── worker/        # Celery + sync-пайплайн (scan -> metadata -> alert)
```

Публичный API-контракт не изменился (пути, методы, поля, статусы).

### 2. Исправленные баги

| Баг | Было | Стало |
| --- | ---- | ----- |
| Несовпадение порта Postgres | бэкенд ходил на `backend-db:5433`, а Postgres слушает 5432 → `alembic`/запросы падали | порт внутри сети 5432; наружу `5433:5432`; healthcheck'и |
| DELETE файла с алертами | физический файл удалялся до удаления строки, FK-нарушение → HTTP 500 + «сирота» | `ON DELETE CASCADE` + удаление строки первым → 204 |
| Чтение файла целиком в память | `upload.read()` и повторное `read_text`/`read_bytes` в метаданных, без лимитов | потоковая запись с лимитом (413), потоковые счётчики |
| Зависание статуса `processing` | исключение в задаче оставляло файл в `processing` навсегда | `failed` + critical-алерт |
| Падение `.delay()` | Redis недоступен → 500, хотя файл уже создан | `enqueue_scan` запускает inline-обработку в фоне |
| Доверие MIME клиенту | `.pdf` с подделанным `Content-Type` проходил проверку | проверка magic-байтов (`%PDF`) |
| `title` > 255 символов | DB-ошибка → 500 | Pydantic-валидация → 422 |
| `Dockerfile` фронтенда | `COPY .env.production` несуществующего файла → сборка падала | убран |
| Redis/Layout: `depends_on` без healthcheck, `favicon`/хардкод URL | гонки при старте, битые ссылки | исправлено в compose/фронте |

### 3. «Неочевидная» оптимизация

- **Потоковая обработка с ограниченной памятью**: файл больше не читается
  целиком ни при загрузке (чанки 1 МБ + атомарный `os.replace`), ни при
  извлечении метаданных (счётчики строк/символов и `approx_page_count` по
  чанкам). Для PDF учтён «подводный камень» — токен `/Type /Page`, пересекающий
  границу чанка, считается корректно (перенос хвоста).
- **Один конфиг и отсутствие дублей движков**: убран event-loop хак в Celery;
  у воркера один ленивый sync-движок (psycopg), у API — async (asyncpg).

### 4. Фронтенд разбит на слои

```
frontend/src/
├── types/          # модели FileItem / AlertItem
├── lib/            # apiClient (единый base URL из NEXT_PUBLIC_API_URL), форматтеры
├── api/            # files.ts / alerts.ts
├── hooks/          # useDashboardData, useUploadFile
├── components/     # PageHeader, FilesTable, AlertsTable, UploadFileModal, StatusBadge
└── app/            # только композиция
```

---

## Тесты

- `backend/tests/` — 41 тест (pytest, asyncio, in-memory SQLite):
  API-контракт (включая регрессии на исправленные баги), сканер, хранилище,
  фазы воркера.
- `frontend/src/**/*.test.*` — 20 тестов (Vitest + Testing Library):
  форматтеры, API-клиент, хуки, компоненты.

## Стек

Python 3.14, FastAPI, SQLAlchemy 2, PostgreSQL 16, Redis 7, Celery, Alembic,
uv; Node 20, Next.js 15, React 18, react-bootstrap, Vitest.

