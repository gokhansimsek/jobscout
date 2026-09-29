import json

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


def test_records_from_an_older_shape_load_or_count_as_missing(store, tmp_path):
    store.add_alert(Alert("a", alert_html(*[(i, "T", "C", "L") for i in "12345"])))
    (tmp_path / "jobs").mkdir()
    (tmp_path / "scores").mkdir()
    # 1: a field since removed is ignored; 2: a required field is missing; 3: not JSON;
    # 4: JSON but not an object; 5: not UTF-8.
    (tmp_path / "jobs" / "1.json").write_text(
        json.dumps({**details("1").__dict__, "removed_field": "x"}), encoding="utf-8"
    )
    (tmp_path / "jobs" / "2.json").write_text(json.dumps({"job_id": "2"}), encoding="utf-8")
    (tmp_path / "scores" / "3.json").write_text("{truncated", encoding="utf-8")
    (tmp_path / "scores" / "4.json").write_text("null", encoding="utf-8")
    (tmp_path / "scores" / "5.json").write_bytes(b"\xff\xfe not utf-8")

    j1, j2, j3, j4, j5 = store.jobs()

    assert j1.details == details("1")
    assert j2.details is None  # fetched again
    assert [r.job_id for r in store.needing_details()] == ["2", "3", "4", "5"]
    assert j3.score is None and j4.score is None and j5.score is None  # scored again
