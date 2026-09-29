from email.message import EmailMessage

from conftest import alert_html

from jobscout.parse import parse_alert_html
from jobscout.sources import FolderSource


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
