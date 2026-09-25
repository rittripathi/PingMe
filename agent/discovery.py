"""
Discovery agent — the practical answer to "there are 1000s of public APIs,
we can't hardcode all of them."

apis.guru (https://apis.guru) publishes a free, keyless JSON index of
~2000+ public APIs with links to their OpenAPI specs. When a request
doesn't match anything in the local registry, this module:

  1. Searches that index by keyword (search_apis_guru) — fast, cheap,
     no LLM call, just string matching over titles/descriptions.
  2. Fetches the OpenAPI spec for the best candidate.
  3. Has the LLM *read* the spec (propose_connector_from_spec) and
     propose a DynamicConnector config — base URL, params, and a JMESPath
     to the relevant value — from the real spec, not from memory.
  4. The caller (planner.py) dry-runs that config through
     DynamicConnector.fetch(), same verify-before-propose principle as
     everywhere else, before it's ever shown to the user as ready.

HONESTLY UNTESTED: steps 1-3 need network access to apis.guru and a real
LLM call, neither reachable from the sandbox this was built in. The
keyword-ranking logic (_rank_candidates) is pure string matching and is
unit-tested offline against a mocked index — that part is solid. The live
fetch and the LLM-reads-a-real-spec step are not verified; expect to
debug prompt/parsing against real spec shapes, which vary a lot in size
and structure.

Off by default — see config.settings.enable_discovery.
"""

from typing import Any, Optional

import httpx
from pydantic import BaseModel, Field

APIS_GURU_LIST_URL = "https://api.apis.guru/v2/list.json"

# Generic filler words that add noise rather than signal — "current" and
# "rate" alone are common enough in unrelated domains (banking's "current
# account", "interest rate") that leaving them in let a banking API
# outscore an actual forex API on a real query. Domain terms (exchange,
# eur, inr, crypto, weather, ...) are exactly what should decide the match.
_STOPWORDS = {
    "notify", "ping", "alert", "please", "when", "the", "and", "for",
    "with", "that", "this", "from", "more", "than", "are", "was", "were",
    "between", "about", "current", "today", "now", "me", "my", "is", "if",
}


class ProposedConnector(BaseModel):
    supported: bool
    reason: Optional[str] = None  # why unsupported, if supported=False

    name: Optional[str] = None
    description: Optional[str] = None
    capabilities: list[str] = Field(default_factory=list)
    value_field: Optional[str] = None
    base_url: Optional[str] = None
    static_params: dict[str, Any] = Field(default_factory=dict)
    param_query_keys: dict[str, str] = Field(default_factory=dict)
    response_path: Optional[str] = None
    parameters: dict[str, Any] = Field(default_factory=dict)

    def to_connector_config(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "capabilities": self.capabilities,
            "value_field": self.value_field,
            "base_url": self.base_url,
            "static_params": self.static_params,
            "param_query_keys": self.param_query_keys,
            "response_path": self.response_path,
            "parameters": self.parameters,
            "auth": None,
        }


def _rank_candidates(index: dict, query: str, limit: int) -> list[dict]:
    """
    Separated from search_apis_guru so this scoring logic is testable
    offline against a small mocked index, without hitting the network.
    Deliberately simple (term overlap, no embeddings) — cheap enough to
    run on every unsupported request. Swap for embedding similarity once
    the registry has enough entries that keyword matching starts missing
    obvious hits (same tradeoff discussed for the connector registry
    itself once it grows past a few dozen).

    Title hits are weighted 2x over description hits — a term appearing
    in the API's actual name/title is a much stronger signal than an
    incidental mention buried in a longer description.
    """
    query_terms = {t for t in query.lower().split() if len(t) > 2 and t not in _STOPWORDS}
    scored = []

    for api_id, entry in index.items():
        preferred_version = entry.get("versions", {}).get(entry.get("preferred", ""), {})
        info = preferred_version.get("info", {})
        title = (info.get("title") or "").lower()
        description = (info.get("description") or "").lower()

        title_hits = sum(1 for term in query_terms if term in title)
        description_hits = sum(1 for term in query_terms if term in description)
        score = title_hits * 2 + description_hits

        if score > 0:
            scored.append(
                {
                    "api_id": api_id,
                    "title": info.get("title", ""),
                    "description": (info.get("description") or "")[:200],
                    "spec_url": preferred_version.get("swaggerUrl"),
                    "score": score,
                }
            )

    scored.sort(key=lambda c: c["score"], reverse=True)
    return scored[:limit]


async def search_apis_guru(query: str, limit: int = 5) -> list[dict]:
    """UNTESTED live (needs network to api.apis.guru). Ranking logic (see
    _rank_candidates) is unit-tested separately."""
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(APIS_GURU_LIST_URL)
        response.raise_for_status()
        index = response.json()
    return _rank_candidates(index, query, limit)


async def propose_connector_from_spec(
    llm, spec_url: str, user_query: str, candidate_title: str
) -> ProposedConnector:
    """
    UNTESTED (network + LLM). Fetches an OpenAPI spec and asks the LLM to
    propose a DynamicConnector config from it. Specs are truncated since
    full specs can be 100KB+ — this truncation is the most likely thing
    to need tuning against a real spec; a large spec may need the
    relevant endpoint located first (e.g. by searching for the query
    terms within the spec text) rather than blindly taking the first
    15,000 characters.
    """
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(spec_url)
        response.raise_for_status()
        spec_text = response.text[:15000]

    prompt = f"""
You are reading the OpenAPI spec for the public API "{candidate_title}" to
determine if it can satisfy this user request:

"{user_query}"

OPENAPI SPEC (possibly truncated — the relevant endpoint may not be visible
if the spec is large; say unsupported rather than guessing if so):
{spec_text}

Find ONE GET endpoint that returns a single relevant numeric value with no
authentication required (or a simple API-key auth you can describe). Do not
invent fields that aren't in the spec.

If found, propose a connector config. If not, set supported=false and say
why in `reason` — do not guess at a plausible-looking endpoint.
"""

    structured_llm = llm.with_structured_output(ProposedConnector, method="json_schema")
    return await structured_llm.ainvoke(prompt)
