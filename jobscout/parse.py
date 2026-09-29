"""Turn alert-email HTML into JobRef objects. Pure: no I/O."""

import re

from bs4 import BeautifulSoup

from jobscout.models import JobRef

JOB_ID_RE = re.compile(r"/jobs/view/(\d+)")


def parse_alert_html(html: str) -> list[JobRef]:
    """Extract the jobs listed in one alert email.

    Each job appears in several links; only the card link wraps ``<p>`` tags with
    company and location, so the others are skipped.

    Args:
        html: The alert email's HTML body.

    Returns:
        Unique jobs, in the order they appear in the email.
    """
    soup = BeautifulSoup(html, "html.parser")
    jobs: dict[str, JobRef] = {}

    for card in soup.find_all("a", href=JOB_ID_RE):
        paragraphs = [p.get_text(" ", strip=True) for p in card.find_all("p")]
        match = JOB_ID_RE.search(str(card.get("href", "")))
        if not paragraphs or not match or match.group(1) in jobs:
            continue

        job_id = match.group(1)
        title_link = card.find("a")
        title = title_link.get_text(" ", strip=True) if title_link else paragraphs[0]
        company, _, location = paragraphs[0].partition(" · ")
        jobs[job_id] = JobRef(
            job_id=job_id,
            title=title,
            company=company.strip(),
            location=location.strip(),
            flags=tuple(paragraphs[1:]),
        )

    return list(jobs.values())
