"""Render scored jobs as a ranked markdown report. Pure: no I/O."""

from datetime import date

from jobscout.models import Job


def ranked(jobs: list[Job]) -> list[Job]:
    """Keep the scored jobs and sort them best first.

    Args:
        jobs: Jobs as returned by the Job store.

    Returns:
        Jobs that have a score, highest score first.
    """
    return sorted(
        (j for j in jobs if j.score), key=lambda j: j.score.score if j.score else -1, reverse=True
    )


def render_report(jobs: list[Job], today: date) -> str:
    """Render the ranked report.

    Args:
        jobs: Jobs as returned by the Job store; unscored ones are left out.
        today: Date shown in the report title.

    Returns:
        The report as markdown.
    """
    rows = ranked(jobs)
    lines = [f"# JobScout report ({today})", "", f"{len(rows)} scored jobs", ""]
    for job in rows:
        s, ref = job.score, job.ref
        assert s is not None
        lines += [
            f"## {s.score}/10 [{s.verdict}] {ref.title} @ {ref.company}",
            f"{ref.location} · {ref.url}",
            "",
            s.reasoning,
            "",
            f"- Matches: {', '.join(s.matched_skills) or '-'}",
            f"- Gaps: {', '.join(s.gaps) or '-'}",
        ]
        if s.dealbreakers_hit:
            lines.append(f"- Dealbreakers: {', '.join(s.dealbreakers_hit)}")
        lines.append("")
    return "\n".join(lines)
