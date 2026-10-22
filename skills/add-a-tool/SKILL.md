---
name: add-a-tool
description: Give the voice agent a new ability by adding a function tool that the LLM can call, such as looking something up in an API or database, booking, checking an order or transferring, with per-call state and tests. Use when the agent needs to fetch data or take an action, or when replacing the example get_current_time tool with real ones.
---

# Add a tool

Tools are `async` methods on `Assistant` in `src/agent.py`, decorated with `@function_tool`. `get_current_time` is the example. The docstring and type hints are the schema the LLM sees.

```python
from typing import Literal

    @function_tool
    async def check_order(
        self, context: RunContext[CallState], order_number: str, detail: Literal["status", "items"]
    ) -> str:
        """Look up one of the caller's orders.

        Args:
            order_number: The order number, as the caller read it out
            detail: What the caller wants to know about it
        """
        order = await orders.get(order_number)
        if order is None:
            raise ToolError(
                "No order has that number. Read it back to the caller and ask them to check it."
            )
        context.userdata.order = order
        return f"Order {order.number} is {order.status}."
```

## Rules

- **Describe it for the LLM.** One line on what it does, then every argument under `Args:`. Use `Literal[...]` for fixed choices, so the LLM can only pass valid ones.
- **Return a sentence or two of plain text.** It's turned into speech; no JSON, lists or markdown.
- **Raise `ToolError` with a recovery hint** when something goes wrong; the LLM passes it on to the user.
- **Keep per-call state out of the LLM's hands.** Who the user is, or which order they mean, goes in a state object, not in arguments the LLM repeats between tools:
  ```python
  @dataclass
  class CallState:
      order: Order | None = None

  session = AgentSession[CallState](userdata=CallState(), ...)  # in entrypoint
  ```
  Tools take `context: RunContext[CallState]` (imported from `livekit.agents`) and read `context.userdata`.
- **Call real APIs asynchronously,** with a timeout, and keep credentials in `.env.local` (and `.env.example`, empty).
- **Tell the agent when to use it.** Add a line to `INSTRUCTIONS` about what the tool is for and when to call it. Update the "What you do" line too.
- **Log IDs, not personal details.**

## Test it

Add a test to `tests/test_agent.py` that checks the call and the reply:

```python
async def test_checks_an_order(session, judge):
    result = await session.run(user_input="Where's my order 4 1 2 7?")
    result.expect.next_event().is_function_call(name="check_order")
    result.expect.next_event().is_function_call_output()
    await result.expect.next_event().is_message(role="assistant").judge(
        judge, intent="Tells the user the order's status."
    )
```

Use a fake of the API in tests (pass it into `Assistant`, or patch it) so they don't depend on a live system. Run `uv run pytest` twice; an LLM doesn't answer the same way every time.

If the agent now has a clear purpose, also rewrite `INSTRUCTIONS` and `GREETING` for it, and remove `get_current_time` if it doesn't belong.
