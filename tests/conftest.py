import sys

collect_ignore = []
if sys.version_info[:2] < (3, 7):
    # AutoExtract providers requires Python 3.7+
    collect_ignore.append("test_providers.py")
    collect_ignore.append("test_task_manager.py")
    collect_ignore.append("test_slot_semaphore.py")