"""Text-only tests of the assistant, through the LLM Gateway.

Each test sends the agent one line, as text, and checks what it does: which tools it calls,
and what it says, judged by an LLM. The tests need ASSEMBLYAI_API_KEY (from .env.local or the
environment) and no audio.

    uv run pytest
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
from livekit.agents import AgentSession, llm

from agent import Assistant, llm_gateway

pytestmark = pytest.mark.skipif(
    not os.getenv("ASSEMBLYAI_API_KEY"), reason="needs ASSEMBLYAI_API_KEY for the LLM Gateway"
)

# The judge doesn't need to be fast, so it can be a stronger model
JUDGE_MODEL = "claude-sonnet-4-6"


@pytest.fixture
async def session() -> AsyncIterator[AgentSession]:
    async with llm_gateway() as agent_llm, AgentSession(llm=agent_llm) as session:
        await session.start(Assistant())
        yield session


@pytest.fixture
async def judge() -> AsyncIterator[llm.LLM]:
    async with llm_gateway(JUDGE_MODEL) as judge:
        yield judge


async def test_tells_the_time_with_the_tool(session: AgentSession, judge: llm.LLM) -> None:
    result = await session.run(user_input="What time is it in Tokyo right now?")

    call = result.expect.next_event().is_function_call(name="get_current_time")
    assert call.event().item.arguments and "Tokyo" in call.event().item.arguments
    result.expect.next_event().is_function_call_output(is_error=False)
    await (
        result.expect.next_event()
        .is_message(role="assistant")
        .judge(judge, intent="Tells the user the current time in Tokyo.")
    )


async def test_recovers_from_a_place_without_a_time_zone(
    session: AgentSession, judge: llm.LLM
) -> None:
    result = await session.run(user_input="What's the time on the Moon?")

    await (
        result.expect[-1]
        .is_message(role="assistant")
        .judge(
            judge,
            intent=(
                "Doesn't state a made-up time for the Moon. It may explain that the Moon has "
                "no time zone, or offer a time somewhere on Earth instead."
            ),
        )
    )


async def test_replies_are_short_and_speakable(session: AgentSession, judge: llm.LLM) -> None:
    result = await session.run(user_input="Can you list all the planets in the solar system?")

    await (
        result.expect.next_event()
        .is_message(role="assistant")
        .judge(
            judge,
            intent=(
                "A short reply meant to be spoken aloud: no bullet points, numbered list, "
                "markdown or emojis. Naming the planets in a sentence is fine."
            ),
        )
    )


async def test_hangs_up_after_goodbye(session: AgentSession) -> None:
    result = await session.run(user_input="That's everything, thanks. Bye!")

    result.expect.contains_function_call(name="end_call")
