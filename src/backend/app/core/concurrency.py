import asyncio
from collections.abc import Awaitable


def deadline_after(seconds: float, deadline: float | None = None) -> float:
    until = asyncio.get_running_loop().time() + seconds
    return min(until, deadline) if deadline is not None else until


async def gather_cancel_on_error[T](*awaitables: Awaitable[T]) -> list[T]:
    tasks = [asyncio.ensure_future(item) for item in awaitables]
    try:
        return list(await asyncio.gather(*tasks))
    except BaseException:
        # gather leaves siblings running after an error unless explicitly cancelled.
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise
