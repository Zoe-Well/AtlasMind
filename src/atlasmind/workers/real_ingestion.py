"""Persistent ingestion worker process entry point."""

from __future__ import annotations

import asyncio

from atlasmind.runtime import create_runtime
from atlasmind.settings import load_settings


async def run() -> None:
    settings = load_settings()
    runtime = create_runtime(settings)
    await runtime.verify()
    try:
        while True:
            processed = await runtime.knowledge.process_next()
            if processed is None:
                await asyncio.sleep(settings.ingestion_poll_seconds)
    finally:
        await runtime.close()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
