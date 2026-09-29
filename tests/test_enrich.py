from conftest import alert_html, job_page_html

from jobscout.enrich import FetchError, enrich
from jobscout.models import Alert


def seed(store, n: int) -> None:
    store.add_alert(
        Alert(
            "a",
            alert_html(*[(str(i), f"Title {i}", "Email Co", "L") for i in range(1, n + 1)]),
        )
    )


class FakeGet:
    """Scripted responses by job id; records every URL requested."""

    def __init__(self, responses: dict):
        self.responses = responses
        self.urls: list[str] = []

    def __call__(self, url: str):
        self.urls.append(url)
        job_id = url.rstrip("/").rsplit("/", 1)[-1]
        response = self.responses[job_id]
        if isinstance(response, Exception):
            raise response
        return response


def test_fetches_parses_and_saves_details(store):
    seed(store, 1)
    get = FakeGet(
        {
            "1": (
                200,
                job_page_html("Senior Backend", "Acme", "Python and AWS", "Entry level"),
            )
        }
    )

    result = enrich(store, get=get, sleep=lambda s: None)

    saved = store.jobs()[0].details
    assert result.fetched == [saved]
    assert saved.title == "Senior Backend" and saved.company == "Acme"
    assert "Python and AWS" in saved.description
    assert saved.criteria == {"Seniority level": "Entry level"}


def test_removed_job_keeps_email_data_with_empty_description(store):
    seed(store, 1)

    enrich(store, get=FakeGet({"1": (404, "")}), sleep=lambda s: None)

    saved = store.jobs()[0].details
    assert saved.title == "Title 1" and saved.description == ""


def test_blocking_stops_the_run_and_saves_nothing_more(store):
    seed(store, 3)
    get = FakeGet({"1": (200, job_page_html("A", "B", "C")), "2": (999, ""), "3": (200, "")})

    result = enrich(store, get=get, sleep=lambda s: None)

    assert result.blocked is True
    assert len(get.urls) == 2  # job 3 never requested
    assert [r.job_id for r in store.needing_details()] == ["2", "3"]


def test_page_without_description_is_retried_not_saved(store):
    seed(store, 2)
    login_wall = "<html><body><h1>Sign in to view this job</h1></body></html>"
    get = FakeGet({"1": (200, login_wall), "2": (200, job_page_html("A", "B", "C"))})

    result = enrich(store, get=get, sleep=lambda s: None)

    assert result.failed == [("1", "no job description on page")]
    assert [d.job_id for d in result.fetched] == ["2"]
    assert [r.job_id for r in store.needing_details()] == ["1"]


def test_network_error_skips_job_and_continues(store):
    seed(store, 2)
    get = FakeGet({"1": FetchError("timeout"), "2": (200, job_page_html("A", "B", "C"))})

    result = enrich(store, get=get, sleep=lambda s: None)

    assert result.failed == [("1", "timeout")]
    assert [d.job_id for d in result.fetched] == ["2"]


def test_request_cap_and_delay_between_requests(store):
    seed(store, 5)
    get = FakeGet({str(i): (200, job_page_html("A", "B", "C")) for i in range(1, 6)})
    sleeps: list[float] = []

    enrich(store, get=get, sleep=sleeps.append, max_requests=3)

    assert len(get.urls) == 3
    assert len(sleeps) == 2  # between requests, never before the first
    assert all(3 <= s <= 7 for s in sleeps)
