import json
from types import SimpleNamespace as NS

import pytest

from jobscout.models import JobDetails
from jobscout.score import Scorer

JOB = JobDetails("1", "Senior Backend", "Acme", "İzmir", "Python, FastAPI, AWS")
GOOD = {
    "score": 9,
    "verdict": "apply",
    "matched_skills": ["Python"],
    "gaps": [],
    "dealbreakers_hit": [],
    "reasoning": "Fits.",
}


def message(payload=GOOD, stop_reason="end_turn"):
    text = payload if isinstance(payload, str) else json.dumps(payload)
    return NS(
        stop_reason=stop_reason,
        stop_details=None,
        content=[NS(type="thinking", thinking=""), NS(type="text", text=text)],
        usage=NS(
            input_tokens=1000,
            output_tokens=200,
            cache_creation_input_tokens=0,
            cache_read_input_tokens=3000,
        ),
    )


class FakeClient:
    """Stands in for anthropic.Anthropic at the Scorer's seam."""

    def __init__(self, *responses, batch_polls: int = 0):
        self.responses = list(responses)
        self.calls: list[dict] = []
        self.polls_left = batch_polls
        self.messages = NS(
            create=self._create,
            batches=NS(
                create=self._batch_create,
                retrieve=self._retrieve,
                results=self._results,
            ),
        )

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)

    def _batch_create(self, requests):
        self.batch_requests = requests
        return NS(id="batch_1")

    def _retrieve(self, batch_id):
        self.polls_left -= 1
        return NS(processing_status="ended" if self.polls_left < 0 else "in_progress")

    def _results(self, batch_id):
        return [
            NS(
                custom_id=r["custom_id"],
                result=NS(type="succeeded", message=self.responses.pop(0)),
            )
            for r in self.batch_requests
        ]


def scorer(client, model="claude-sonnet-5-5", rubric="Senior Python only", sleep=lambda s: None):
    return Scorer(client, cv="Python dev, 15 years", rubric=rubric, model=model, sleep=sleep)


def test_scores_are_validated_stamped_and_costed():
    s = scorer(FakeClient(message()))

    run = s.score([JOB])

    assert run.failed == []
    assert run.scores[0].score == 9 and run.scores[0].prompt_hash == s.prompt_hash
    # sonnet: 1000*2 + 200*10 + 3000*0.20 per MTok
    assert run.usage.cost == pytest.approx((2000 + 2000 + 600) / 1e6)


@pytest.mark.parametrize(
    "response, reason",
    [
        (message(stop_reason="refusal"), "refused"),
        (message(stop_reason="max_tokens"), "max_tokens"),
        (message(payload="not json"), "invalid JSON"),
        (message(payload={**GOOD, "score": 11}), "out of range"),
    ],
)
def test_bad_responses_become_failures_not_crashes(response, reason):
    run = scorer(FakeClient(response)).score([JOB])

    assert run.scores == []
    assert run.failed[0][0] == "1" and reason in run.failed[0][1]


def test_sonnet_request_uses_effort_and_refusal_fallback():
    client = FakeClient(message())

    scorer(client).score([JOB])

    call = client.calls[0]
    assert call["output_config"]["effort"] == "low"
    assert call["extra_body"] == {"fallbacks": "default"}
    assert call["extra_headers"] == {"anthropic-beta": "server-side-fallback-2026-07-01"}
    assert "cache_control" in call["system"][0]


def test_haiku_request_omits_unsupported_options():
    client = FakeClient(message())

    scorer(client, model="claude-haiku-4-5").score([JOB])

    call = client.calls[0]
    assert "effort" not in call["output_config"]
    assert "extra_body" not in call


def test_prompt_hash_changes_with_rubric_and_model():
    base = scorer(FakeClient()).prompt_hash

    assert scorer(FakeClient(), rubric="Remote only").prompt_hash != base
    assert scorer(FakeClient(), model="claude-haiku-4-5").prompt_hash != base
    assert scorer(FakeClient()).prompt_hash == base


def test_batch_polls_until_ended_and_halves_cost():
    client = FakeClient(message(), batch_polls=2)
    sleeps, submitted = [], []

    run = scorer(client, sleep=sleeps.append).score([JOB], batch=True, on_submit=submitted.append)

    assert submitted == ["batch_1"] and run.batch_id == "batch_1"
    assert len(sleeps) == 2
    assert run.scores[0].job_id == "1"
    assert "fallbacks" not in client.batch_requests[0]["params"]  # rejected by the Batch API
    assert run.usage.cost == pytest.approx((2000 + 2000 + 600) / 1e6 / 2)
