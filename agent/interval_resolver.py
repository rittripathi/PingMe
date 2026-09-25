from connectors.base import Connector


class IntervalResolver:
    """
    Decides how often a trigger should be checked. Kept as its own tool,
    separate from parameter filling, because it answers a different
    question: not "what does the API need" but "how fast does this data
    change, and did the user ask for a specific cadence".

    Deterministic on purpose — no LLM call. The inputs (a user-stated
    number, or the connector's own declared volatility) are already
    concrete; a model call here would add latency and a chance of
    inventing a number instead of using the one already available.
    """

    def resolve(self, requested_seconds: int | None, connector: Connector) -> tuple[int, str]:
        """
        Returns (interval_seconds, reason) — the reason is surfaced to the
        user so "why did it pick 120s?" always has an answer.
        """
        if requested_seconds is not None and requested_seconds > 0:
            if requested_seconds < connector.min_interval_seconds:
                return (
                    connector.min_interval_seconds,
                    f"you asked for every {requested_seconds}s, but {connector.name} "
                    f"needs at least {connector.min_interval_seconds}s between checks",
                )
            return requested_seconds, "using the frequency you specified"

        return (
            connector.default_interval_seconds,
            f"{connector.name} data typically changes every "
            f"~{connector.default_interval_seconds}s, so checking on that cadence",
        )
