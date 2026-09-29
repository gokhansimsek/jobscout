"""Builders for fake LinkedIn HTML, shaped like the real alert emails and job pages."""

import pytest

from jobscout.store import JobStore


def alert_html(*jobs: tuple[str, str, str, str]) -> str:
    """jobs: (job_id, title, company, location). Each job gets 3 links, like the real emails."""
    cards = []
    for job_id, title, company, location in jobs:
        href = f"https://www.linkedin.com/comm/jobs/view/{job_id}?alertAction=markasviewed&token=x"
        cards.append(
            f'<a href="{href}"><img></a>'
            f'<a href="{href}"><a href="{href}">{title}</a>'
            f"<p>{company} · {location}</p><p>Easy Apply</p></a>"
        )
    return f"<html><body>{''.join(cards)}<a href='https://www.linkedin.com/comm/jobs/alerts'>Manage</a></body></html>"


def job_page_html(
    title: str, company: str, description: str, seniority: str = "Mid-Senior level"
) -> str:
    return f"""<html><body>
      <h1>{title}</h1>
      <a class="topcard__org-name-link">{company}</a>
      <span class="topcard__flavor--bullet">İzmir, Türkiye</span>
      <div class="show-more-less-html__markup"><p>{description}</p></div>
      <ul class="description__job-criteria-list">
        <li class="description__job-criteria-item">
          <h3 class="description__job-criteria-subheader">Seniority level</h3>
          <span class="description__job-criteria-text">{seniority}</span>
        </li>
      </ul>
    </body></html>"""


@pytest.fixture
def store(tmp_path) -> JobStore:
    return JobStore(tmp_path)
