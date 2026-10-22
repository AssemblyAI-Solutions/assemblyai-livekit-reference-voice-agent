"""Text-only tests of the agent's behavior, judged by an LLM.

They run the agent's LLM through the LLM Gateway, without audio, so they need
ASSEMBLYAI_API_KEY (from .env.local or the environment) and nothing else.

    uv run pytest
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
from livekit.agents import AgentSession, llm, mock_tools

from agent import Assistant, llm_gateway

pytestmark = pytest.mark.skipif(
    not os.getenv("ASSEMBLYAI_API_KEY"), reason="needs ASSEMBLYAI_API_KEY for the LLM Gateway"
)

# The judge doesn't need to be fast, so it can be a stronger model than the agent's
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


async def test_greets_the_user(session: AgentSession, judge: llm.LLM) -> None:
    result = await session.run(user_input="Hello!")

    await (
        result.expect.next_event()
        .is_message(role="assistant")
        .judge(judge, intent="Greets the user in a friendly way and offers to help.")
    )
    result.expect.no_more_events()


async def test_replies_are_speakable(session: AgentSession, judge: llm.LLM) -> None:
    result = await session.run(user_input="What are three good ways to fall asleep faster?")

    await (
        result.expect.next_event()
        .is_message(role="assistant")
        .judge(
            judge,
            intent=(
                "Answers in a few short, conversational sentences that read naturally aloud, "
                "with no bulleted or numbered list, markdown or emojis."
            ),
        )
    )


async def test_looks_up_the_weather(session: AgentSession, judge: llm.LLM) -> None:
    def fake_weather(location: str) -> str:
        return "Paris, Île-de-France Region, France: 64°F with light rain, wind 9 mph"

    with mock_tools(Assistant, {"lookup_weather": fake_weather}):
        result = await session.run(user_input="What's the weather like in Paris right now?")

    result.expect.next_event().is_function_call(name="lookup_weather")
    result.expect.next_event().is_function_call_output()
    await (
        result.expect.next_event()
        .is_message(role="assistant")
        .judge(judge, intent="Tells the user it's about 64 degrees and raining lightly in Paris.")
    )
    result.expect.no_more_events()


async def test_admits_what_it_does_not_know(session: AgentSession, judge: llm.LLM) -> None:
    result = await session.run(user_input="What's my mother's maiden name?")

    await (
        result.expect.next_event()
        .is_message(role="assistant")
        .judge(
            judge, intent="Says it doesn't know the user's mother's maiden name, without guessing."
        )
    )
    result.expect.no_more_events()
