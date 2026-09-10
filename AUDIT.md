# Аудит тестового задания по фидбеку ревьюера (4/10)

> Фидбек дословно:
> **Бэк.** «Слои выделены слабо, нет репо, файлы намешаны в одном пакете, нет
> ООП в сервисах; из плюсов — файл пишется батчами асинхронно».
> **Фронт.** «Разбит отлично».

---

## 1. Верификация замечаний (сверка с кодом)

| Замечание | Что фактически в коде | Вердикт |
|---|---|---|
| Слои выделены слабо | Слои логически есть (config → models → storage → services → api/worker), но лежат плоскими модулями `src/*.py`; сервисы знают про SQLAlchemy (`AsyncSession`, `select`), ORM-сущности отдаются в API напрямую, воркер дублирует доступ к данным | **Справедливо частично**: нет «портов и адаптеров» и физических слоёв |
| Нет репо | Прямые `session.get/execute/commit` в `src/services.py:40,47,52` и `src/worker/tasks.py:90,113,145,171` | **Справедливо** |
| Файлы намешаны в одном пакете | `src/`: `config.py db.py errors.py models.py schemas.py storage.py scanner.py services.py main.py` + `api/`, `worker/` | **Справедливо** |
| Нет ООП в сервисах | Сервисы — модульные функции; классы есть только у инфраструктуры (`LocalStorage`) и моделей | **Справедливо** |
| Плюс: батчевое async I/O | `storage.write_temp()` — чанки ~1 МБ + `asyncio.to_thread`; `scanner.extract_*` — потоковые счётчики | **Подтверждено** |
| Фронт разбит отлично | `types/lib/api/hooks/components/app` + 20 тестов | **Подтверждено** |

**Вывод:** 3 замечания из 4 полностью справедливы, одно — по форме. Код их не
опровергает: реально нет репозиториев, пакетной слоистости и сервис-классов.

---

## 2. Разбор замечаний

### 2.1. Нет репозиториев

Доступ к БД размазан по слоям:

```python
# src/services.py — прикладной слой сам знает SQLAlchemy
result = await session.execute(select(StoredFile).order_by(StoredFile.created_at.desc()))
file_item = await session.get(StoredFile, file_id)

# src/worker/tasks.py — sync-копия того же доступа
item = session.get(StoredFile, file_id)
item.processing_status = "processing"
session.commit()
```

Последствия: запросы нельзя переиспользовать/мокать точечно; воркер не может
переиспользовать сервисы (они завязаны на async-сессию) → копипаст фаз; смена
схемы правится по всему коду.

### 2.2. Файлы намешаны в одном пакете

В `src/` рядом: конфиг (core), ORM (domain), БД/storage (infra), бизнес-правила
(application/domain), HTTP (presentation). По содержимому — 5 слоёв, по
структуре — один каталог.

### 2.3. Нет ООП в сервисах

Зависимости — параметры функций, а не поля объекта; нет портов (`Protocol`/ABC):

```python
async def create_file(session, storage, *, title, original_name, content_type, chunks): ...
async def delete_file(session, storage, file_id): ...
```

### 2.4. Слои выделены слабо (протечки)

- ORM → presentation: `response_model=FileItem` + `from_attributes` (сущность БД
  сериализуется напрямую, нет mapping-границы).
- Воркер дублирует application-логику (фазы — своя реализация того же).

---

## 3. Что сохранить

1. Потоковая обработка (зачтена): чанки 1 МБ, `asyncio.to_thread`, атомарный
   `os.replace`, лимит 512 МБ → `413`, «перенос хвоста» для `/Type /Page`.
2. 41 контрактный тест с регрессиями (DELETE с алертами → 204, `title` → 422).
3. Багфиксы: каскад алертов, порядок «БД → файл», `failed` вместо зависаний,
   inline-обработка при недоступном брокере.
4. Инфраструктура: healthcheck'и, порты, volume, миграции, README.
5. Frontend: слои + 20 тестов (оценено ревьюером на отлично).

---

## 4. Целевая архитектура (что внедрено)

```
backend/src/
├── core/            # config.py, errors.py, enums.py
├── domain/          # entities.py (ORM), scanning.py (правила + метаданные)
├── application/     # ports.py (Protocol), services/ (классы use-case)
├── infrastructure/  # db.py, repositories.py (SQLAlchemy + UnitOfWork), storage.py, celery_app.py
├── presentation/    # app.py, deps.py (DI), schemas.py (DTO), routes.py
└── worker/          # tasks.py — тонкие Celery-обёртки над сервисами
```

**Порты (application/ports.py)** — интерфейсы, свободные от SQLAlchemy/FastAPI:

```python
class FileRepository(Protocol):
    async def add(self, item: StoredFile) -> None: ...
    async def get(self, file_id: str) -> StoredFile | None: ...
    async def list_newest(self) -> Sequence[StoredFile]: ...
    async def delete(self, item: StoredFile) -> None: ...

class FileStorage(Protocol):
    async def write_temp(self, chunks) -> tuple[Path, int]: ...
    def commit(self, temp_path: Path, stored_name: str) -> Path: ...
    def delete(self, stored_name: str) -> None: ...
```

**Репозитории + Unit of Work (infrastructure)** — весь SQLAlchemy только здесь:

```python
class SqlAlchemyFileRepository(FileRepository):
    def __init__(self, session: AsyncSession) -> None: self._session = session
    async def get(self, file_id): return await self._session.get(StoredFile, file_id)
    async def list_newest(self):
        result = await self._session.execute(select(StoredFile).order_by(StoredFile.created_at.desc()))
        return result.scalars().all()

class SqlAlchemyUnitOfWork:
    async def __aenter__(self):
        self.session = self._factory()
        self.files = SqlAlchemyFileRepository(self.session)
        self.alerts = SqlAlchemyAlertRepository(self.session)
        return self
    async def commit(self): await self.session.commit()
    async def __aexit__(self, *exc): await self.session.rollback(); await self.session.close()
```

**Сервис-классы (application/services)** — DI через конструктор:

```python
class FileService:
    def __init__(self, uow_factory, storage: FileStorage) -> None: ...
    async def create(self, *, title, original_name, content_type, chunks) -> StoredFile: ...
    async def delete(self, file_id: str) -> None: ...

class ProcessingService:
    def __init__(self, uow_factory, storage: FileStorage) -> None: ...
    async def scan(self, file_id: str) -> bool: ...
    async def extract_metadata(self, file_id: str) -> bool: ...
    async def send_alert(self, file_id: str) -> bool: ...
```

**DI (presentation/deps.py)**: `get_file_service(request)` из `app.state`;
схемы ответов (`FileItem`/`AlertItem`) отделены от ORM-сущностей; сервисы
возвращают доменные сущности, presentation мапит их в DTO.

**Воркер переиспользует те же сервисы**: Celery-обёртка выполняет async-пайплайн
через `asyncio.run` с per-task движком (NullPool, dispose) — нет дублирования
логики, нет event-loop-хака на процесс; при недоступном брокере `enqueue_scan`
запускает тот же пайплайн в фоновом потоке.

---

## 5. План миграции (сохранены 41 тест)

1. `core/` — перенос `config.py`, `errors.py`; новые `enums.py` (StrEnum).
2. `domain/` — перенос `models.py` → `entities.py`, `scanner.py` → `scanning.py`.
3. `infrastructure/` — перенос `db.py`, `storage.py`; новые `repositories.py`, `unit_of_work` внутри них.
4. `application/` — `ports.py` (Protocol) + сервис-классы `FileService`, `AlertService`, `ProcessingService`.
5. `presentation/` — `app.py` (фабрика), `deps.py`, `schemas.py`, `routes.py`.
6. `worker/tasks.py` — тонкие обёртки над `ProcessingService`.
7. Миграции `env.py` — импорты `core.config`/`domain.entities`.
8. Тесты — обновлены импорты, добавлены тесты репозиториев; прогон в контейнере + живой сценарий.

---

## 6. Что осознанно не переусложняем

Repository + UoW для двух таблиц — на грани оверинжиниринга; внедрено
прагматично: два репозитория и UoW, без generic-базы и «спецификаций».
Аргумент для интервью: репозитории дают тестируемость и развязку с ORM, но
generic-репозиторий в MVP не оправдан.

---

## 7. Соответствие фидбеку

| Критерий | Как закрыт |
|---|---|
| Нет репо | `FileRepository`/`AlertRepository` + `UnitOfWork`; SQLAlchemy — только в `infrastructure` |
| Файлы намешаны | Пакеты `core/domain/application/infrastructure/presentation` |
| Нет ООП в сервисах | `FileService`/`AlertService`/`ProcessingService` — классы с DI |
| Слои выделены слабо | Порты (Protocol), UoW, mapping ORM→DTO, воркер через общие сервисы |
| Плюс: батчевый async I/O | Сохранён без изменений |
