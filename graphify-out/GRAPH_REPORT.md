# Graph Report - JobScout  (2026-09-29)

## Corpus Check
- Corpus is ~9,221 words - fits in a single context window. You may not need a graph.

## Summary
- 308 nodes · 690 edges · 11 communities (9 shown, 2 thin omitted)
- Extraction: 88% EXTRACTED · 12% INFERRED · 0% AMBIGUOUS · INFERRED: 85 edges (avg confidence: 0.92)
- Token cost: 70,431 input · 0 output

## Community Hubs (Navigation)
- Claude Scorer & Tests
- CLI Commands & Config
- Domain Glossary & Docs
- Graph Adapter & Alert Parsing
- Job Page Enrichment
- Domain Models & AlertSource
- Folder Adapter & Dependencies
- Job Store Persistence
- Token Usage & Cost
- Package Init
- Project Metadata

## God Nodes (most connected - your core abstractions)
1. `JobStore` - 32 edges
2. `Alert` - 21 edges
3. `JobDetails` - 20 edges
4. `CONTEXT.md (domain glossary)` - 20 edges
5. `enrich()` - 19 edges
6. `FakeClient` - 19 edges
7. `Scorer` - 18 edges
8. `JobScore` - 15 edges
9. `GraphSource` - 14 edges
10. `scorer()` - 14 edges

## Surprising Connections (you probably didn't know these)
- `python-dotenv` --references--> `setup()`  [INFERRED]
  requirements.txt → jobscout/config.py
- `msal` --references--> `get_token()`  [INFERRED]
  requirements.txt → jobscout/sources.py
- `cmd_resume()` --implements--> `Batch API scoring (--batch, resume)`  [INFERRED]
  jobscout/__main__.py → README.md
- `main()` --implements--> `CLI commands (login, run, fetch, jobs, enrich, score, resume, report)`  [INFERRED]
  jobscout/__main__.py → README.md
- `JobScout pipeline (fetch -> enrich -> score -> report)` --references--> `main()`  [INFERRED]
  README.md → jobscout/__main__.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Job knowledge grows in stages (JobRef -> JobDetails -> JobScore)** — context_jobref, context_jobdetails, context_jobscore, context_enrichment, context_scorer [EXTRACTED 1.00]
- **Prompt hash inputs that trigger re-scoring** — context_prompt_hash, context_cv, context_rubric, context_stale_score [EXTRACTED 1.00]
- **Alert source adapters** — context_alert_source, context_graph_adapter, context_folder_adapter [EXTRACTED 1.00]

## Communities (11 total, 2 thin omitted)

### Community 0 - "Claude Scorer & Tests"
Cohesion: 0.06
Nodes (50): Anthropic, Any, JobScore, The LLM's judgment of one job (stage 3). Fields match ``SCORE_SCHEMA`` in…, _custom_id(), _format_job(), make_client(), ModelProfile (+42 more)

### Community 1 - "CLI Commands & Config"
Cohesion: 0.07
Nodes (44): date, Project paths and process setup shared by the CLI., Prepare the process for a CLI run. Loads ``.env`` into the environment and…, setup(), cmd_enrich(), cmd_fetch(), cmd_jobs(), cmd_login() (+36 more)

### Community 2 - "Domain Glossary & Docs"
Cohesion: 0.10
Nodes (40): CONTEXT.md (domain glossary), Alert, Alert source, CV, Dealbreaker, Enrichment, Folder adapter (files on disk), Graph adapter (Outlook.com mailbox) (+32 more)

### Community 3 - "Graph Adapter & Alert Parsing"
Cohesion: 0.09
Nodes (34): datetime, GraphGetter, parse_alert_html(), Turn alert-email HTML into JobRef objects. Pure: no I/O., Extract the jobs listed in one alert email. Each job appears in several links;…, AlertSourceError, graph_getter(), get() (+26 more)

### Community 4 - "Job Page Enrichment"
Cohesion: 0.11
Nodes (31): Exception, enrich(), EnrichResult, FetchError, http_getter(), get(), _parse_job_page(), Fetch each job's public LinkedIn page and extract "About the job". Interface:… (+23 more)

### Community 5 - "Domain Models & AlertSource"
Cohesion: 0.20
Nodes (16): Alert, Domain types shared by every stage of the pipeline. Funnel: Alert (email) ->…, One LinkedIn job-alert email. Attributes: id: Stable per email and safe to use…, AlertSource, Anything that can list LinkedIn alert emails., List the available alert emails. Returns: The alerts, each with a stable,…, Protocol, alert_html() (+8 more)

### Community 6 - "Folder Adapter & Dependencies"
Cohesion: 0.11
Nodes (16): FolderSource, _html_from_eml(), _html_from_html(), _html_from_msg(), Path, Create a source over the given folders. Args: *dirs: Folders to read, in order.…, Read every .eml, .msg and .html file; other files are ignored. Yields: One…, Read the HTML part of a .eml file. Args: path: The .eml file. Returns: The HTML… (+8 more)

### Community 7 - "Job Store Persistence"
Cohesion: 0.14
Nodes (12): fixture, JobStore, Path, Store a job's score, replacing any earlier one. Args: score: The job's score., Load one job's JSON record, tolerating records written by an older version.…, Save one job's JSON record. Args: folder: Folder holding ``<job_id>.json``…, Persisted alerts and everything learned about each job., Open a store. Folders are created lazily on first write. Args: root: Directory… (+4 more)

### Community 8 - "Token Usage & Cost"
Cohesion: 0.22
Nodes (6): ApiUsage, Token tally and dollar cost for one scoring run. Attributes: price: Dollars per…, Add one response's token usage to the tally. Args: usage: The ``usage`` field…, Dollars spent so far, after the batch discount., Summarise tokens and cost on one line. Returns: E.g. ``tokens: in=1000 out=200…, Usage

## Knowledge Gaps
- **6 isolated node(s):** `jobscout`, `Data and privacy (git-ignored data/ contents)`, `Target role: senior/lead Python backend`, `Strong positives`, `Neutral factors` (+1 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 121 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **2 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `JobStore` connect `Job Store Persistence` to `Claude Scorer & Tests`, `CLI Commands & Config`, `Domain Glossary & Docs`, `Job Page Enrichment`, `Domain Models & AlertSource`, `Folder Adapter & Dependencies`?**
  _High betweenness centrality (0.172) - this node is a cross-community bridge._
- **Why does `Scorer` connect `Claude Scorer & Tests` to `CLI Commands & Config`, `Domain Glossary & Docs`, `Job Page Enrichment`?**
  _High betweenness centrality (0.113) - this node is a cross-community bridge._
- **Why does `JobDetails` connect `Job Page Enrichment` to `Claude Scorer & Tests`, `CLI Commands & Config`, `Domain Glossary & Docs`, `Domain Models & AlertSource`, `Job Store Persistence`?**
  _High betweenness centrality (0.105) - this node is a cross-community bridge._
- **Are the 15 inferred relationships involving `JobStore` (e.g. with `enrich()` and `cmd_enrich()`) actually correct?**
  _`JobStore` has 15 INFERRED edges - model-reasoned connections that need verification._
- **Are the 5 inferred relationships involving `Alert` (e.g. with `Alert` and `AlertSource`) actually correct?**
  _`Alert` has 5 INFERRED edges - model-reasoned connections that need verification._
- **Are the 5 inferred relationships involving `JobDetails` (e.g. with `EnrichResult` and `JobDetails (stage 2)`) actually correct?**
  _`JobDetails` has 5 INFERRED edges - model-reasoned connections that need verification._
- **Are the 2 inferred relationships involving `enrich()` (e.g. with `Enrichment` and `JobStore`) actually correct?**
  _`enrich()` has 2 INFERRED edges - model-reasoned connections that need verification._