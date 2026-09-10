"""Alert read use-cases (application layer)."""

from collections.abc import Sequence

from src.application.ports import UowFactory
from src.domain.entities import Alert


class AlertService:
    def __init__(self, uow_factory: UowFactory) -> None:
        self._uow_factory = uow_factory

    async def list_alerts(self) -> Sequence[Alert]:
        async with self._uow_factory() as uow:
            return await uow.alerts.list_newest()
