# JobScout: domain glossary

**Alert**: one LinkedIn job-alert email (sender `jobalerts-noreply@linkedin.com`). Contains several job cards: title, company, location, flags. No job description.

**Alert source**: where Alerts come from. Adapters: Graph (Outlook.com mailbox), Folder (files on disk).

**Job**: one LinkedIn posting, identified by its numeric `job_id` from `/jobs/view/<id>`. The same Job appears in many Alerts; it is always deduplicated by `job_id`. Knowledge about a Job grows in stages:
- **JobRef**: what an Alert says (stage 1).
- **JobDetails**: what the public job page adds: description and LinkedIn criteria (stage 2).
- **JobScore**: the Scorer's judgment (stage 3).

**Job store**: the single owner of all persisted Alerts and Job knowledge. Answers "which Jobs need details / a score".

**Enrichment**: fetching the public job page to turn a JobRef into JobDetails. Personal-scale only: capped, delayed, cached, stops when LinkedIn blocks.

**Scorer**: judges JobDetails against the **CV** and the **Rubric** with Claude; returns JobScores plus token usage and cost.

**Rubric**: the candidate's own priorities (`data/rubric.md`): dealbreakers, positives, score bands. It overrides the model's general opinion.

**Score bands**: 9-10 apply, 7-8 read, 0-6 skip. Any dealbreaker caps the score at 3.

**Prompt hash**: fingerprint of model + effort + instructions + CV + Rubric + schema. A JobScore with a different prompt hash is **stale** and gets re-scored.
