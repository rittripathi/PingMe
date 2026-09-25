from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, create_model


# Sentinel the classifier can pick when nothing registered fits. Without
# this in the Literal, structured output *forces* a choice among real
# capabilities only — the model has no way to say "none of these", so it
# always guesses the closest match instead of reporting unsupported.
UNSUPPORTED = "unsupported"


def build_query_intent_model(capabilities: list[str]) -> type[BaseModel]:
    """
    Built fresh from whatever capabilities are currently registered,
    rather than a hand-maintained Literal. Adding a new connector with
    new capabilities is enough for the classifier to know about it —
    no schema file needs editing.
    """
    intent_literal = Literal[tuple(capabilities) + (UNSUPPORTED,)]
    return create_model(
        "QueryIntent",
        intent=(intent_literal, ...),
        entities=(dict[str, Any], Field(default_factory=dict)),
        condition=(Optional[dict[str, Any]], None),
        # Explicit cadence the user stated ("check every 5 minutes" -> 300).
        # None means they didn't specify one — the IntervalResolver falls
        # back to the connector's own default.
        requested_interval_seconds=(Optional[int], None),
    )


class ParameterResolution(BaseModel):
    status: Literal["complete", "needs_input"]
    parameters: dict[str, Any] = Field(default_factory=dict)
    missing: list[str] = Field(default_factory=list)
    message: Optional[str] = None
    # When a tool returned multiple plausible candidates (e.g. geocoding
    # "Paris" matches several cities) and it's genuinely ambiguous which
    # one the user means, list them here instead of guessing. Maps a
    # parameter name to the candidate options so the caller can present
    # "did you mean X or Y?" instead of a vague "missing parameter".
    suggestions: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)


# Maps the symbols an LLM naturally extracts ("<", ">", "==") to the
# operator vocabulary the Trigger model / rules engine expects.
OPERATOR_MAP = {
    "<": "lt", "<=": "lte", ">": "gt", ">=": "gte", "==": "eq", "=": "eq",
    "lt": "lt", "lte": "lte", "gt": "gt", "gte": "gte", "eq": "eq",
}


def normalize_condition(raw_condition: dict[str, Any] | None) -> dict[str, Any] | None:
    if not raw_condition:
        return None

    operator = raw_condition.get("operator")
    value = raw_condition.get("value")
    if operator is None or value is None:
        return None

    normalized_operator = OPERATOR_MAP.get(str(operator).strip())
    if normalized_operator is None:
        return None

    try:
        return {"operator": normalized_operator, "value": float(value)}
    except (TypeError, ValueError):
        return None
