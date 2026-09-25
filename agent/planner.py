from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from agent.interval_resolver import IntervalResolver
from agent.parameter_filler import ParameterFiller
from agent.discovery import propose_connector_from_spec, search_apis_guru
from agent.schemas import UNSUPPORTED, build_query_intent_model, normalize_condition
from config import settings

MAX_VERIFY_RETRIES = 2  # total attempts = 1 initial + this many retries


class PlannerState(TypedDict, total=False):
    user_query: str
    intent: dict[str, Any]
    connector: Any
    context: dict[str, Any]
    parameters: dict[str, Any]
    interval_seconds: int
    interval_reason: str
    verified_value: float
    verify_error: str
    verify_attempts: int
    result: dict[str, Any]


class Planner:
    def __init__(self, llm, registry):
        self.llm = llm
        self.registry = registry
        self.parameter_filler = ParameterFiller(llm)
        self.interval_resolver = IntervalResolver()

        self.QueryIntentModel = build_query_intent_model(registry.all_capabilities())
        self._system_prompt = self._build_system_prompt()

        self.graph = self._build_graph()

    def _build_system_prompt(self) -> str:
        lines = [
            "You convert a user's natural language request into a structured intent "
            "for a condition-based alerting system called PingMe.",
            "",
            "Choose ONLY one of these intents:",
            "",
        ]
        for connector in self.registry.connectors.values():
            for cap in connector.capabilities:
                lines.append(f"- {cap}: {connector.description}")
        lines += [
            "",
            "Extract entities such as: asset, currency, location, city, country.",
            "",
            "If the user specifies a threshold condition, extract:",
            '- condition: {"operator": one of <, <=, >, >=, ==, "value": number}',
            "",
            "If the user specifies how often to check (e.g. 'every 5 minutes', "
            "'check hourly'), extract requested_interval_seconds as an integer "
            "number of seconds. If they don't say, leave it null — do not guess.",
            "",
            "Examples:",
            '"Bitcoin price" -> crypto_price',
            '"Ping me when bitcoin drops below 90000" -> crypto_price, '
            'condition: {"operator": "<", "value": 90000}',
            '"Notify me if Delhi temperature exceeds 40, checking every 10 minutes" '
            '-> temperature, condition: {"operator": ">", "value": 40}, '
            "requested_interval_seconds: 600",
            "",
            f'If the request does not clearly match ANY intent above, respond with '
            f'intent: "{UNSUPPORTED}" — do NOT guess the closest one.',
            f'"notify me when my package is delivered" -> {UNSUPPORTED}',
        ]
        return "\n".join(lines)

    def refresh_capabilities(self):
        """
        Call after registering a new connector at runtime (e.g. the
        discovery agent confirming a new source) so the intent classifier
        can immediately route to it, without restarting the process.
        """
        self.QueryIntentModel = build_query_intent_model(self.registry.all_capabilities())
        self._system_prompt = self._build_system_prompt()

    # ---------------- Nodes ----------------

    async def understand_query(self, state: PlannerState):
        structured_llm = self.llm.with_structured_output(self.QueryIntentModel, method="json_schema")
        result = await structured_llm.ainvoke(self._system_prompt + "\n\nUser query:\n" + state["user_query"])
        print(f"[planner] classified intent: {result.model_dump()}")
        return {"intent": result.model_dump()}

    async def search_registry(self, state: PlannerState):
        intent = state["intent"]["intent"]

        if intent == UNSUPPORTED:
            proposal = await self._try_discovery(state["user_query"])
            if proposal is not None:
                return {
                    "result": {
                        "status": "proposed_connector",
                        "message": (
                            f"I don't have a built-in source for this, but I found "
                            f"\u00ab{proposal.name}\u00bb on the web that looks like it fits: "
                            f"{proposal.description}. Does this look right?"
                        ),
                        "proposal": proposal.to_connector_config(),
                    }
                }
            return {
                "result": {
                    "status": "unsupported",
                    "message": "This doesn't match any data source PingMe currently supports.",
                }
            }

        connector = self.registry.search(intent)
        if connector is None:
            return {"result": {"status": "unsupported", "message": f"No known source supports '{intent}'."}}
        return {"connector": connector}

    async def _try_discovery(self, user_query: str):
        """
        Gated behind settings.enable_discovery (default off) — see
        agent/discovery.py's module docstring for what is and isn't
        verified about this path. Any failure here (network, LLM, a
        malformed spec) falls through to a normal "unsupported" result
        rather than crashing the request.
        """
        if not settings.enable_discovery:
            return None

        try:
            candidates = await search_apis_guru(user_query, limit=5)
            print(f"[discovery] {len(candidates)} ranked candidate(s): "
                  f"{[(c['api_id'], c['score']) for c in candidates]}")

            for candidate in candidates:
                if not candidate.get("spec_url"):
                    continue
                try:
                    proposal = await propose_connector_from_spec(
                        self.llm, candidate["spec_url"], user_query, candidate["title"]
                    )
                except Exception as exc:
                    print(f"[discovery] spec read failed for '{candidate['api_id']}': {exc}")
                    continue

                if proposal.supported:
                    return proposal
                print(f"[discovery] candidate '{candidate['api_id']}' rejected by spec-reader: {proposal.reason}")

            return None
        except Exception as exc:
            print(f"[discovery] failed, falling through to unsupported: {exc}")
            return None

    async def fill_parameters(self, state: PlannerState):
        connector = state["connector"]

        if not connector.parameters:
            return {"parameters": {}}

        resolution = await self.parameter_filler.fill(
            user_query=state["user_query"],
            intent=state["intent"],
            connector=connector,
            context=state.get("context", {}),
        )

        if resolution.status == "needs_input":
            return {
                "result": {
                    "status": "needs_input",
                    "message": resolution.message or ("Missing: " + ", ".join(resolution.missing)),
                    "missing": resolution.missing,
                    "suggestions": resolution.suggestions,
                }
            }
        return {"parameters": resolution.parameters}

    async def check_parameters(self, state: PlannerState):
        connector = state["connector"]
        parameters = state["parameters"]
        missing = []

        for name, schema in connector.parameters.items():
            if not schema.get("required"):
                continue
            if name not in parameters:
                missing.append(name)
                continue
            value = parameters[name]
            expected_type = schema.get("type")
            if expected_type == "float":
                try:
                    parameters[name] = float(value)
                except (TypeError, ValueError):
                    return {"result": {"status": "needs_input", "message": f"Parameter '{name}' must be a number."}}
            elif expected_type == "string" and not isinstance(value, str):
                return {"result": {"status": "needs_input", "message": f"Parameter '{name}' must be text."}}

        if missing:
            return {"result": {"status": "needs_input", "message": "Missing: " + ", ".join(missing), "missing": missing}}
        return {}

    async def resolve_interval(self, state: PlannerState):
        connector = state["connector"]
        requested = state["intent"].get("requested_interval_seconds")
        interval_seconds, reason = self.interval_resolver.resolve(requested, connector)
        return {"interval_seconds": interval_seconds, "interval_reason": reason}

    async def verify_request(self, state: PlannerState):
        """
        Prove the plan works instead of asserting it. On failure this no
        longer just dies — see handle_verify_failure / give_up below for
        the self-correction retry loop.
        """
        connector = state["connector"]
        parameters = state["parameters"]
        try:
            value = await connector.fetch(parameters)
        except Exception as exc:
            attempts = state.get("verify_attempts", 0) + 1
            print(f"[planner] verify attempt {attempts} failed: {exc}")
            return {"verify_error": str(exc), "verify_attempts": attempts}
        return {"verified_value": value, "verify_error": None}

    async def handle_verify_failure(self, state: PlannerState):
        """
        Self-correction: feed the live failure back as context and route
        back to fill_parameters instead of dying on the first bad guess.
        This is the actual "try, observe, adjust" loop — it's what makes
        the search tools (coin lookup, repo lookup, etc.) worth having,
        since a blind first guess now gets a second attempt informed by
        what actually went wrong.
        """
        context = dict(state.get("context", {}))
        context["previous_attempt_failed"] = {
            "parameters": state.get("parameters"),
            "error": state.get("verify_error"),
        }
        print(f"[planner] retrying parameter resolution after verify failure "
              f"(attempt {state.get('verify_attempts')})")
        return {"context": context}

    async def give_up(self, state: PlannerState):
        return {
            "result": {
                "status": "infeasible",
                "message": (
                    f"Tried {state.get('verify_attempts', 1)} time(s) — "
                    f"last error: {state.get('verify_error')}"
                ),
            }
        }

    # ---------------- Routers ----------------

    def _finish_or(self, next_node: str):
        def router(state: PlannerState):
            return "finish" if "result" in state else next_node
        return router

    def verify_router(self, state: PlannerState):
        if state.get("verify_error") is None:
            return "finish"
        # Allow MAX_VERIFY_RETRIES retries on top of the first attempt —
        # give up only once total attempts exceeds that.
        if state.get("verify_attempts", 0) >= MAX_VERIFY_RETRIES + 1:
            return "give_up"
        return "retry"

    # ---------------- Graph ----------------

    def _build_graph(self):
        graph = StateGraph(PlannerState)

        graph.add_node("understand_query", self.understand_query)
        graph.add_node("search_registry", self.search_registry)
        graph.add_node("fill_parameters", self.fill_parameters)
        graph.add_node("check_parameters", self.check_parameters)
        graph.add_node("resolve_interval", self.resolve_interval)
        graph.add_node("verify_request", self.verify_request)
        graph.add_node("handle_verify_failure", self.handle_verify_failure)
        graph.add_node("give_up", self.give_up)

        graph.add_edge(START, "understand_query")
        graph.add_edge("understand_query", "search_registry")

        graph.add_conditional_edges(
            "search_registry", self._finish_or("fill_parameters"),
            {"finish": END, "fill_parameters": "fill_parameters"},
        )
        graph.add_conditional_edges(
            "fill_parameters", self._finish_or("check_parameters"),
            {"finish": END, "check_parameters": "check_parameters"},
        )
        graph.add_conditional_edges(
            "check_parameters", self._finish_or("resolve_interval"),
            {"finish": END, "resolve_interval": "resolve_interval"},
        )

        graph.add_edge("resolve_interval", "verify_request")
        graph.add_conditional_edges(
            "verify_request", self.verify_router,
            {"finish": END, "retry": "handle_verify_failure", "give_up": "give_up"},
        )
        graph.add_edge("handle_verify_failure", "fill_parameters")
        graph.add_edge("give_up", END)

        return graph.compile()

    # ---------------- Public ----------------

    async def plan(self, user_query: str) -> dict:
        state = await self.graph.ainvoke({"user_query": user_query, "context": {}})

        if "result" in state:
            return state["result"]

        connector = state["connector"]
        condition = normalize_condition(state["intent"].get("condition"))
        if condition is not None:
            condition["field"] = connector.value_field

        return {
            "status": "ready",
            "intent": state["intent"],
            "plan": {
                "source": connector.name,
                "config": state["parameters"],
                "condition": condition,
                "interval_seconds": state["interval_seconds"],
                "interval_reason": state["interval_reason"],
                "verified_value": state["verified_value"],
            },
        }
