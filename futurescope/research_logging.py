from __future__ import annotations

from typing import Any

from futurescope.research_registry import ResearchRegistry


def log_dashboard_look(
    query_type: str,
    query: dict[str, Any],
    reason: str,
    experiment_id: str | None = None,
) -> int | None:
    """Best-effort cheap logger for interactive historical research surfaces.

    The logger de-duplicates identical query payloads, so Streamlit reruns do not
    inflate the count.  Logging failure never blocks the dashboard, but callers
    should visibly disclose the failure when validation claims matter.
    """

    try:
        return ResearchRegistry().log_look(
            query_type=query_type,
            query=query,
            reason=reason,
            experiment_id=experiment_id,
            result_revealed=True,
            source="futurescope-dashboard",
        )
    except Exception:
        return None
