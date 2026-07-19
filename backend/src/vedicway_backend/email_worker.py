from __future__ import annotations

import argparse
import os
import threading

from .email_delivery import EmailDispatcher, production_email_configuration_errors
from .store import Store


class EmailWorker:
    """Single-purpose consumer for transactional email deliveries."""

    def __init__(self, dispatcher: EmailDispatcher) -> None:
        self.dispatcher = dispatcher

    def process_once(self) -> bool:
        return self.dispatcher.process_once() is not None

    def drain(self, limit: int = 16) -> int:
        count = 0
        while count < limit and self.process_once():
            count += 1
        return count


def main() -> None:
    parser = argparse.ArgumentParser(description="VedicWay transactional email worker")
    parser.add_argument("--once", action="store_true", help="Process one queued delivery")
    parser.add_argument("--drain", type=int, default=0, help="Process up to N deliveries and stop")
    arguments = parser.parse_args()

    if os.environ.get("VEDICWAY_ENV", "development").casefold() == "production":
        errors = production_email_configuration_errors()
        if errors:
            raise RuntimeError(f"Transactional email configuration is invalid: {','.join(errors)}")

    worker = EmailWorker(EmailDispatcher(Store()))
    if arguments.once:
        worker.process_once()
    elif arguments.drain:
        worker.drain(arguments.drain)
    else:
        while True:
            if not worker.process_once():
                threading.Event().wait(0.75)


if __name__ == "__main__":
    main()
