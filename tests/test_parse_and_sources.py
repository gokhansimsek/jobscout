import hashlib
from email.message import EmailMessage

import pytest
from conftest import alert_html

from jobscout.parse import parse_alert_html
from jobscout.sources import ALERT_SENDER, AlertSourceError, FolderSource, GraphSource


def graph_page(*msg_ids: str, next_link: str | None = None) -> tuple[int, None, dict]:
    page: dict = {"value": [{"id": m, "body": {"content": f"<p>{m}</p>"}} for m in msg_ids]}
    if next_link:
        page["@odata.nextLink"] = next_link
    return 200, None, page


class FakeGraph:
    """Scripted Graph responses in order; records every (url, params) requested."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests: list[tuple[str, dict | None]] = []

    def __call__(self, url, params):
        self.requests.append((url, params))
        return self.responses.pop(0)


def test_parse_dedupes_links_and_splits_company_location():
    html = alert_html(
        ("111", "Backend Engineer", "Acme", "İzmir, Türkiye"),
        ("222", "Tech Lead", "Beta", "Remote"),
    )

    jobs = parse_alert_html(html)

    assert [j.job_id for j in jobs] == ["111", "222"]
    assert jobs[0].title == "Backend Engineer"
    assert jobs[0].company == "Acme"
    assert jobs[0].location == "İzmir, Türkiye"
    assert jobs[0].flags == ("Easy Apply",)
    assert jobs[0].url == "https://www.linkedin.com/jobs/view/111/"


def test_folder_source_reads_html_and_eml_and_ignores_the_rest(tmp_path):
    (tmp_path / "a.html").write_text("<p>html alert</p>", encoding="utf-8")
    eml = EmailMessage()
    eml["Subject"] = "alert"
    eml.set_content("plain")
    eml.add_alternative("<p>eml alert</p>", subtype="html")
    (tmp_path / "b.eml").write_bytes(eml.as_bytes())
    (tmp_path / "notes.txt").write_text("ignore me")

    alerts = list(FolderSource(tmp_path, tmp_path / "missing").alerts())

    assert [a.id for a in alerts] == ["a", "b"]
    assert "eml alert" in alerts[1].html


def test_graph_pages_through_next_link_with_the_query_only_on_page_one():
    get = FakeGraph(graph_page("m1", "m2", next_link="https://next/page2"), graph_page("m3"))

    alerts = list(GraphSource(7, get=get, sleep=lambda s: None).alerts())

    assert [a.html for a in alerts] == ["<p>m1</p>", "<p>m2</p>", "<p>m3</p>"]
    assert alerts[0].id == hashlib.sha1(b"m1").hexdigest()[:16]
    (_, first_params), second = get.requests
    query = (first_params or {}).get("$filter", "")
    assert ALERT_SENDER in query and "receivedDateTime ge" in query
    assert second == ("https://next/page2", None)


def test_graph_waits_out_throttling_then_continues():
    sleeps: list[float] = []
    get = FakeGraph((429, 3, {}), graph_page("m1"))

    alerts = list(GraphSource(get=get, sleep=sleeps.append).alerts())

    assert sleeps == [3]
    assert len(alerts) == 1


def test_graph_gives_up_after_persistent_throttling():
    get = FakeGraph(*[(429, 1, {})] * 5)

    with pytest.raises(AlertSourceError, match="throttling"):
        list(GraphSource(get=get, sleep=lambda s: None).alerts())


def test_graph_error_status_becomes_alert_source_error():
    get = FakeGraph((503, None, {}))

    with pytest.raises(AlertSourceError, match="HTTP 503"):
        list(GraphSource(get=get, sleep=lambda s: None).alerts())
