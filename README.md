# JobScout

Ranks LinkedIn job-alert emails against your CV with Claude.

```
Outlook alerts ──► parse jobs ──► fetch public job pages ──► score with Claude ──► data/report.md
 (Microsoft Graph)  (dedupe by job_id)  (capped, cached)       (CV + rubric)        (ranked)
```

Each job gets a 0-10 score and a verdict: **9-10 apply**, **7-8 read**, **0-6 skip**.
Scoring follows your own [rubric](data/rubric.md), which overrides the model's general opinion.
Domain terms are defined in [CONTEXT.md](CONTEXT.md).

## Requirements

- Python 3.14+
- An Anthropic API key
- A personal Microsoft account (outlook.com / hotmail) that receives LinkedIn job alerts
- An Azure app registration for reading that mailbox (see below)

## Setup

```sh
python -m venv .venv
.venv\Scripts\activate          # Windows; use `source .venv/bin/activate` elsewhere
pip install -r requirements.txt
copy .env.example .env          # then fill it in
```

### `.env`

| Variable | Purpose |
|---|---|
| `MS_CLIENT_ID` | Application (client) ID of your Azure app registration |
| `MS_AUTHORITY` | Leave as `https://login.microsoftonline.com/consumers` for personal accounts |
| `ANTHROPIC_API_KEY` | Your Anthropic API key |
| `ANTHROPIC_WORKSPACE_ID` | Only if the key was created at org level (error: "not scoped to a workspace") |

### Azure app registration

1. In the Azure portal, register an app with **Personal Microsoft accounts only**.
2. Under **Authentication**, enable **Allow public client flows** (needed for device-code sign-in).
3. Under **API permissions**, add Microsoft Graph delegated permission `Mail.Read`.
4. Copy the Application (client) ID into `MS_CLIENT_ID`.

### Your CV and rubric

- Put your CV as Markdown in `data/cv.md` (git-ignored).
- Edit `data/rubric.md`: target role, dealbreakers, positives, bonuses, score bands.
  The rubric is part of the prompt, so changing it re-scores every job on the next run.

### Sign in once

```sh
python -m jobscout login
```

This runs the device-code flow and caches a refresh token in `.token_cache.json`.
Later runs never prompt, so they are safe to schedule.

## Usage

```sh
python -m jobscout run                 # fetch → enrich → score → report
python -m jobscout run --batch         # same, scoring via the Batch API (50% off, async)
```

| Command | What it does |
|---|---|
| `login` | One-time Outlook sign-in (device code) |
| `run [--batch] [--limit N] [--days D] [--model M]` | Whole pipeline |
| `fetch [--days D]` | Pull alert emails from Outlook (default: last 14 days) |
| `jobs` | List known jobs and how far each has got |
| `enrich [--max N]` | Fetch public job pages (default cap: 40 per run) |
| `score [--batch] [--limit N] [--model M]` | Score jobs that are unscored or stale |
| `resume BATCH_ID` | Collect an earlier batch (Ctrl+C while waiting is safe) |
| `report` | Write `data/report.md` and print the top 10 |

Models: `claude-sonnet-5-5` (default) or `claude-haiku-4-5`. Each run prints token usage and cost.

`fetch` and `run` exit with code 1 when the Outlook sign-in has expired or the mailbox can't be read
(network error, Graph error, persistent throttling), so a scheduler can flag it; `run` still carries on
with already-stored alerts. For an expired sign-in, run `login` again.

### Without Outlook

Drop alert emails as `.eml`, `.msg` or `.html` files into `data/samples/`. They are read alongside
fetched alerts, so `enrich`, `score` and `report` work without a mailbox.

## How it behaves

- **Deduplication**: the same job appears in many alerts; it is stored once, keyed by LinkedIn `job_id`.
- **Polite enrichment**: job pages are fetched with a 3-7 s random delay, at most 40 per run,
  cached on disk, and fetching stops as soon as LinkedIn answers 429/999. Try again the next day.
- **Incremental scoring**: each score records a hash of model, effort, instructions, CV, rubric and
  schema. Only unscored jobs, or jobs whose hash no longer matches, are sent to Claude.

## Data and privacy

Everything lives under `data/`. Only `data/rubric.md` is tracked in git. Kept out of git:

| Path | Contents |
|---|---|
| `.env` | API keys |
| `.token_cache.json` | Refresh token for your mailbox. Treat it like a password |
| `data/cv.md` | Your CV |
| `data/emails/`, `data/samples/` | Alert emails (their links carry LinkedIn auth tokens) |
| `data/jobs/`, `data/scores/`, `data/report.md` | Cached job pages, scores, report |

## Development

```sh
pip install pytest ruff
pytest
ruff check .
```

Tests run offline; they don't call Outlook, LinkedIn or the Anthropic API.
