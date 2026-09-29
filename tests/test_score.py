import dataclasses
import json
from types import SimpleNamespace as NS
from typing import Any, cast

import anthropic
import pytest

from jobscout.models import JobDetails, JobScore
from jobscout.score import SCORE_SCHEMA, Scorer

JOB = JobDetails("1", "Senior Backend", "Acme", "İzmir", "Python, FastAPI, AWS")
JOB2 = JobDetails("2", "Data Engineer", "Beta", "Remote", "Python, Spark")
# The Scorer only reads the message; the request would need the SDK's own HTTP library.
CONNECTION_ERROR = anthropic.APIConnectionError(request=cast(Any, None))
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
    """Stands in for anthropic.Anthropic at the Scorer's seam.

    Responses are consumed in order. An exception is raised instead of returned;
    in batch results, a string is a non-succeeded result type (e.g. "expired").
    """

    def __init__(self, *responses, batch_polls: int = 0, reverse_results: bool = False):
        self.responses = list(responses)
        self.calls: list[dict] = []
        self.polls_left = batch_polls
        self.reverse_results = reverse_results
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
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def _batch_create(self, requests):
        self.batch_requests = requests
        return NS(id="batch_1")

    def _retrieve(self, batch_id):
        self.polls_left -= 1
        return NS(processing_status="ended" if self.polls_left < 0 else "in_progress")

    def _results(self, batch_id):
        # Pair each request with its response in submission order, then optionally
        # reverse: the real API returns results in any order.
        pairs = [(r["custom_id"], self.responses.pop(0)) for r in self.batch_requests]
        if self.reverse_results:
            pairs.reverse()
        return [
            NS(
                custom_id=custom_id,
                result=NS(type=response)
                if isinstance(response, str)
                else NS(type="succeeded", message=response),
            )
            for custom_id, response in pairs
        ]


def scorer(client, model="claude-sonnet-5-5", rubric="Senior Python only", sleep=lambda s: None):
    return Scorer(client, cv="Python dev, 15 years", rubric=rubric, model=model, sleep=sleep)


def test_score_schema_matches_jobscore_fields():
    # The model fills everything except what the Scorer stamps on itself.
    fields = {f.name for f in dataclasses.fields(JobScore)} - {"job_id", "prompt_hash"}

    assert set(SCORE_SCHEMA["properties"]) == fields
    assert set(SCORE_SCHEMA["required"]) == fields


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


def test_api_errors_become_failures_and_the_run_continues():
    run = scorer(FakeClient(CONNECTION_ERROR, message())).score([JOB, JOB2])

    assert run.failed == [("1", "Connection error.")]
    assert [s.job_id for s in run.scores] == ["2"]


def test_batch_results_are_matched_by_custom_id_not_position():
    client = FakeClient(
        message({**GOOD, "score": 9}), message({**GOOD, "score": 3}), reverse_results=True
    )

    run = scorer(client).score([JOB, JOB2], batch=True)

    assert {s.job_id: s.score for s in run.scores} == {"1": 9, "2": 3}


def test_unsuccessful_batch_results_become_failures():
    run = scorer(FakeClient("expired", message())).score([JOB, JOB2], batch=True)

    assert run.failed == [("1", "expired")]
    assert [s.job_id for s in run.scores] == ["2"]
    assert run.usage.cost == pytest.approx((2000 + 2000 + 600) / 1e6 / 2)  # only job 2 billed


def test_interrupted_batch_can_be_collected_by_a_new_scorer():
    client = FakeClient(message())

    def interrupt(batch_id):
        raise KeyboardInterrupt  # the user stops waiting right after submission

    with pytest.raises(KeyboardInterrupt):
        scorer(client).score([JOB], batch=True, on_submit=interrupt)
    run = scorer(client).collect("batch_1")

    assert run.batch_id == "batch_1"
    assert [s.job_id for s in run.scores] == ["1"]


def test_collected_scores_keep_the_hash_they_were_submitted_with():
    client = FakeClient(message())
    submitter = scorer(client, rubric="Senior Python only")
    submitter.score([JOB], batch=True, on_submit=lambda batch_id: None)
    client.responses.append(message())  # the same batch, collected again

    # The rubric was edited before resuming: these scores came from the old prompt.
    run = scorer(client, rubric="Remote only").collect("batch_1")

    assert run.scores[0].job_id == "1"
    assert run.scores[0].prompt_hash == submitter.prompt_hash


def test_batch_submitted_before_custom_id_carried_the_hash_uses_the_current_one():
    client = FakeClient(message())
    client.batch_requests = [{"custom_id": "1"}]  # the old format: bare job id
    s = scorer(client)

    run = s.collect("batch_1")

    assert run.scores[0].job_id == "1"
    assert run.scores[0].prompt_hash == s.prompt_hash
