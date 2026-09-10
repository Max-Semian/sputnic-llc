# METHODOLOGY.md — методология разработки и реестр требований

Документ описывает **как развивать проект дальше**: архитектурные правила,
конвенции, процесс изменений, Definition of Done и реестр проверяемых
требований с идентификаторами. Требования пронумерованы (ARCH/BE/FE/DATA/API/
TEST/INFRA/SEC/GIT/DOC) со словами **MUST / SHOULD / MUST NOT** — на них можно
ссылаться в задачах и в инструкциях для LLM (шаблон — в разделе 12).

---

## 0. Как пользоваться документом

- **Человек**: перед началом задачи прочитать разделы 1–3 и реестр (раздел 13);
  в PR ссылаться на ID требований («закрывает API-2, TEST-3»).
- **LLM**: в промпт вставлять раздел 12 целиком + перечень затрагиваемых ID;
  после генерации — прогнать Quality Gates (раздел 11).
- Изменение требований — только правкой этого файла отдельным коммитом
  (`docs: ...`), не «по ходу» фичи.

---

## 1. Контекст проекта

Файлообменник: загрузка файлов → асинхронная проверка на подозрительный
контент → лента алертов. Текущее состояние: рабочий MVP, покрыт тестами
(44 backend, 20 frontend), разложен по слоям.

| Слой | Технологии |
|---|---|
| Backend | Python 3.14, FastAPI, SQLAlchemy 2 (async), Pydantic v2 |
| Очередь | Celery + Redis 7 |
| БД / миграции | PostgreSQL 16, Alembic |
| Хранилище | локальный диск (`backend/storage/files`), потоковая запись |
| Frontend | Next.js 15 (App Router), React 18, react-bootstrap, TypeScript |
| Тесты | pytest + pytest-asyncio + httpx + aiosqlite; Vitest + Testing Library |

### 1.1. Слои backend (MUST соблюдать)

```
backend/src/
  core/            # Settings, доменные ошибки, enum-ы. Ничего не импортирует из проекта.
  domain/          # ORM-сущности, чистые бизнес-правила (scanning).
  application/     # ports.py (Protocol) + services/ (классы use-case).
  infrastructure/  # db.py, repositories.py (+ UnitOfWork), storage.py, celery_app.py.
  presentation/    # app.py, deps.py, schemas.py, routes.py.
  worker/          # tasks.py — тонкие Celery-обёртки.
```

Направление зависимостей (MUST):

```
presentation ──► application ──► domain ◄── infrastructure
      │                 ▲                        │
      └─────────► core ◄┴────────────────────────┘
```

- ARCH-1 (MUST): `domain` не импортирует FastAPI/SQLAlchemy-сессии/Celery.
- ARCH-2 (MUST): `application` зависит только от `domain` и `ports.py`
  (Protocol), но не от конкретных репозиториев/storage.
- ARCH-3 (MUST): весь SQLAlchemy-доступ — только в `infrastructure/repositories.py`.
- ARCH-4 (MUST): HTTP-детали (`HTTPException`, `UploadFile`, `FileResponse`)
  не покидают `presentation`.
- ARCH-5 (MUST): новые «порты» описываются `Protocol` в `application/ports.py`,
  реализации кладутся в `infrastructure`.
- ARCH-6 (MUST): воркер переиспользует application-сервисы; новые фоновые
  операции добавляются как задачи-обёртки, а не как отдельная бизнес-логика.

---

## 2. Backend-конвенции

- BE-1 (MUST): Python 3.14, полные type hints; `from __future__ import` не нужен.
- BE-2 (MUST): строковые статусы/уровни — только через enum из `core/enums.py`
  (`ProcessingStatus`, `ScanStatus`, `AlertLevel`), не «магические строки».
- BE-3 (MUST): ошибки домена — подклассы `core.errors.AppError` с `status_code` и
  `detail`; HTTP-код назначается только в presentation-слое.
- BE-4 (MUST): конфигурация — только через `core.config.Settings`
  (env/pydantic-settings). Чтение `os.environ` вне `config.py` запрещено (MUST NOT).
- BE-5 (MUST): сервисы — классы с внедрением зависимостей через конструктор
  (`__init__(self, uow_factory, storage)`), без глобального состояния.
- BE-6 (MUST): доступ к БД — только через UnitOfWork и репозитории
  (`async with self._uow_factory() as uow: ... await uow.commit()`).
- BE-7 (SHOULD): бизнес-правило без ввода-вывода — чистая функция в `domain/`
  (как `scanning.evaluate_threats`) и покрыто юнит-тестом.
- BE-8 (MUST): логирование — модульный `logging.getLogger(__name__)`; секреты и
  содержимое файлов в логи не пишутся.
- BE-9 (MUST): публичные модули/классы/функции имеют краткие docstring.
- BE-10 (SHOULD): размер файла ≤ ~150 строк; если больше — делить по смыслу.

---

## 3. Frontend-конвенции

```
frontend/src/
  types/        # типы домена (зеркало DTO бэкенда)
  lib/          # apiClient (единый base URL), форматтеры
  api/          # функции запросов (files.ts, alerts.ts)
  hooks/        # состояние и side-effects (useDashboardData, useUploadFile)
  components/   # презентационные компоненты
  app/          # только композиция страниц (Server Components + client-острова)
```

- FE-1 (MUST): страницы в `app/` не содержат fetch/бизнес-логики — только композиция.
- FE-2 (MUST): все запросы идут через `lib/apiClient.ts`; URL API — только из
  `NEXT_PUBLIC_API_URL` (fallback `http://localhost:8000`). Хардкод URL запрещён (MUST NOT).
- FE-3 (MUST): типы ответов — из `types/` (синхронизируются с `presentation/schemas.py`).
- FE-4 (MUST): состояние/загрузка/ошибки — в хуках, а не в компонентах.
- FE-5 (SHOULD): компоненты без побочных эффектов; `"use client"` только там,
  где реально нужны хуки/DOM.
- FE-6 (MUST): каждый новый хук/утилита/компонент — с тестом (Vitest).
- FE-7 (SHOULD): серверная логика (metadata, layout) остаётся в Server Components.

---

## 4. Данные, хранилище, миграции

- DATA-1 (MUST): файлы пишутся потоково чанками (`Settings.chunk_size`, 1 МБ) через
  `FileStorage.write_temp` + `commit` (атомарный `os.replace`). Чтение файла целиком
  в память запрещено (MUST NOT).
- DATA-2 (MUST): лимит размера (`Settings.max_upload_size`, 512 МБ) проверяется
  **во время** чтения; превышение → `FileTooLargeError` (HTTP 413), пустой файл →
  `EmptyFileError` (HTTP 400); временные файлы при ошибке удаляются.
- DATA-3 (MUST): инвариант «нет строки в БД → нет файла». Порядок: записать файл →
  INSERT; при ошибке БД файл удалить. Удаление: сначала строка (алерты каскадом),
  потом файл.
- DATA-4 (MUST): имена на диске генерирует сервер (`uuid` + расширение);
  пользовательское имя хранится только в `original_name`.
- DATA-5 (MUST): миграции — только новые ревизии (`alembic revision`), правка
  применённых запрещена (MUST NOT); у каждой ревизии есть рабочий `downgrade`.
- DATA-6 (MUST): `models`/`entities` — источник правды схемы; любое изменение —
  модель + миграция в одном коммите.
- DATA-7 (SHOULD): метаданные файла считаются потоково (счётчики), без загрузки
  содержимого; для токенов — учёт границы чанка (carry).
- DATA-8 (SHOULD): тяжёлые списки — пагинация + индексы (`created_at`, `file_id`)
  при появлении нагрузки.

## 5. API-контракт

Действующие эндпоинты (менять без согласования нельзя):

| Метод | Путь | Код | Назначение |
|---|---|---|---|
| GET | `/files` | 200 | список файлов (новые сверху) |
| POST | `/files` | 201 | multipart `title` + файл |
| GET | `/files/{id}` | 200/404 | карточка файла |
| PATCH | `/files/{id}` | 200/404/422 | переименование |
| DELETE | `/files/{id}` | 204/404 | удаление (+каскад алертов) |
| GET | `/files/{id}/download` | 200/404 | скачивание |
| GET | `/alerts` | 200 | лента алертов |

- API-1 (MUST): ответы описываются схемами из `presentation/schemas.py`; ORM-сущности
  не сериализуются в API напрямую.
- API-2 (MUST): маппинг ошибок домена в HTTP — единственной точкой
  (exception handler) в `presentation/app.py`; новые ошибки — подкласс `AppError`.
- API-3 (MUST): изменения публичного контракта (путь/метод/код/поля) фиксируются
  тестом и отмечаются в README; ломающие изменения — только при явном запросе.
- API-4 (SHOULD): валидация входа — схемой/DTO (например, `title` 1..255 → 422),
  а не проверкой «руками» в роуте.
- API-5 (MUST): фоновые задачи запускаются через `enqueue_scan` (с fallback),
  а не прямым `.delay()` из роута.

## 6. Тестирование

Пирамида: юнит (domain/сервисы/репозитории) → API-контракт → e2e-смоук.

- TEST-1 (MUST): багфикс начинается с **падающего теста**, воспроизводящего баг,
  и заканчивается зелёным; тест остаётся как регрессия.
- TEST-2 (MUST): backend-тесты не требуют внешних сервисов: SQLite in-memory
  (`StaticPool`, `PRAGMA foreign_keys=ON`) и `tmp_path` для storage.
- TEST-3 (MUST): новый эндпоинт → тесты кодов (201/400/404/413/422) и побочных
  эффектов (запись в БД/storage, постановка задачи).
- TEST-4 (MUST): новое бизнес-правило → юнит-тест чистой функции + тест фазы
  пайплайна (scan/metadata/alert) на ожидаемый статус и уровень алерта.
- TEST-5 (MUST): новые репозитории/UoW → тесты CRUD, сортировки и каскадов.
- TEST-6 (MUST): фронтенд — тесты форматтеров, apiClient (mock fetch, ошибки),
  хуков (`renderHook`), компонентов (пусто/загрузка/данные/ошибка).
- TEST-7 (SHOULD): e2e-смоук после крупных изменений: `docker compose up`,
  upload → processed/clean + alert, подозрительный файл → warning, DELETE → 204.
- TEST-8 (MUST): тесты детерминированы: без sleep/сетевых вызовов; время файлов и
  id задаются явно там, где важен порядок.

---

## 7. Процесс изменений

### 7.1. Багфикс (workflow)

1. Воспроизвести (curl/тест/логи) и зафиксировать факт и причину.
2. Написать **падающий** регрессионный тест (TEST-1).
3. Исправить минимально; не «причёсывать» соседний код.
4. Прогнать Quality Gates (раздел 11).
5. В описании коммита — «было → стало» и ID требования.

### 7.2. Новая фича

1. Уточнить контракт (API-3) и затрагиваемые требования.
2. Domain (правило/сущность) → application (сервис/порт) → infrastructure
   (реализация порта/репозиторий) → presentation (роут/DTO) → frontend (api →
   hook → component). Строго в этом порядке (ARCH-1..6).
3. Тесты на каждом уровне (TEST-3..6).
4. Обновить README (структура/эндпоинты) и, при необходимости, METHODOLOGY.

### 7.3. Изменение схемы БД

1. `domain/entities.py` — правка модели.
2. `alembic revision -m "..."` → заполнить `upgrade`/`downgrade` (DATA-5).
3. Проверить на чистой БД и на текущей: `alembic upgrade head`.
4. Тест на новое поведение (каскад/индекс/поле).

### 7.4. Новая фоновая операция

1. Чистое правило/подсчёт — в `domain/`.
2. Метод в `ProcessingService` (или новом application-сервисе).
3. Задача-обёртка в `worker/tasks.py` через `_run(...)`; цепочка — `.delay`
   следующего шага только после успешного коммита (ARCH-6).
4. Тест фазы + обновление e2e-смоука при необходимости.

## 8. Git, ревью, Definition of Done

- GIT-1 (MUST): атомарные коммиты; формат сообщений: `область: императив`
  (`backend: ...`, `frontend: ...`, `docs: ...`, `infra: ...`).
- GIT-2 (MUST): в репозиторий не попадают секреты и персональные данные
  (транскрипты интервью, ключи, дампы) — SEC-2.
- GIT-3 (SHOULD): миграции, код и тесты одного изменения — в одном коммите.
- GIT-4 (MUST): перед push — зелёные Quality Gates; незакрытые пункты DoD
  перечислены в описании коммита/PR.

**DoD (Definition of Done) — обязательно всё:**

- [ ] код соответствует ARCH-* и конвенциям BE-*/FE-*;
- [ ] новые/изменённые ветки поведения покрыты тестами (TEST-*);
- [ ] `python -m pytest` зелёный; фронт-тесты зелёные, если фронт затронут;
- [ ] миграции применяются на чистой БД (если схема менялась);
- [ ] публичный контракт либо не изменён, либо изменение согласовано и покрыто;
- [ ] README/METHODOLOGY обновлены при изменении структуры/контракта/требований;
- [ ] e2e-смоук выполнен для крупных изменений.

## 9. Инфраструктура и окружение

- INFRA-1 (MUST): локальный запуск — только через `docker compose -f
  docker-compose.dev.yml`; сервисы: `backend`, `backend-worker`, `backend-db`,
  `backend-redis`, `frontend`.
- INFRA-2 (MUST): Postgres слушает 5432 внутри сети; наружу проброшен `5433:5432`;
  `POSTGRES_*`/`POSTGRES_PORT` — через `.env.dev`; у БД/Redis есть healthcheck.
- INFRA-3 (MUST): storage смонтирован в volume `backend-storage` (файлы переживают
  пересоздание контейнеров).
- INFRA-4 (MUST): точка входа API — `uvicorn src.presentation.app:app`;
  воркер — `celery -A src.worker.tasks.celery_app`.
- INFRA-5 (SHOULD): перед выполнением миграций в новом окружении —
  `docker exec backend alembic upgrade head`.
- INFRA-6 (SHOULD): после изменения зависимостей — обновлять `uv.lock`
  (`uv lock` в контейнере) и проверять сборку образов.

## 10. Безопасность и приватность

- SEC-1 (MUST): доверять содержимому, а не заголовкам: тип определяется по
  magic-байтам (`%PDF`), а не по `Content-Type`.
- SEC-2 (MUST): не коммитить PII/секреты; файлы с интервью/дампами держать вне
  git (например, в `.gitignore`).
- SEC-3 (MUST): имена файлов на диске — серверные; path traversal исключён
  (`FileStorage._resolve`); пользовательские строки валидируются по длине.
- SEC-4 (MUST): лимиты ресурсов: `max_upload_size` (413), чанковая обработка,
  отсутствие чтения файлов целиком в память.
- SEC-5 (SHOULD): логи без содержимого файлов и без персональных данных.
- SEC-6 (SHOULD, backlog): аутентификация/авторизация и антивирусная проверка —
  отсутствуют осознанно в MVP; при выходе в прод обязательны.

---


## 10.1. Запреты (анти-паттерны)

- MUST NOT: SQLAlchemy-доступ (`select`, `session.get`, `commit`) вне
  `infrastructure/repositories.py` (ARCH-3).
- MUST NOT: `HTTPException`, `UploadFile`, `FileResponse` в domain/application (ARCH-4).
- MUST NOT: чтение файла целиком (`read()`, `read_bytes()`, `read_text()`) при
  обработке содержимого (DATA-1).
- MUST NOT: «магические» строки статусов/уровней вместо `core/enums.py` (BE-2).
- MUST NOT: чтение `os.environ` вне `core/config.py` (BE-4).
- MUST NOT: хардкод URL API на фронте — только `apiClient`/`NEXT_PUBLIC_API_URL` (FE-2).
- MUST NOT: прямой `.delay()` из роута — только `enqueue_scan` (API-5).
- MUST NOT: правка применённых миграций; только новые ревизии (DATA-5).
- MUST NOT: коммит PII/секретов (SEC-2) и смешивание несвязанных изменений (GIT-1).
- MUST NOT: тесты, зависящие от времени/сети/порядка без явной фиксации (TEST-8).
- SHOULD NOT: generic-репозитории и абстракции «на будущее» без потребности.

## 11. Quality Gates (MUST прогонять перед коммитом)

```bash
# 1) стек поднят
 docker compose -f docker-compose.dev.yml up -d --build
# 2) схема БД актуальна (если менялась)
 docker exec backend alembic upgrade head
# 3) backend-тесты (все зелёные, без внешних сервисов)
 docker exec backend python -m pytest -q
# 4) frontend-тесты (если фронт затронут)
 cd frontend && npm ci && npm test
# 5) e2e-смоук (для крупных изменений)
 curl -s localhost:8000/files
 curl -s -o /dev/null -w '%{http_code}\n' localhost:3000/
```

Критерии приёмки итерации: пункты 1–5 выше; отсутствие регрессий в публичном
API; реестр требований не нарушен.

## 12. Шаблон инструкции для LLM

> Скопировать в начало задачи; подставить `<ЗАДАЧА>` и список ID.

```
Ты — разработчик проекта «файлообменник» (репозиторий sputnic-llc).

ОБЯЗАТЕЛЬНО соблюдай METHODOLOGY.md (реестр требований: ARCH/BE/FE/DATA/API/
TEST/INFRA/SEC/GIT/DOC). Затрагиваемые требования: <ID, ID, ...>.

КОНТЕКСТ
- Backend: backend/src/{core,domain,application,infrastructure,presentation,worker}
- Frontend: frontend/src/{types,lib,api,hooks,components,app}
- Слои и направление зависимостей — ARCH-1..6; доступ к БД — через UoW/репозитории.
- Контракт API зафиксирован в presentation/schemas.py и покрыт тестами.

ЗАДАЧА
<ЗАДАЧА>

КАК РАБОТАТЬ
1) Сначала составь план (какие слои затрагиваются, какие тесты добавишь).
2) Меняй код в порядке domain → application → infrastructure → presentation →
   frontend.
3) Для каждого изменения ветки поведения добавь/обнови тест (TEST-1..8).
4) Не меняй публичный контракт без явного указания.

ОГРАНИЧЕНИЯ (MUST NOT)
- импортировать SQLAlchemy вне infrastructure/repositories;
- бросать HTTPException вне presentation;
- читать файлы целиком в память;
- хардкодить URL API на фронте;
- править применённые миграции;
- коммитить секреты/PII.

ФОРМАТ ОТВЕТА
1) План (кратко). 2) Список изменённых файлов. 3) Код. 4) Команды проверки
(Quality Gates) и их фактический вывод. 5) Чек-лист DoD.
```

## 13. Реестр требований (проверка)

| ID | Проверка |
|---|---|
| ARCH-1 | `grep -rn "sqlalchemy\|fastapi\|celery" backend/src/domain` пусто |
| ARCH-2 | сервисы не импортируют `infrastructure.*` |
| ARCH-3 | `grep -rn "select(\|session" backend/src/application` пусто |
| ARCH-4 | `grep -rn "HTTPException\|UploadFile" backend/src/application backend/src/domain` пусто |
| ARCH-5 | новые интерфейсы — `Protocol` в `application/ports.py` |
| ARCH-6 | `worker/tasks.py` — только обёртки `_run(lambda s: s.method)` |
| BE-1..10 | ревью конвенций + pytest |
| FE-1..7 | ревью структуры + `npm test` |
| DATA-1..8 | тесты storage/метаданных/репозиториев + `alembic upgrade head` |
| API-1..5 | тесты `tests/test_api.py` + `localhost:8000/openapi.json` |
| TEST-1..8 | `docker exec backend python -m pytest` |
| INFRA-1..6 | `docker compose ps`, healthcheck'и, `alembic current` |
| SEC-1..6 | тесты сканера, ревью, `.gitignore` |
| GIT-1..4 | `git log --oneline`, `git status` |
| DOC-1..3 | README/METHODOLOGY актуальны |

## 14. Справочник домена (не менять без согласования)

- Статусы обработки: `uploaded → processing → processed | failed`.
- Статусы скана: `clean | suspicious | failed`.
- Уровни алертов: `info` (успех), `warning` (требует внимания), `critical` (сбой).
- Правила скана: подозрительные расширения (`.exe .bat .cmd .sh .js`); размер
  \> 10 МБ; `.pdf` без magic-байт `%PDF`.
- Метаданные: текст — `line_count`/`char_count`; PDF — `approx_page_count`.
- Настройки: `max_upload_size` 512 МБ, `chunk_size` 1 МБ, `storage_dir`
  `backend/storage/files`.

## 15. Рецепты (частые задачи)

- **Новый эндпоинт**: `presentation/schemas.py` (DTO) → метод в
  `application/services/*` (через UoW) → роут в `presentation/routes.py` с
  `Depends` → тесты (коды + побочные эффекты, TEST-3).
- **Новое поле в файле**: `domain/entities.py` → миграция (DATA-5) → проброс в
  `presentation/schemas.py` и `frontend/src/types` → тесты.
- **Новое правило скана**: чистая функция в `domain/scanning.py` → вызов в
  `ProcessingService.scan` → юнит-тест правила + тест фазы (TEST-4).
- **Новая фоновая операция**: метод в application-сервисе → задача-обёртка в
  `worker/tasks.py` → тест фазы → (при необходимости) e2e.
- **Новый экран**: `api/` → `hooks/` → `components/` → страница в `app/`
  (только композиция) → тесты хука/компонента (TEST-6).

## 16. Бэклог (приоритет сверху вниз)

1. Аутентификация/авторизация (SEC-6).
2. Пагинация + индексы для `/files` и `/alerts` (DATA-8, API-3).
3. Celery retry/backoff + dead-letter + идемпотентность алертов.
4. Наблюдаемость: метрики очереди/фаз, healthcheck воркера, алертинг «зависших».
5. Внешнее хранилище (S3/MinIO) как вторая реализация `FileStorage`.
6. Авто-обновление статусов на фронте (polling → SSE/WebSocket) + React Query.
7. Интеграционные тесты на Postgres в CI (в дополнение к SQLite).

Правило: фичи из бэклога реализуются только при явном запросе и с соблюдением
реестра требований (включая тесты и DoD).

---

## 17. Изменение методологии

- DOC-1 (MUST): требования меняются отдельным коммитом `docs:` с обоснованием;
- DOC-2 (MUST): новое правило получает ID и способ проверки в разделе 13;
- DOC-3 (SHOULD): противоречия между README, METHODOLOGY и кодом разрешаются в
  пользу METHODOLOGY, затем читается код/тесты.
