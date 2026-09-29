"""JobScout CLI.

Usage::

    python -m jobscout run [--batch] [--limit N] [--days D] [--model M]   whole pipeline
    python -m jobscout fetch [--days D]      pull alert emails from Outlook
    python -m jobscout jobs                  list known jobs and their state
    python -m jobscout enrich [--max N]      fetch job pages
    python -m jobscout score [--batch] [--limit N] [--model M]
    python -m jobscout resume BATCH_ID       collect an earlier batch
    python -m jobscout report                write data/report.md
"""

import argparse
from datetime import UTC, datetime

from jobscout.config import DATA_DIR, setup
from jobscout.enrich import MAX_REQUESTS_PER_RUN, enrich
from jobscout.report import ranked, render_report
from jobscout.score import DEFAULT_MODEL, MODELS, Scorer, ScoreRun, make_client
from jobscout.sources import GraphSource
from jobscout.store import JobStore

REPORT = DATA_DIR / "report.md"


def cmd_fetch(store: JobStore, days: int) -> None:
    """Save new alert emails from Outlook into the store.

    Args:
        store: Where alerts are saved.
        days: How far back to look.
    """
    new = sum(store.add_alert(a) for a in GraphSource(days).alerts())
    print(f"{new} new alert emails")


def cmd_jobs(store: JobStore) -> None:
    """Print every known job and how far it has got through the pipeline.

    Args:
        store: Where jobs are read from.
    """
    jobs = store.jobs()
    for j in jobs:
        state = f"{j.score.score:>2}/10" if j.score else ("detail" if j.details else "  -  ")
        print(f"{state}  {j.ref.job_id}  {j.ref.title} @ {j.ref.company} ({j.ref.location})")
    print(f"\n{len(jobs)} unique jobs")


def cmd_enrich(store: JobStore, max_requests: int) -> None:
    """Fetch job pages for jobs without details and print the outcome.

    Args:
        store: Where jobs are read from and details saved.
        max_requests: Hard cap on page requests.
    """
    result = enrich(store, max_requests=max_requests)
    for d in result.fetched:
        print(f"  + {d.job_id}  {d.title} @ {d.company}")
    for job_id, reason in result.failed:
        print(f"  ! {job_id}: {reason}")
    if result.blocked:
        print("  ! LinkedIn is blocking; stopped early. Try again tomorrow.")
    print(f"{len(result.fetched)} fetched, {len(store.needing_details())} still without details")


def _scorer(model: str) -> Scorer:
    """Build a Scorer from the production client and ``data/cv.md`` + ``data/rubric.md``.

    Args:
        model: A key of ``MODELS``.

    Returns:
        A ready Scorer.
    """
    return Scorer(
        make_client(),
        cv=(DATA_DIR / "cv.md").read_text(encoding="utf-8"),
        rubric=(DATA_DIR / "rubric.md").read_text(encoding="utf-8"),
        model=model,
    )


def _save_run(store: JobStore, run: ScoreRun) -> None:
    """Save a run's scores and print scores, failures and cost.

    Args:
        store: Where scores are saved.
        run: The finished run.
    """
    for s in run.scores:
        store.save_score(s)
        print(f"  {s.score:>2}/10 {s.verdict:<5} {s.job_id}")
    for job_id, reason in run.failed:
        print(f"  ! {job_id}: {reason}")
    print(run.usage)


def cmd_score(store: JobStore, batch: bool, limit: int | None, model: str) -> None:
    """Score jobs that are unscored or stale.

    Args:
        store: Where jobs are read from and scores saved.
        batch: Use the Batch API.
        limit: Score at most this many jobs; None for all.
        model: A key of ``MODELS``.
    """
    scorer = _scorer(model)
    jobs = store.needing_score(scorer.prompt_hash)[:limit]
    if not jobs:
        print("Nothing to score (all jobs already scored with the current prompt).")
        return
    print(f"Scoring {len(jobs)} jobs with {model} ({'batch' if batch else 'standard'})")

    def on_submit(batch_id: str) -> None:
        """Tell the user how to resume if they stop waiting.

        Args:
            batch_id: The submitted batch.
        """
        print(f"  batch {batch_id} submitted. Ctrl+C is safe; resume with:")
        print(f"  python -m jobscout resume {batch_id}")

    _save_run(store, scorer.score(jobs, batch=batch, on_submit=on_submit))


def cmd_resume(store: JobStore, batch_id: str, model: str) -> None:
    """Collect an earlier batch and save its scores.

    Args:
        store: Where scores are saved.
        batch_id: The batch to collect.
        model: The model the batch was submitted with (for pricing and prompt hash).
    """
    _save_run(store, _scorer(model).collect(batch_id))


def cmd_report(store: JobStore) -> None:
    """Write ``data/report.md`` and print the top 10 jobs.

    Args:
        store: Where jobs are read from.
    """
    jobs = store.jobs()
    today = datetime.now(UTC).astimezone().date()
    REPORT.write_text(render_report(jobs, today), encoding="utf-8")
    print(f"\nTop matches (full report: {REPORT})")
    for j in ranked(jobs)[:10]:
        s = j.score
        assert s is not None
        print(f"  {s.score:>2}/10 {s.verdict:<5} {j.ref.title} @ {j.ref.company}  {j.ref.url}")


def main() -> None:
    """Parse the command line and run one subcommand."""
    setup()
    ap = argparse.ArgumentParser(prog="jobscout")
    sub = ap.add_subparsers(dest="cmd", required=True)

    run_p = sub.add_parser("run")
    fetch_p = sub.add_parser("fetch")
    sub.add_parser("jobs")
    enrich_p = sub.add_parser("enrich")
    score_p = sub.add_parser("score")
    resume_p = sub.add_parser("resume")
    sub.add_parser("report")

    for p in (run_p, fetch_p):
        p.add_argument("--days", type=int, default=14)
    for p in (run_p, score_p):
        p.add_argument("--batch", action="store_true", help="Batch API: 50%% off, async")
        p.add_argument("--limit", type=int)
    for p in (run_p, score_p, resume_p):
        p.add_argument("--model", default=DEFAULT_MODEL, choices=sorted(MODELS))
    enrich_p.add_argument("--max", type=int, default=MAX_REQUESTS_PER_RUN)
    resume_p.add_argument("batch_id")
    args = ap.parse_args()

    store = JobStore()
    match args.cmd:
        case "fetch":
            cmd_fetch(store, args.days)
        case "jobs":
            cmd_jobs(store)
        case "enrich":
            cmd_enrich(store, args.max)
        case "score":
            cmd_score(store, args.batch, args.limit, args.model)
        case "resume":
            cmd_resume(store, args.batch_id, args.model)
        case "report":
            cmd_report(store)
        case "run":
            print("1/4 fetch")
            cmd_fetch(store, args.days)
            print("2/4 enrich")
            cmd_enrich(store, MAX_REQUESTS_PER_RUN)
            print("3/4 score")
            cmd_score(store, args.batch, args.limit, args.model)
            print("4/4 report")
            cmd_report(store)


if __name__ == "__main__":
    main()
