import asyncio
import os
import signal
from asyncio import CancelledError
from collections import Counter

import pytest
from scrapy_autoextract.task_manager import TaskManager
from tests.utils import async_test


class _TasksBench:
    def __init__(self):
        self.lock = asyncio.Lock()
        self.manager = TaskManager(cancel_on_signals={signal.SIGUSR1})
        self.n = 10

    async def identity(self, value):
        """Waits on the lock and then just return value"""
        assert len(self.manager.running_tasks) == self.n
        async with self.lock:
            return value

    async def release_after(self, sleep):
        """Releases the lock after some time"""
        await asyncio.sleep(sleep)
        assert len(self.manager.running_tasks) == self.n
        self.lock.release()
        return 0

    async def cancel_after(self, sleep):
        """Cancel all tasks after some time"""
        await asyncio.sleep(sleep)
        assert len(self.manager.running_tasks) == self.n
        self.manager.cancel_all()
        return CancelledError()

    async def kill_after(self, sleep):
        """Send SIGINT signal after some time"""
        await asyncio.sleep(sleep)
        assert len(self.manager.running_tasks) == self.n
        pid = os.getpid()
        os.kill(pid, signal.SIGUSR1)
        return CancelledError()


@pytest.fixture()
def tasks_bench():
    return _TasksBench()


class TestTaskManager:

    @async_test
    async def test_run(self, tasks_bench):
        """Run 10 tasks and waits for it"""
        await tasks_bench.lock.acquire()
        tasks = [
            tasks_bench.manager.run(tasks_bench.identity(i))
            for i in range(tasks_bench.n)
        ] + [tasks_bench.release_after(0.05)]
        result = await asyncio.gather(*tasks)
        assert sum(result) == sum(range(tasks_bench.n))
        assert len(tasks_bench.manager.running_tasks) == 0

    @async_test
    async def test_cancel_all(self, tasks_bench):
        """Run 10 tasks that waits on lock, and at some point all are cancelled"""
        await tasks_bench.lock.acquire()
        tasks = [
            tasks_bench.manager.run(tasks_bench.identity(i))
            for i in range(tasks_bench.n)
        ] + [tasks_bench.cancel_after(0.05)]
        result = await asyncio.gather(*tasks, return_exceptions=True)
        assert all(isinstance(r, CancelledError) for r in result)
        assert len(tasks_bench.manager.running_tasks) == 0

        # Submitted tasks after cancellation must be cancelled as well
        with pytest.raises(CancelledError):
            await tasks_bench.manager.run(tasks_bench.identity(1))

    @async_test
    async def test_signal_cancelation(self):
        """ Run 10 tasks that waits on lock, and at some point all are cancelled by a signal"""
        old_signal_handler_called = []

        def old_signal_handler(*args):
            old_signal_handler_called.append(True)
            raise ValueError(
                """
                The new handler should executed even if an error in raised by the old one.
                Also, the exception from the old handler should be raised.
                """
            )

        signal.signal(signal.SIGUSR1, old_signal_handler)

        tasks_bench = _TasksBench()
        await tasks_bench.lock.acquire()
        tasks = [
            tasks_bench.manager.run(tasks_bench.identity(i))
            for i in range(tasks_bench.n)
        ] + [tasks_bench.kill_after(0.05)]
        result = await asyncio.gather(*tasks, return_exceptions=True)
        type_count = Counter(type(r) for r in result)
        assert type_count.keys() == {CancelledError, ValueError}
        assert type_count[CancelledError] == 10
        assert len(tasks_bench.manager.running_tasks) == 0
        assert old_signal_handler_called

        # Submitted tasks after cancellation must be cancelled as well
        with pytest.raises(CancelledError):
            await tasks_bench.manager.run(tasks_bench.identity(1))
