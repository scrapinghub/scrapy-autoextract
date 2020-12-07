import asyncio
from collections import Counter

from scrapy_autoextract.slot_semaphore import SlotsSemaphore

from .utils import async_test


class TaskSimulator:
    """
    Executes dummy tasks using ``SlotSemaphore``. Useful for unit testing.
    """

    def __init__(self, slot_concurrency):
        self.slot_concurrency = slot_concurrency

        self.total_runned_tasks = 0
        self.task_id_generator = 0
        self.slot_sem = SlotsSemaphore(self.slot_concurrency)
        self.registered_tasks = Counter()
        self.running_tasks = Counter()
        self.max_slots_in_parallel = 0

    async def task(self, slot, sleep, duration):
        """
        Executed a dummy task for the given slot.
        :param slot: The slot
        :param sleep: sleep time before acquiring an semaphore executing the time
        :param duration: duration of the task
        """
        self.task_id_generator = self.task_id_generator + 1
        task_id = self.task_id_generator

        def log(text):
            print(
                f"[{task_id:3}] {text}. Parallelism {self.running_tasks[slot]}. Registered tasks {self.registered_tasks[slot]}"
            )

        await asyncio.sleep(sleep)

        assert len(str(self.slot_sem)) > 0
        self.registered_tasks[slot] += 1
        log("Acquiring")
        await self.slot_sem.run(self.run_task(duration, log, slot), slot)
        self.running_tasks[slot] -= 1
        self.total_runned_tasks += 1
        self.registered_tasks[slot] -= 1
        assert len(str(self.slot_sem)) > 0
        log("Finished")

    async def run_task(self, duration, log, slot):
        self.running_tasks[slot] += 1
        log("Running")
        assert (
                self.running_tasks[slot] > 0
                and self.running_tasks[slot] <= self.slot_concurrency
        )
        assert len(str(self.slot_sem)) > 0
        self.max_slots_in_parallel = max(
            self.max_slots_in_parallel,
            sum([1 for tasks in self.running_tasks.values() if tasks]),
        )
        await asyncio.sleep(duration)


@async_test
async def test_slot_semaphore_simple_case():
    parallelism = 3
    sim = TaskSimulator(parallelism)
    duration = 0.05
    await asyncio.gather(
        sim.task(1, 0, duration),
        sim.task(1, 0, duration),
        sim.task(1, 0, duration),
        sim.task(1, 0, duration),
    )
    assert sim.total_runned_tasks == 4
    assert sim.slot_sem.slots == {}


@async_test
async def test_slot_semaphore():
    """
    Simulate the execution of concurrent tasks respecting a given
    parallelism per slot.

    The time is divided in a fixed number of ticks. For each tick,
    N tasks can be executed. At the first tick, all tasks are
    scheduled. For the second tick, only the par tasks are executed: 0, 2, 4, ..
    For the third one, only those divisible by 3. And so on. And this happens
    cyclically each N ticks.

    The same is happening for several slots. For the first slot, there is
    no delay between tasks, so all tasks for a particular tick are scheduled
    for the same time. But for slots higher than 0 some small delay is introduced
    to misalign them.

    So in conclusion, the following is tested:
    - running more tasks than the allowed parallelism, but respecting
      the parallelism
    - running tasks for different slots
    """
    parallelism = 3
    concurrency = 2 * parallelism
    slots = 3
    clock_tick = 0.025
    ticks = 30

    tasks = []
    sim = TaskSimulator(parallelism)
    for tick in range(ticks):
        for task in range(concurrency):
            for slot in range(slots):
                if task % ((tick % concurrency) + 1) == 0:
                    start_time = tick * clock_tick
                    # Introducing some delays. No delays in slot 0.
                    # Higher delay as the slot is higher
                    # Again, no delay is task is 0.
                    # Higher delays is the task is higher
                    # Delay always bounded by clock_tick
                    delay_multiplier = (slot * task) / (slots * concurrency)
                    delay = delay_multiplier * clock_tick
                    start_time += delay
                    tasks.append(sim.task(slot, start_time, clock_tick))

    await asyncio.gather(*tasks)
    assert sim.total_runned_tasks == len(tasks)
    assert sim.slot_sem.slots == {}
    assert sim.max_slots_in_parallel == parallelism
