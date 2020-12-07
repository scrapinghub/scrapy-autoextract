from asyncio import BoundedSemaphore
from typing import Dict, Hashable, Awaitable, TypeVar

import attr

T = TypeVar("T")


class SlotsSemaphore:
    """
    A synchronization primitive that keeps one semaphore per living slot.
    Useful for limiting concurrency within each slot without limiting concurrency
    between the slots.

    Internally, a dictionary is keeping a semaphore per each slot. When no
    more tasks pending or running for this slot, the semaphore for the slot
    is freed, so that the dictionary does not ever grow with slots.

    Example usage::

        sem = SlotsSemaphore(2)

        async def task(url):
            async with sem.use_slot(get_domain(url)):
                await fetch(url)

        results = await asyncio.gather(*[task(url) for url in urls])

    Or alternatively::

        sem = SlotsSemaphore(2)
        results = await asyncio.gather(*[sem.run(fetch(url), get_domain(url))
                                         for url in urls])


    Ideas for the future:
    - To avoid excessive creation and destruction of semaphores,
      the policy regarding when to evict an empty semaphore could be changed.
      Using a LRU cache instead of a dict might do the job.
    """

    def __init__(self, concurrency_per_slot: int):
        """
        :param concurrency_per_slot: maximum number of tasks that can run
                                     concurrently per each slot
        """
        self.concurrency_per_slot = concurrency_per_slot
        self.slots: Dict[Hashable, _SlotMeta] = {}

    def use_slot(self, slot: Hashable):
        """
        Return an asynchronous context manager to wrap your async code so
        that it respect the concurrency limits
        """
        return _SlotSemaphore(self, slot)

    async def run(self, awaitable: Awaitable[T], slot: Hashable) -> T:
        """Run the given awaitable respecting the concurrency limits"""
        async with self.use_slot(slot):
            return await awaitable

    def __str__(self):
        slots_str = "empty"
        if self.slots:
            counts_str = ",".join(
                str(info.registered_tasks) for info in self.slots.values()
            )
            slots_str = f"{len(self.slots)} slots. Tasks counts {counts_str}"
        return f"SlotsSemaphore({self.concurrency_per_slot}) {slots_str}"


@attr.s(auto_attribs=True)
class _SlotMeta:
    semaphore: BoundedSemaphore
    registered_tasks: int


class _SlotSemaphore:
    """
    Keys:
    - When no slot is present in the slots dictionary, a new one is created.
    - The number of registered tasks is tracked
    - When the number of registered tasks reaches 0 after releasing, the slot
      is removed
    """

    def __init__(self, parent: SlotsSemaphore, slot: Hashable):
        self.parent = parent
        self.slot = slot

    async def __aenter__(self):
        if self.slot not in self.parent.slots:
            self.parent.slots[self.slot] = _SlotMeta(
                BoundedSemaphore(self.parent.concurrency_per_slot), registered_tasks=0
            )
        slot_info = self.parent.slots[self.slot]
        slot_info.registered_tasks += 1
        await slot_info.semaphore.acquire()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        slot_info = self.parent.slots[self.slot]
        slot_info.semaphore.release()
        slot_info.registered_tasks -= 1
        if slot_info.registered_tasks == 0:
            del self.parent.slots[self.slot]
