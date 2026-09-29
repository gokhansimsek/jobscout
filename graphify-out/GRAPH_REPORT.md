# Graph Report - JobScout  (2026-09-29)

## Corpus Check
- Corpus is ~7,471 words - fits in a single context window. You may not need a graph.

## Summary
- 269 nodes · 497 edges · 13 communities (10 shown, 3 thin omitted)
- Extraction: 90% EXTRACTED · 10% INFERRED · 0% AMBIGUOUS · INFERRED: 51 edges (avg confidence: 0.91)
- Token cost: 56,532 input · 0 output

## Community Hubs (Navigation)
- Domain Glossary & Rubric
- CLI Commands & Config
- Claude Scorer & Cost
- Job Page Enrichment
- Domain Models & Alert Source
- Alert Parsing & Job Refs
- Scorer Tests
- Ranked Report
- Job Store Persistence
- Alert File Readers
- Package Init
- Package Root
- Offline Test Tooling

## God Nodes (most connected - your core abstractions)
1. `JobStore` - 31 edges
2. `Alert` - 19 edges
3. `JobDetails` - 19 edges
4. `enrich()` - 17 edges
5. `Scorer` - 16 edges
6. `FakeClient` - 13 edges
7. `JobScore` - 12 edges
8. `main()` - 11 edges
9. `JobRef` - 11 edges
10. `alert_html()` - 11 edges

## Surprising Connections (you probably didn't know these)
- `Incremental scoring` --semantically_similar_to--> `Prompt hash`  [INFERRED] [semantically similar]
  README.md → CONTEXT.md
- `Microsoft Graph (Outlook mail)` --semantically_similar_to--> `Graph adapter (Outlook.com mailbox)`  [INFERRED] [semantically similar]
  README.md → CONTEXT.md
- `data/samples offline alerts` --semantically_similar_to--> `Folder adapter (files on disk)`  [INFERRED] [semantically similar]
  README.md → CONTEXT.md
- `Rubric score bands (9-10, 7-8, 4-6, 0-3)` --semantically_similar_to--> `Score bands`  [INFERRED] [semantically similar]
  data/rubric.md → CONTEXT.md
- `Deduplication by job_id` --rationale_for--> `Job`  [INFERRED]
  README.md → CONTEXT.md

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Job knowledge stages (JobRef -> JobDetails -> JobScore)** — context_job, context_jobref, context_jobdetails, context_jobscore, context_job_store [EXTRACTED 1.00]
- **Scoring prompt inputs fingerprinted by prompt hash** — context_scorer, context_cv, context_rubric, context_prompt_hash, readme_claude_models [INFERRED 0.85]
- **Rubric scoring rules** — data_rubric_dealbreakers, data_rubric_strong_positives, data_rubric_bonuses, data_rubric_mild_negatives, data_rubric_score_bands [EXTRACTED 1.00]

## Communities (13 total, 3 thin omitted)

### Community 0 - "Domain Glossary & Rubric"
Cohesion: 0.06
Nodes (46): CONTEXT.md (JobScout domain glossary), Alert, Alert source, CV, Enrichment, Folder adapter (files on disk), Graph adapter (Outlook.com mailbox), Job (+38 more)

### Community 1 - "CLI Commands & Config"
Cohesion: 0.07
Nodes (40): Project paths and process setup shared by the CLI., Prepare the process for a CLI run. Loads ``.env`` into the environment and…, setup(), cmd_enrich(), cmd_fetch(), cmd_jobs(), cmd_login(), cmd_report() (+32 more)

### Community 2 - "Claude Scorer & Cost"
Cohesion: 0.07
Nodes (31): Anthropic, Any, ApiUsage, JobScore, The LLM's judgment of one job (stage 3). Fields match ``SCORE_SCHEMA`` in…, _format_job(), ModelProfile, Scorer: judge jobs against the CV + rubric with Claude. Interface:: scorer =… (+23 more)

### Community 3 - "Job Page Enrichment"
Cohesion: 0.11
Nodes (29): Exception, fixture, enrich(), EnrichResult, FetchError, http_getter(), get(), _parse_job_page() (+21 more)

### Community 4 - "Domain Models & Alert Source"
Cohesion: 0.16
Nodes (18): Alert, JobDetails, Domain types shared by every stage of the pipeline. Funnel: Alert (email) ->…, One LinkedIn job-alert email. Attributes: id: Stable per email and safe to use…, What the public job page adds (stage 2). Attributes: job_id: LinkedIn's numeric…, AlertSource, Anything that can list LinkedIn alert emails., List the available alert emails. Returns: The alerts, each with a stable,… (+10 more)

### Community 5 - "Alert Parsing & Job Refs"
Cohesion: 0.14
Nodes (14): JobRef, What an alert email tells us about a job (stage 1 of the funnel). Attributes:…, Canonical job page URL, without the email's tracking parameters., parse_alert_html(), Turn alert-email HTML into JobRef objects. Pure: no I/O., Extract the jobs listed in one alert email. Each job appears in several links;…, FolderSource, Read every .eml, .msg and .html file; other files are ignored. Yields: One… (+6 more)

### Community 6 - "Scorer Tests"
Cohesion: 0.24
Nodes (11): parametrize, FakeClient, message(), Stands in for anthropic.Anthropic at the Scorer's seam., scorer(), test_bad_responses_become_failures_not_crashes(), test_batch_polls_until_ended_and_halves_cost(), test_haiku_request_omits_unsupported_options() (+3 more)

### Community 7 - "Ranked Report"
Cohesion: 0.19
Nodes (10): date, Job, Everything known about one job so far, as returned by the Job store.…, ranked(), Render scored jobs as a ranked markdown report. Pure: no I/O., Render the ranked report. Args: jobs: Jobs as returned by the Job store;…, Keep the scored jobs and sort them best first. Args: jobs: Jobs as returned by…, render_report() (+2 more)

### Community 8 - "Job Store Persistence"
Cohesion: 0.17
Nodes (7): Path, Store a job's score, replacing any earlier one. Args: score: The job's score., Load one job's JSON record. Args: folder: Folder holding ``<job_id>.json``…, Save one job's JSON record. Args: folder: Folder holding ``<job_id>.json``…, Open a store. Folders are created lazily on first write. Args: root: Directory…, Store a job's details, replacing any earlier ones. Args: details: The job's…, T

### Community 9 - "Alert File Readers"
Cohesion: 0.22
Nodes (8): _html_from_eml(), _html_from_html(), _html_from_msg(), Path, Create a source over the given folders. Args: *dirs: Folders to read, in order.…, Read the HTML part of a .eml file. Args: path: The .eml file. Returns: The HTML…, Read the HTML body of an Outlook .msg file. Args: path: The .msg file. Returns:…, Read a saved .html alert. Args: path: The .html file. Returns: The file's…

## Knowledge Gaps
- **12 isolated node(s):** `jobscout`, `CONTEXT.md (JobScout domain glossary)`, `data/report.md ranked report`, `Claude models (claude-sonnet-5-5, claude-haiku-4-5)`, `Offline tests (pytest, ruff)` (+7 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 118 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **3 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `JobStore` connect `CLI Commands & Config` to `Claude Scorer & Cost`, `Job Page Enrichment`, `Domain Models & Alert Source`, `Alert Parsing & Job Refs`, `Ranked Report`, `Job Store Persistence`?**
  _High betweenness centrality (0.154) - this node is a cross-community bridge._
- **Why does `JobDetails` connect `Domain Models & Alert Source` to `CLI Commands & Config`, `Claude Scorer & Cost`, `Job Page Enrichment`, `Alert Parsing & Job Refs`, `Scorer Tests`, `Ranked Report`, `Job Store Persistence`?**
  _High betweenness centrality (0.098) - this node is a cross-community bridge._
- **Why does `Scorer` connect `Claude Scorer & Cost` to `CLI Commands & Config`, `Domain Models & Alert Source`, `Scorer Tests`?**
  _High betweenness centrality (0.082) - this node is a cross-community bridge._
- **Are the 14 inferred relationships involving `JobStore` (e.g. with `enrich()` and `cmd_enrich()`) actually correct?**
  _`JobStore` has 14 INFERRED edges - model-reasoned connections that need verification._
- **Are the 4 inferred relationships involving `Alert` (e.g. with `AlertSource` and `FolderSource`) actually correct?**
  _`Alert` has 4 INFERRED edges - model-reasoned connections that need verification._
- **Are the 4 inferred relationships involving `JobDetails` (e.g. with `EnrichResult` and `_format_job()`) actually correct?**
  _`JobDetails` has 4 INFERRED edges - model-reasoned connections that need verification._
- **Are the 2 inferred relationships involving `Scorer` (e.g. with `JobDetails` and `JobScore`) actually correct?**
  _`Scorer` has 2 INFERRED edges - model-reasoned connections that need verification._