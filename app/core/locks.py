import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager


class KeyedLock:
    """Взаимное исключение по ключу; запись о ключе удаляется, когда им никто не пользуется."""

    def __init__(self) -> None:
        self._entries: dict[str, tuple[asyncio.Lock, int]] = {}

    @asynccontextmanager
    async def __call__(self, key: str) -> AsyncIterator[None]:
        lock, users = self._entries.get(key, (asyncio.Lock(), 0))
        self._entries[key] = (lock, users + 1)
        try:
            async with lock:
                yield
        finally:
            lock, users = self._entries[key]
            if users == 1:
                del self._entries[key]
            else:
                self._entries[key] = (lock, users - 1)
