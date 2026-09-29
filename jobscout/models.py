"""Domain types shared by every stage of the pipeline.

Funnel: Alert (email) -> JobRef -> JobDetails (job page) -> JobScore (LLM judgment).
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Alert:
    """One LinkedIn job-alert email.

    Attributes:
        id: Stable per email and safe to use as a filename.
        html: The email's HTML body.
    """

    id: str
    html: str


@dataclass(frozen=True)
class JobRef:
    """What an alert email tells us about a job (stage 1 of the funnel).

    Attributes:
        job_id: LinkedIn's numeric job id, from ``/jobs/view/<id>``.
        title: Job title as shown in the email.
        company: Company name.
        location: Location text, e.g. "İzmir, Türkiye".
        flags: Card extras such as "Easy Apply" or "Actively recruiting".
    """

    job_id: str
    title: str
    company: str
    location: str
    flags: tuple[str, ...] = field(default=())

    @property
    def url(self) -> str:
        """Canonical job page URL, without the email's tracking parameters."""
        return f"https://www.linkedin.com/jobs/view/{self.job_id}/"


@dataclass(frozen=True)
class JobDetails:
    """What the public job page adds (stage 2).

    Attributes:
        job_id: LinkedIn's numeric job id.
        title: Title from the job page, falling back to the email's.
        company: Company from the job page, falling back to the email's.
        location: Location from the job page, falling back to the email's.
        description: The "About the job" text; empty if the page had none.
        criteria: LinkedIn's criteria list, e.g. ``{"Seniority level": "Entry level"}``.
    """

    job_id: str
    title: str
    company: str
    location: str
    description: str
    criteria: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class JobScore:
    """The LLM's judgment of one job (stage 3). Fields match ``SCORE_SCHEMA`` in score.py.

    Attributes:
        job_id: LinkedIn's numeric job id.
        score: 0-10, using the score bands in ``data/rubric.md``.
        verdict: One of "apply", "read", "skip".
        matched_skills: CV skills the posting asks for.
        gaps: Requirements the CV lacks, and important unknowns.
        dealbreakers_hit: Rubric dealbreakers that apply.
        reasoning: 2-3 sentence justification citing the posting.
        prompt_hash: Which model and prompt produced this; a different hash means stale.
    """

    job_id: str
    score: int
    verdict: str
    matched_skills: list[str]
    gaps: list[str]
    dealbreakers_hit: list[str]
    reasoning: str
    prompt_hash: str


@dataclass(frozen=True)
class Job:
    """Everything known about one job so far, as returned by the Job store.

    Attributes:
        ref: What the alert email said.
        details: What the job page said, if fetched yet.
        score: The latest judgment, if scored yet (may be stale).
    """

    ref: JobRef
    details: JobDetails | None = None
    score: JobScore | None = None
