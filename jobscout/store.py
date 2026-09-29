"""Job store: the one module that knows how job data is laid out on disk.

Layout under the store's root::

    emails/   alerts saved by add_alert()
    samples/  alerts you drop in by hand (.msg from Outlook, .eml, .html)
    jobs/     <job_id>.json  JobDetails
    scores/   <job_id>.json  JobScore

Callers ask questions ("which jobs need a score?") and never touch paths.
"""

import json
from dataclasses import asdict
from pathlib import Path

from jobscout.config import DATA_DIR
from jobscout.models import Alert, Job, JobDetails, JobRef, JobScore
from jobscout.parse import parse_alert_html
from jobscout.sources import FolderSource


class JobStore:
    """Persisted alerts and everything learned about each job."""

    def __init__(self, root: Path = DATA_DIR):
        """Open a store. Folders are created lazily on first write.

        Args:
            root: Directory holding the store's folders.
        """
        self._inbox = root / "emails"
        self._samples = root / "samples"
        self._details = root / "jobs"
        self._scores = root / "scores"

    # --- alerts -------------------------------------------------------------------

    def add_alert(self, alert: Alert) -> bool:
        """Save an alert unless it is already stored.

        Args:
            alert: The alert email to save.

        Returns:
            True if the alert was new, False if it was already stored.
        """
        path = self._inbox / f"{alert.id}.html"
        if path.exists():
            return False
        self._inbox.mkdir(parents=True, exist_ok=True)
        path.write_text(alert.html, encoding="utf-8")
        return True

    # --- queries ------------------------------------------------------------------

    def jobs(self) -> list[Job]:
        """List every known job with what is known about it.

        Returns:
            Jobs deduplicated across alerts, in first-seen order.
        """
        return [
            Job(
                ref,
                self._read(self._details, ref.job_id, JobDetails),
                self._read(self._scores, ref.job_id, JobScore),
            )
            for ref in self._refs()
        ]

    def needing_details(self) -> list[JobRef]:
        """List jobs whose page has not been fetched yet.

        Returns:
            Jobs without JobDetails, in first-seen order.
        """
        return [ref for ref in self._refs() if not (self._details / f"{ref.job_id}.json").exists()]

    def needing_score(self, prompt_hash: str) -> list[JobDetails]:
        """List jobs that have details but no score from the current prompt.

        Args:
            prompt_hash: The Scorer's current prompt hash; scores with another hash are stale.

        Returns:
            Details of jobs that are unscored or stale, in first-seen order.
        """
        return [
            job.details
            for job in self.jobs()
            if job.details and not (job.score and job.score.prompt_hash == prompt_hash)
        ]

    # --- writes -------------------------------------------------------------------

    def save_details(self, details: JobDetails) -> None:
        """Store a job's details, replacing any earlier ones.

        Args:
            details: The job's details.
        """
        self._write(self._details, details.job_id, details)

    def save_score(self, score: JobScore) -> None:
        """Store a job's score, replacing any earlier one.

        Args:
            score: The job's score.
        """
        self._write(self._scores, score.job_id, score)

    # --- implementation -----------------------------------------------------------

    def _refs(self) -> list[JobRef]:
        """Parse all stored alerts into unique job references.

        Returns:
            Jobs deduplicated by job id, in first-seen order.
        """
        refs: dict[str, JobRef] = {}
        for alert in FolderSource(self._inbox, self._samples).alerts():
            for ref in parse_alert_html(alert.html):
                refs.setdefault(ref.job_id, ref)
        return list(refs.values())

    @staticmethod
    def _read[T](folder: Path, job_id: str, cls: type[T]) -> T | None:
        """Load one job's JSON record.

        Args:
            folder: Folder holding ``<job_id>.json`` files.
            job_id: Which job to load.
            cls: Dataclass to build from the JSON.

        Returns:
            The record, or None if the job has none.
        """
        path = folder / f"{job_id}.json"
        if not path.exists():
            return None
        return cls(**json.loads(path.read_text(encoding="utf-8")))

    @staticmethod
    def _write(folder: Path, job_id: str, obj: JobDetails | JobScore) -> None:
        """Save one job's JSON record.

        Args:
            folder: Folder holding ``<job_id>.json`` files.
            job_id: Which job the record belongs to.
            obj: The record.
        """
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{job_id}.json").write_text(
            json.dumps(asdict(obj), ensure_ascii=False, indent=2), encoding="utf-8"
        )
