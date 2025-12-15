import asyncio
import json
from typing import AsyncGenerator, List, Set

from .schemas import SearchJobsInput, Job
from .adapters.seek import search_seek
from .adapters.linkedin import search_linkedin
from .session import get_seen, add_seen


def _sse(event: str, data: dict) -> bytes:
    return (f"event: {event}\n" + "data: " + json.dumps(data, ensure_ascii=False) + "\n\n").encode("utf-8")


async def stream_jobs(input: SearchJobsInput) -> AsyncGenerator[bytes, None]:
    """
    Streams jobs as they are discovered. Uses session_id for server-side de-duplication.
    """
    requested = input.limit
    alloc = input.allocation or {}

    # Build initial exclude set from client and session memory
    exclude: Set[str] = set(input.exclude_hashes or [])
    if input.session_id:
        exclude |= get_seen(input.session_id)

    delivered: Set[str] = set()

    # Async queue to collect results from worker tasks
    queue: asyncio.Queue[Job | None] = asyncio.Queue()

    async def produce_seek():
        n = alloc.get("seek", 0)
        if n <= 0:
            return
        remaining = n
        local_exclude = set(exclude)
        attempts = 0
        max_attempts = max(3, n)
        # Incremental fetch: small pages to enable earlier streaming
        while remaining > 0 and attempts < max_attempts:
            page = min(1, remaining)
            jobs = await asyncio.to_thread(search_seek, input.query, page, list(local_exclude))
            if not jobs:
                attempts += 1
                await asyncio.sleep(0.25)
                continue
            attempts = 0
            for j in jobs:
                if j.hash in local_exclude:
                    continue
                local_exclude.add(j.hash)
                remaining -= 1
                await queue.put(j)
                if remaining <= 0:
                    break
        return

    async def produce_linkedin():
        n = alloc.get("linkedin", 0)
        if n <= 0:
            return
        remaining = n
        local_exclude = set(exclude)
        attempts = 0
        max_attempts = max(3, n)
        while remaining > 0 and attempts < max_attempts:
            page = min(1, remaining)
            jobs = await asyncio.to_thread(search_linkedin, input.query, page, list(local_exclude))
            if not jobs:
                attempts += 1
                await asyncio.sleep(0.25)
                continue
            attempts = 0
            for j in jobs:
                if j.hash in local_exclude:
                    continue
                local_exclude.add(j.hash)
                remaining -= 1
                await queue.put(j)
                if remaining <= 0:
                    break
        return

    producers = [asyncio.create_task(produce_seek()), asyncio.create_task(produce_linkedin())]

    # Emit initial progress
    yield _sse("progress", {"delivered": 0, "requested": requested, "by_source": alloc})

    try:
        done_sources = 0
        while True:
            # Stop if fulfilled
            if len(delivered) >= requested:
                break

            try:
                item = await asyncio.wait_for(queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                # periodic heartbeat
                yield _sse("progress", {"delivered": len(delivered), "requested": requested})
                # check if producers finished
                if all(p.done() for p in producers):
                    break
                continue

            if item is None:
                done_sources += 1
                if done_sources >= len(producers):
                    break
                continue

            job: Job = item
            if job.hash in exclude or job.hash in delivered:
                continue
            delivered.add(job.hash)
            # add to session seen immediately
            if input.session_id:
                add_seen(input.session_id, [job.hash])
            yield _sse("job", job.model_dump())

            # emit light progress
            yield _sse("progress", {"delivered": len(delivered), "requested": requested})

            if len(delivered) >= requested:
                break

        # Ensure producers complete
        await asyncio.gather(*producers, return_exceptions=True)
    finally:
        # Final end event
        yield _sse("end", {"delivered": len(delivered), "requested": requested})
