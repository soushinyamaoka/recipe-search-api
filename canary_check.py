"""Run a sequential canary check against every registered recipe scraper."""

import asyncio
import logging
import time
from datetime import datetime
from typing import Any, Mapping

from app import SCRAPERS, _SAFE_LOG_FIELDS, log_event


CANARY_KEYWORD = "カレー"
CANARY_JOB = "recipe-search-canary"

# The shared formatter emits only explicitly allowed fields. These names contain
# canary metadata only; no URL, response body, or exception message is included.
_SAFE_LOG_FIELDS.update(
    {
        "keyword",
        "site_count",
        "site",
        "hit_count",
        "elapsed_ms",
    }
)


async def run_canary(
    scrapers: Mapping[str, Mapping[str, Any]] | None = None,
) -> int:
    """Check every scraper once and return zero only when all return results."""
    scraper_registry = SCRAPERS if scrapers is None else scrapers
    run_id = datetime.now().astimezone().strftime("%Y%m%dT%H%M%S%f%z")
    job_started = time.perf_counter()
    failed_sites = 0

    log_event(
        logging.INFO,
        "job_start",
        job=CANARY_JOB,
        run_id=run_id,
        keyword=CANARY_KEYWORD,
        site_count=len(scraper_registry),
    )

    for site, scraper in scraper_registry.items():
        site_started = time.perf_counter()
        hit_count: int | None = None
        status = "error"
        level = logging.ERROR

        try:
            if scraper["paginated"]:
                results = await scraper["fn"](CANARY_KEYWORD, 1)
            else:
                results = await scraper["fn"](CANARY_KEYWORD)
            hit_count = len(results)
            if hit_count > 0:
                status = "ok"
                level = logging.INFO
            else:
                status = "zero"
                level = logging.WARNING
        except Exception:
            # Do not include the exception or its message in canary logs.
            pass

        if status != "ok":
            failed_sites += 1

        log_event(
            level,
            "canary_site_result",
            job=CANARY_JOB,
            run_id=run_id,
            site=site,
            hit_count=hit_count,
            status=status,
            elapsed_ms=round((time.perf_counter() - site_started) * 1000),
        )

    overall_status = "success" if failed_sites == 0 else "failure"
    log_event(
        logging.INFO if failed_sites == 0 else logging.ERROR,
        "job_end",
        job=CANARY_JOB,
        run_id=run_id,
        status=overall_status,
        site_count=len(scraper_registry),
        duration_ms=round((time.perf_counter() - job_started) * 1000),
    )
    return 0 if failed_sites == 0 else 1


def main() -> int:
    """Run the asynchronous canary from a command-line entry point."""
    return asyncio.run(run_canary())


if __name__ == "__main__":
    raise SystemExit(main())
