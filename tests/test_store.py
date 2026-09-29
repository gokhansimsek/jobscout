from conftest import alert_html

from jobscout.models import Alert, JobDetails, JobScore


def details(job_id: str) -> JobDetails:
    return JobDetails(job_id, "t", "c", "l", "desc")


def score(job_id: str, prompt_hash: str) -> JobScore:
    return JobScore(job_id, 8, "read", [], [], [], "ok", prompt_hash)


def test_add_alert_is_idempotent(store):
    alert = Alert("abc", alert_html(("1", "T", "C", "L")))

    assert store.add_alert(alert) is True
    assert store.add_alert(alert) is False


def test_jobs_dedupes_across_alerts_and_includes_manual_samples(store, tmp_path):
    store.add_alert(Alert("a1", alert_html(("1", "T1", "C", "L"), ("2", "T2", "C", "L"))))
    store.add_alert(Alert("a2", alert_html(("2", "T2", "C", "L"), ("3", "T3", "C", "L"))))
    (tmp_path / "samples").mkdir()
    (tmp_path / "samples" / "manual.html").write_text(
        alert_html(("4", "T4", "C", "L")), encoding="utf-8"
    )

    assert [j.ref.job_id for j in store.jobs()] == ["1", "2", "3", "4"]


def test_jobs_joins_details_and_score(store):
    store.add_alert(Alert("a", alert_html(("1", "T", "C", "L"), ("2", "T", "C", "L"))))
    store.save_details(details("1"))
    store.save_score(score("1", "h"))

    j1, j2 = store.jobs()

    assert j1.details == details("1") and j1.score == score("1", "h")
    assert j2.details is None and j2.score is None


def test_needing_details_and_needing_score(store):
    store.add_alert(Alert("a", alert_html(*[(i, "T", "C", "L") for i in "1234"])))
    for i in "123":
        store.save_details(details(i))
    store.save_score(score("1", "current"))
    store.save_score(score("2", "stale"))

    assert [r.job_id for r in store.needing_details()] == ["4"]
    # 1 is up to date, 2 is stale, 3 is unscored, 4 has no details yet
    assert [d.job_id for d in store.needing_score("current")] == ["2", "3"]
