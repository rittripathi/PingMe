from typing import Any

from langchain_core.messages import ToolMessage

from agent.schemas import ParameterResolution
from agent.tools import geocode_location


class ParameterFiller:
    def __init__(self, llm):
        self.llm = llm
        self.tools = [geocode_location]
        self.tool_map = {tool.__name__: tool for tool in self.tools}

    async def fill(
        self,
        user_query: str,
        intent: dict[str, Any],
        connector,
        context: dict[str, Any] | None = None,
    ) -> ParameterResolution:
        context = context or {}

        prompt = f"""
You are the parameter-resolution agent for PingMe.

Your job is to determine the values of the parameters required by the
selected connector.

You can obtain values from:
1. The user's original query.
2. The extracted intent/entities.
3. The provided context.
4. Available tools.

IMPORTANT:
- Do NOT invent values.
- If a value can be extracted from the query, use it.
- If external information is required (e.g. coordinates for a place name), use a tool.
- If the required information cannot be obtained, mark it as missing.
- Do not create parameters the connector does not require.
- If context includes "previous_attempt_failed", that exact combination of
  parameters was already tried live and failed — do NOT propose the same
  values again. Use a tool to find the correct value instead of repeating
  the same guess (e.g. if a coin_id was wrong, that's a sign to search for
  the right one rather than reuse it).

USER QUERY:
{user_query}

EXTRACTED INTENT:
{intent}

SELECTED CONNECTOR:
Name: {connector.name}
Description: {connector.description}

PARAMETERS:
{connector.parameters}

CONTEXT:
{context}

Determine how to obtain every required parameter.
"""

        messages = [("user", prompt)]

        tool_llm = self.llm.bind_tools(self.tools)

        for iteration in range(5):
            response = await tool_llm.ainvoke(messages)

            # Debug visibility: if this never prints tool_calls>0 on any
            # iteration, the model isn't invoking tools at all (a model/
            # provider tool-calling issue, not a geocoding data issue) —
            # check this first if parameter resolution keeps looping.
            print(f"[parameter_filler] iteration {iteration}: tool_calls={response.tool_calls}")

            if not response.tool_calls:
                break

            messages.append(response)

            for tool_call in response.tool_calls:
                tool_name = tool_call["name"]
                tool_args = tool_call["args"]
                tool = self.tool_map.get(tool_name)

                if tool is None:
                    messages.append(("user", f"Tool '{tool_name}' is not available."))
                    continue

                try:
                    result = await tool(**tool_args)
                except Exception as exc:
                    # A tool failing shouldn't crash the whole request —
                    # feed the failure back so the model can ask instead.
                    result = {"error": f"Tool '{tool_name}' failed: {exc}"}

                print(f"[parameter_filler] tool {tool_name}({tool_args}) -> {result}")

                messages.append(ToolMessage(content=str(result), tool_call_id=tool_call["id"]))

        final_prompt = f"""
Resolve the connector parameters using the reasoning and tool results above.

Return the final ParameterResolution.

Required parameters:
{connector.parameters}

Original query:
{user_query}

Intent:
{intent}

Context:
{context}

Your result must:
- contain every required parameter that you can determine
- put unresolved required parameters in `missing`
- use status "complete" only when all required parameters are available
- use status "needs_input" when required information is missing
- never invent values
- if a tool call above returned found: false or an error, say so specifically
  in `message` (e.g. "couldn't find coordinates for 'India Gate'") and suggest
  a more specific or different input (e.g. "try a nearby city name instead"),
  rather than a generic "missing parameter" message
- if a tool call returned multiple plausible `candidates` and it is genuinely
  ambiguous which one the user meant (e.g. "Paris" could be France or Texas),
  do NOT guess — use status "needs_input", explain the ambiguity by name in
  `message` (e.g. "Did you mean Paris, France or Paris, Texas?"), and put the
  candidate list under `suggestions` keyed by the parameter name they resolve
  (e.g. suggestions: {{"location": [...]}}) so the user can pick one directly
"""

        final_messages = messages + [("user", final_prompt)]

        structured_llm = self.llm.with_structured_output(
            ParameterResolution,
            method="json_schema",
        )

        return await structured_llm.ainvoke(final_messages)
