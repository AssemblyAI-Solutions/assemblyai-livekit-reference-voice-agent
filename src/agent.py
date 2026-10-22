"""A voice agent that runs every model on AssemblyAI, with one API key.

- Speech-to-text: Universal-3.6 Pro streaming, which also decides when the user's turn ends
- LLM: LLM Gateway, an OpenAI-compatible API for models from Google, OpenAI, Anthropic and more
- Text-to-speech: AssemblyAI Streaming TTS, with word-level timings

    uv run src/agent.py console   # talk to the agent in your terminal
    uv run src/agent.py dev       # connect it to LiveKit Cloud, for a web or phone frontend
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    JobContext,
    JobProcess,
    RunContext,
    ToolError,
    TurnHandlingOptions,
    cli,
    function_tool,
)
from livekit.plugins import assemblyai, openai, silero

from weather import LocationNotFoundError, current_weather

load_dotenv(Path(__file__).parents[1] / ".env.local")

logger = logging.getLogger("agent")

# Any model from https://llm-gateway.assemblyai.com/v1/models. Gemma 4 31B is the quickest to
# a first token among the Gateway models we measured; see the README for others.
LLM_MODEL = "gemma-4-31b"
LLM_GATEWAY_URL = "https://llm-gateway.assemblyai.com/v1"

# A voice id from https://www.assemblyai.com/docs/tts/voices, or one of your cloned voices
TTS_VOICE = "987db62e-a2c2-569a-9c4d-82460cdea1bd"  # Keegan

# Silero (used for barge-in) should agree with AssemblyAI's own VAD on what counts as speech,
# so both use the STT's default threshold on Universal-3.6 Pro.
VAD_THRESHOLD = 0.2

GREETING = "Hi there! I'm a voice assistant running on AssemblyAI. How can I help you today?"

INSTRUCTIONS = """\
You are a friendly, helpful voice assistant. The user is talking to you out loud, and \
everything you write is spoken by a text-to-speech voice.

Keep replies short and conversational: one to three sentences. Don't use lists, markdown, \
emojis or other formatting that can't be spoken. Write numbers, dates, prices and units \
normally; the voice reads them correctly on its own.

If you don't know something, say so instead of guessing. You can look up the current \
weather anywhere in the world."""


class Assistant(Agent):
    def __init__(self) -> None:
        super().__init__(instructions=INSTRUCTIONS)

    async def on_enter(self) -> None:
        # A fixed greeting is spoken right away, without waiting on the LLM
        self.session.say(GREETING)

    @function_tool
    async def lookup_weather(self, context: RunContext, location: str) -> str:
        """Look up the current weather for a place.

        Args:
            location: The name of a city or town, such as "Paris" or "Austin"
        """
        logger.info("looking up weather for %s", location)
        try:
            return await current_weather(location)
        except LocationNotFoundError:
            raise ToolError(f"Couldn't find a place called {location}.") from None


def llm_gateway(model: str = LLM_MODEL) -> openai.LLM:
    """An LLM served by AssemblyAI's LLM Gateway, through its OpenAI-compatible API."""
    api_key = os.getenv("ASSEMBLYAI_API_KEY")
    if not api_key:
        raise ValueError("Set ASSEMBLYAI_API_KEY in .env.local or the environment")
    return openai.LLM(model=model, base_url=LLM_GATEWAY_URL, api_key=api_key)


server = AgentServer()


def prewarm(proc: JobProcess) -> None:
    proc.userdata["vad"] = silero.VAD.load(activation_threshold=VAD_THRESHOLD)


server.setup_fnc = prewarm


@server.rtc_session()
async def entrypoint(ctx: JobContext) -> None:
    ctx.log_context_fields = {"room": ctx.room.name}

    tts = assemblyai.TTS(voice=TTS_VOICE)
    # Open the TTS connection now, so the greeting doesn't wait on the handshake
    tts.prewarm()

    session = AgentSession(
        stt=assemblyai.STT(
            model="universal-3-6-pro",
            # "min_latency" ends turns soonest; "balanced" waits a little longer for the user
            # to go on, and "max_accuracy" longer still.
            mode="min_latency",
            vad_threshold=VAD_THRESHOLD,
            # Names and jargon the agent should always hear right, e.g. ["AssemblyAI"]
            # keyterms_prompt=[],
        ),
        llm=llm_gateway(),
        tts=tts,
        vad=ctx.proc.userdata["vad"],
        turn_handling=TurnHandlingOptions(
            # Universal-3.6 Pro decides when the user has finished speaking...
            turn_detection="stt",
            # ...so LiveKit shouldn't add its own delay on top
            endpointing={"min_delay": 0},
            # A cough or an "uh-huh" pauses the agent instead of cutting it off
            interruption={"resume_false_interruption": True},
        ),
        tts_text_transforms=["filter_emoji", "filter_markdown"],
        # When the user interrupts, keep only the words they heard in the chat history,
        # using the TTS's word timings
        use_tts_aligned_transcript=True,
    )

    async def log_usage() -> None:
        logger.info("usage: %s", session.usage)

    ctx.add_shutdown_callback(log_usage)

    await session.start(agent=Assistant(), room=ctx.room)


if __name__ == "__main__":
    cli.run_app(server)
