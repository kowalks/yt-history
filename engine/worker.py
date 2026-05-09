"""Background task management for scraping sessions."""

import threading
import uuid
from typing import List, Callable


def start_task(target: Callable, args: tuple) -> str:
    """Launches a daemon thread for a background task."""
    thread = threading.Thread(
        target=target,
        args=args,
        daemon=True
    )
    thread.start()
    return str(uuid.uuid4())
