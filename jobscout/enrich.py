"""Fetch each job's public LinkedIn page and extract "About the job".

Interface: ``enrich(store) -> EnrichResult`` fills in JobDetails for jobs that lack them.

Polite by design (LinkedIn's terms forbid bulk scraping; keep volume personal-scale):
no login cookies, cached forever per job, random delay, hard cap per run, stop on blocking.
The page getter and sleep are parameters, so all of that is testable offline.
"""

import random
import time
from collections.abc import Callable
from dataclasses import dataclass, field

import requests
from bs4 import BeautifulSoup, Tag

from jobscout.models import JobDetails, JobRef
from jobscout.store import JobStore

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}
MAX_REQUESTS_PER_RUN = 40
DELAY_SECONDS = (3.0, 7.0)
BLOCKED_STATUSES = {429, 999}  # 999 = LinkedIn's "go away" status

# url -> (status, html). Raises FetchError on network failure.
PageGetter = Callable[[str], tuple[int, str]]


class FetchError(Exception):
    """Network-level failure (DNS, timeout, reset). The job is skipped for this run."""


def http_getter() -> PageGetter:
    """Build the production page getter: one requests session with browser-like headers.

    Returns:
        A function that GETs a URL and returns ``(status, html)``, raising FetchError
        on network failure.
    """
    session = requests.Session()
    session.headers.update(HEADERS)

    def get(url: str) -> tuple[int, str]:
        """GET one page.

        Args:
            url: Page to fetch.

        Returns:
            The HTTP status and response body.

        Raises:
            FetchError: On any network-level failure.
        """
        try:
            resp = session.get(url, timeout=30)
        except requests.RequestException as e:
            raise FetchError(str(e)) from e
        return resp.status_code, resp.text

    return get


@dataclass
class EnrichResult:
    """Outcome of one enrichment run.

    Attributes:
        fetched: Details fetched and saved this run.
        failed: ``(job_id, reason)`` for jobs skipped this run; they are retried next run.
        blocked: True if LinkedIn started blocking and the run stopped early.
    """

    fetched: list[JobDetails] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)
    blocked: bool = False


def enrich(
    store: JobStore,
    *,
    get: PageGetter | None = None,
    sleep: Callable[[float], None] = time.sleep,
    max_requests: int = MAX_REQUESTS_PER_RUN,
) -> EnrichResult:
    """Fetch and save details for jobs in the store that have none.

    A removed job (404) is saved with the email's data and an empty description,
    so it is not requested again. A page with no description (e.g. a login wall)
    is a failure, so the job is retried next run.

    Args:
        store: Where jobs are read from and details are saved.
        get: Page getter; defaults to a real HTTP session.
        sleep: Called with a random 3-7 s delay between requests.
        max_requests: Hard cap on page requests this run.

    Returns:
        What was fetched, what failed, and whether LinkedIn blocked the run.
    """
    get = get or http_getter()
    result = EnrichResult()
    requests_made = 0

    for ref in store.needing_details():
        if requests_made >= max_requests:
            break
        if requests_made:
            sleep(random.uniform(*DELAY_SECONDS))
        requests_made += 1

        try:
            status, html = get(ref.url)
        except FetchError as e:
            result.failed.append((ref.job_id, str(e)))
            continue

        if status in BLOCKED_STATUSES:
            result.blocked = True  # stop the whole run; cached jobs are still usable
            break
        if status == 404:
            details = JobDetails(ref.job_id, ref.title, ref.company, ref.location, "")
        elif status >= 400:
            result.failed.append((ref.job_id, f"HTTP {status}"))
            continue
        else:
            details = _parse_job_page(ref, html)
            if not details.description:
                # A login wall or changed layout, not the job page: saving it would
                # cache an empty description forever.
                result.failed.append((ref.job_id, "no job description on page"))
                continue

        store.save_details(details)
        result.fetched.append(details)

    return result


def _text(node: Tag, selector: str) -> str:
    """Get the text of the first element matching a CSS selector.

    Args:
        node: Element (or whole document) to search in.
        selector: CSS selector.

    Returns:
        The element's whitespace-normalised text, or "" if nothing matches.
    """
    el = node.select_one(selector)
    return el.get_text(" ", strip=True) if el else ""


def _parse_job_page(ref: JobRef, html: str) -> JobDetails:
    """Extract details from a public job page.

    Args:
        ref: The job as the email described it; used for any field the page lacks.
        html: The job page's HTML.

    Returns:
        The job's details.
    """
    soup = BeautifulSoup(html, "html.parser")
    desc_el = soup.select_one(".show-more-less-html__markup")
    criteria = {}
    for item in soup.select(".description__job-criteria-item"):
        key = _text(item, ".description__job-criteria-subheader")
        if key:
            criteria[key] = _text(item, ".description__job-criteria-text")
    return JobDetails(
        job_id=ref.job_id,
        title=_text(soup, "h1") or ref.title,
        company=_text(soup, ".topcard__org-name-link") or ref.company,
        location=_text(soup, ".topcard__flavor--bullet") or ref.location,
        # "\n" keeps bullet structure readable for the LLM
        description=desc_el.get_text("\n", strip=True) if desc_el else "",
        criteria=criteria,
    )
