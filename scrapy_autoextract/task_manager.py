import asyncio
import logging
import signal
from asyncio import CancelledError
from typing import Awaitable, Set, TypeVar

from scrapy.utils.ossignal import signal_names

logger = logging.getLogger(__name__)

T = TypeVar("T")


class TaskManager:
    """
    A class that runs async functions keeping track of those that are running.
    The tasks can be cancelled, and actually they are cancelled
    when ``signal.SIGINT`` is received.

    Note that cancelled tasks will receive exception ``CancelledError``

    Any task submitted after receive the cancelling order will raise also
    ``CancelledError``

    The created task managers will live during the entire lifecycle of the process
    because the signal handler needs the reference to cancel tasks on
    shutdown.

    Example usage::

        async def my_task(sleep):
            await asyncio.sleep(sleep)
            return "Finished"

        manager = TaskManager()
        for i in range(10):
            print(await manager.run(my_task(i)))

        await asyncio.sleep(5)
        manager.cancel_all()
    """

    def __init__(self, cancel_on_signals={signal.SIGINT, signal.SIGTERM}):
        self.running_tasks: Set[asyncio.Task] = set()
        self.cancelled = False
        for sig in cancel_on_signals:
            self._install_signal_handler(sig)

    def _install_signal_handler(self, sig):
        """Installs the signal handler for cancellation, respecting existing handler"""
        old_handler = signal.getsignal(sig)

        def new_handler(*args, **kwargs):
            # Invoke old handler if any
            exception = None
            if callable(old_handler):
                try:
                    old_handler(*args, **kwargs)
                except BaseException as e:
                    exception = e
            self._cancel_on_signal(*args, **kwargs)
            if exception:
                raise exception

        signal.signal(sig, new_handler)

    async def run(self, awaitable: Awaitable[T]) -> T:
        """Run a task"""
        task = asyncio.create_task(awaitable)
        self.running_tasks.add(task)
        try:
            # This avoids a potential race condition
            if self.cancelled:
                raise CancelledError()
            return await task
        finally:
            self.running_tasks.remove(task)

    def _cancel_on_signal(self, sig, frame):
        logger.info(
            f"Received {signal_names[sig]}. Cancelling {len(self.running_tasks)} running tasks"
        )
        self.cancel_all()

    def cancel_all(self):
        """
        Cancel all running tasks and any future submitted task
        """
        self.cancelled = True
        for task in self.running_tasks:
            task.cancel()

    def __len__(self):
        return len(self.running_tasks)
