"""Scorer: judge jobs against the CV + rubric with Claude.

Interface::

    scorer = Scorer(client, cv, rubric, model=..., effort=...)
    run = scorer.score(jobs)               # standard requests: instant, full price
    run = scorer.score(jobs, batch=True)   # Batch API: 50% off, minutes to hours
    run = scorer.collect(batch_id)         # pick up an earlier batch
    run.scores / run.failed / run.usage.cost

The client is injected: Anthropic() in production, a fake in tests. Nothing here touches disk.
"""

import hashlib
import json
import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import anthropic
from anthropic.types import Message
from anthropic.types import Usage as ApiUsage
from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
from anthropic.types.messages.batch_create_params import Request

from jobscout.models import JobDetails, JobScore

DEFAULT_MODEL = "claude-sonnet-5-5"
DEFAULT_EFFORT = "low"  # classification-style task; thinking tokens are billed as output
MAX_TOKENS = 4000
FALLBACK_BETA = "server-side-fallback-2026-07-01"


@dataclass(frozen=True)
class ModelProfile:
    """What the Scorer needs to know about one model.

    Attributes:
        price: Dollars per million tokens (standard tier) for input, output,
            cache_write and cache_read.
        supports_effort: Whether ``output_config.effort`` is accepted.
        supports_fallback: Whether server-side refusal fallback ("default" mode) is accepted.
    """

    price: dict[str, float]
    supports_effort: bool
    supports_fallback: bool


MODELS = {
    "claude-sonnet-5-5": ModelProfile(
        {"input": 2.00, "output": 10.00, "cache_write": 2.50, "cache_read": 0.20},
        supports_effort=True,
        supports_fallback=True,
    ),
    "claude-haiku-4-5": ModelProfile(
        {"input": 1.00, "output": 5.00, "cache_write": 1.25, "cache_read": 0.10},
        supports_effort=False,
        supports_fallback=False,
    ),
}

SCORE_SCHEMA = {
    "type": "object",
    "properties": {
        "score": {"type": "integer", "description": "0-10, using the rubric's score bands"},
        "verdict": {"type": "string", "enum": ["apply", "read", "skip"]},
        "matched_skills": {"type": "array", "items": {"type": "string"}},
        "gaps": {"type": "array", "items": {"type": "string"}},
        "dealbreakers_hit": {"type": "array", "items": {"type": "string"}},
        "reasoning": {"type": "string", "description": "2-3 sentences, cite the posting"},
    },
    "required": ["score", "verdict", "matched_skills", "gaps", "dealbreakers_hit", "reasoning"],
    "additionalProperties": False,
}

INSTRUCTIONS = """\
You screen job postings for one specific candidate. For each posting, judge how well it fits
the candidate's CV *and* their stated preferences in the rubric, then return the JSON result.

How to judge:
- The rubric is the candidate's own priorities. It overrides your general opinion of a job.
- Base every claim on the posting text. If the posting doesn't say something (remote policy,
  seniority, stack), treat it as unknown rather than guessing; mention important unknowns in gaps.
- A title can mislead: "Senior" with junior responsibilities, or "Engineer" with lead scope.
  Judge by responsibilities and requirements, not the title alone.
- The LinkedIn "Seniority level" field is often wrong; trust the posting body over it.
- If any rubric dealbreaker applies, list it in dealbreakers_hit and keep the score in 0-3.
- verdict: "apply" for 9-10, "read" for 7-8, "skip" for 0-6.
- Be concise: reasoning is 2-3 sentences for a busy reader deciding whether to open the link."""


def _zero_tokens() -> dict[str, int]:
    """Start a token tally.

    Returns:
        Zero counts for input, output, cache_write and cache_read.
    """
    return dict.fromkeys(("input", "output", "cache_write", "cache_read"), 0)


@dataclass
class Usage:
    """Token tally and dollar cost for one scoring run.

    Attributes:
        price: Dollars per million tokens, from the model's profile.
        discount: 0.5 for the Batch API, 1.0 otherwise.
        tokens: Running counts for input, output, cache_write and cache_read.
    """

    price: dict[str, float]
    discount: float = 1.0
    tokens: dict[str, int] = field(default_factory=_zero_tokens)

    def add(self, usage: ApiUsage) -> None:
        """Add one response's token usage to the tally.

        Args:
            usage: The ``usage`` field of an API response.
        """
        self.tokens["input"] += usage.input_tokens
        self.tokens["output"] += usage.output_tokens
        self.tokens["cache_write"] += usage.cache_creation_input_tokens or 0
        self.tokens["cache_read"] += usage.cache_read_input_tokens or 0

    @property
    def cost(self) -> float:
        """Dollars spent so far, after the batch discount."""
        return sum(n * self.price[k] for k, n in self.tokens.items()) / 1e6 * self.discount

    def __str__(self) -> str:
        """Summarise tokens and cost on one line.

        Returns:
            E.g. ``tokens: in=1000 out=200 cache_write=0 cache_read=3000  ->  $0.0046``.
        """
        t = self.tokens
        return (
            f"tokens: in={t['input']} out={t['output']} cache_write={t['cache_write']} "
            f"cache_read={t['cache_read']}  ->  ${self.cost:.4f}"
        )


@dataclass
class ScoreRun:
    """Outcome of one scoring run.

    Attributes:
        usage: Tokens and cost.
        scores: Validated scores.
        failed: ``(job_id, reason)`` for jobs that got no valid score.
        batch_id: The batch's id, for batch runs.
    """

    usage: Usage
    scores: list[JobScore] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)
    batch_id: str | None = None


class Scorer:
    """Judges jobs against a CV and rubric with one Claude call per job."""

    def __init__(
        self,
        client: anthropic.Anthropic,
        cv: str,
        rubric: str,
        *,
        model: str = DEFAULT_MODEL,
        effort: str = DEFAULT_EFFORT,
        poll_seconds: float = 30,
        sleep: Callable[[float], None] = time.sleep,
    ):
        """Create a scorer.

        Args:
            client: Anthropic client (or a fake with the same shape).
            cv: The candidate's CV as text.
            rubric: The candidate's priorities and score bands as text.
            model: A key of ``MODELS``.
            effort: Thinking effort; ignored for models that don't support it.
            poll_seconds: Wait between batch status checks.
            sleep: Called to wait between batch status checks.

        Raises:
            ValueError: If the model has no profile in ``MODELS``.
        """
        if model not in MODELS:
            raise ValueError(f"Unknown model {model!r}; add its prices to MODELS")
        self._client = client
        self._model = model
        self._profile = MODELS[model]
        self._effort = effort if self._profile.supports_effort else None
        self._poll_seconds = poll_seconds
        self._sleep = sleep
        # Stable prefix: identical bytes on every call, so it can be cached.
        self._system = f"{INSTRUCTIONS}\n\n<rubric>\n{rubric}\n</rubric>\n\n<cv>\n{cv}\n</cv>"

    @property
    def prompt_hash(self) -> str:
        """Fingerprint of model, effort, prompt, CV, rubric and schema.

        Scores stamped with a different hash are stale.
        """
        key = json.dumps([self._model, self._effort, self._system, SCORE_SCHEMA], sort_keys=True)
        return hashlib.sha256(key.encode()).hexdigest()[:12]

    def score(
        self,
        jobs: list[JobDetails],
        batch: bool = False,
        on_submit: Callable[[str], None] | None = None,
    ) -> ScoreRun:
        """Score jobs.

        Args:
            jobs: Jobs to score.
            batch: Use the Batch API (half price, waits for completion) instead of
                one standard request per job.
            on_submit: Called with the batch id right after submission, so the
                caller can record it for ``collect`` if the wait is interrupted.

        Returns:
            Scores, failures and usage. API errors and invalid responses become
            failures rather than exceptions.
        """
        if batch:
            batch_obj = self._client.messages.batches.create(
                requests=[Request(custom_id=job.job_id, params=self._params(job)) for job in jobs]
            )
            if on_submit:
                on_submit(batch_obj.id)
            return self.collect(batch_obj.id)

        run = ScoreRun(Usage(self._profile.price))
        for job in jobs:
            try:
                message = self._client.messages.create(**self._params(job), **self._fallback())
            except (anthropic.APIStatusError, anthropic.APIConnectionError) as e:
                run.failed.append((job.job_id, str(e)))
                continue
            run.usage.add(message.usage)
            self._record(run, job.job_id, message)
        return run

    def collect(self, batch_id: str) -> ScoreRun:
        """Wait for a batch to end and read its results.

        Args:
            batch_id: Id returned when the batch was submitted.

        Returns:
            Scores, failures and usage (at the batch discount).
        """
        while self._client.messages.batches.retrieve(batch_id).processing_status != "ended":
            self._sleep(self._poll_seconds)
        run = ScoreRun(Usage(self._profile.price, discount=0.5), batch_id=batch_id)
        # Results come back in any order: key by custom_id, never by position.
        for result in self._client.messages.batches.results(batch_id):
            if result.result.type != "succeeded":
                run.failed.append((result.custom_id, result.result.type))
                continue
            run.usage.add(result.result.message.usage)
            self._record(run, result.custom_id, result.result.message)
        return run

    # --- implementation -----------------------------------------------------------

    def _params(self, job: JobDetails) -> MessageCreateParamsNonStreaming:
        """Build the request body for one job; shared by standard and batch requests.

        Args:
            job: The job to score.

        Returns:
            Messages API parameters.
        """
        output_config: Any = {"format": {"type": "json_schema", "schema": SCORE_SCHEMA}}
        if self._effort:
            output_config["effort"] = self._effort
        return {
            "model": self._model,
            "max_tokens": MAX_TOKENS,
            "system": [
                {"type": "text", "text": self._system, "cache_control": {"type": "ephemeral"}}
            ],
            "messages": [{"role": "user", "content": _format_job(job)}],
            "output_config": output_config,
        }

    def _fallback(self) -> dict[str, Any]:
        """Extra request options for server-side refusal fallback.

        Standard requests only: the Batch API rejects the ``fallbacks`` parameter.

        Returns:
            ``extra_headers`` / ``extra_body`` kwargs, or {} if the model doesn't support it.
        """
        if not self._profile.supports_fallback:
            return {}
        return {
            "extra_headers": {"anthropic-beta": FALLBACK_BETA},
            "extra_body": {"fallbacks": "default"},
        }

    def _record(self, run: ScoreRun, job_id: str, message: Message) -> None:
        """Add a response to the run as a score, or as a failure if it is invalid.

        Args:
            run: The run to update.
            job_id: Which job the response is for.
            message: The API response.
        """
        try:
            run.scores.append(self._to_score(job_id, message))
        except ValueError as e:
            run.failed.append((job_id, str(e)))

    def _to_score(self, job_id: str, message: Message) -> JobScore:
        """Validate a response and turn it into a JobScore.

        Args:
            job_id: Which job the response is for.
            message: The API response.

        Returns:
            The score, stamped with the current prompt hash.

        Raises:
            ValueError: If the model refused, was cut off, or returned invalid output.
        """
        if message.stop_reason == "refusal":
            raise ValueError(f"refused: {message.stop_details}")
        if message.stop_reason == "max_tokens":
            raise ValueError("hit max_tokens; raise MAX_TOKENS")
        text = next((b.text for b in message.content if b.type == "text"), None)
        if text is None:
            raise ValueError("no text block in response")
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(f"invalid JSON: {e}") from e
        if not 0 <= data.get("score", -1) <= 10:
            raise ValueError(f"score out of range: {data.get('score')}")
        return JobScore(job_id=job_id, prompt_hash=self.prompt_hash, **data)


def _format_job(job: JobDetails) -> str:
    """Render a job as the user message.

    Args:
        job: The job to describe.

    Returns:
        The job wrapped in ``<posting>`` tags.
    """
    criteria = "\n".join(f"- {k}: {v}" for k, v in job.criteria.items()) or "- (none listed)"
    description = job.description or "(No description available: judge from title/company only.)"
    return (
        f"<posting>\nTitle: {job.title}\nCompany: {job.company}\nLocation: {job.location}\n"
        f"LinkedIn criteria:\n{criteria}\n\nDescription:\n{description}\n</posting>"
    )


def make_client() -> anthropic.Anthropic:
    """Build the production Anthropic client from the environment.

    Reads ``ANTHROPIC_API_KEY``, and ``ANTHROPIC_WORKSPACE_ID`` when the key was
    created at org level rather than inside a workspace.

    Returns:
        A configured client.
    """
    workspace = os.environ.get("ANTHROPIC_WORKSPACE_ID")
    return anthropic.Anthropic(
        default_headers={"anthropic-workspace-id": workspace} if workspace else None
    )
