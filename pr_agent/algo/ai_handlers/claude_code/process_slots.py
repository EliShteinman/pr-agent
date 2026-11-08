import asyncio
from weakref import WeakKeyDictionary


class ProcessSlots:
    """Cap concurrent CLI processes per event loop.

    Tools build a fresh handler per command, so a per-instance limit would not bound a webhook
    worker serving several merge requests. A semaphore binds to the loop that first awaits it,
    so each loop (e.g. one per asyncio.run in the CLI) gets its own.
    """

    def __init__(self):
        self._by_loop: WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Semaphore] = WeakKeyDictionary()

    def for_running_loop(self, limit: int) -> asyncio.Semaphore:
        loop: asyncio.AbstractEventLoop = asyncio.get_running_loop()
        semaphore: asyncio.Semaphore | None = self._by_loop.get(loop)
        if semaphore is None:
            semaphore = asyncio.Semaphore(limit)
            self._by_loop[loop] = semaphore
        return semaphore


CLAUDE_CODE_PROCESS_SLOTS = ProcessSlots()
