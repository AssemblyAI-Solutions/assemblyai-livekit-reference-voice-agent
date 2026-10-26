"""A voice agent starter where every model is AssemblyAI's, on one API key.

- Text-to-speech: AssemblyAI streaming TTS, with word-level timings
- Speech-to-text: Universal-3.6 Pro streaming, which also decides when the user has finished
  their turn
- LLM: LLM Gateway, an OpenAI-compatible API for models from Google, OpenAI, Anthropic and more

Each setting below names the skill in skills/ that explains when and how to change it.

    uv run src/agent.py console   # talk to the agent in your terminal
    uv run src/agent.py dev       # connect it to LiveKit Cloud, for a web or phone frontend
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    JobContext,
    JobProcess,
    ToolError,
    TurnHandlingOptions,
    cli,
    function_tool,
)
from livekit.agents.beta.tools import EndCallTool
from livekit.plugins import assemblyai, openai, silero

load_dotenv(Path(__file__).parents[1] / ".env.local")

logger = logging.getLogger("agent")

# Frontends, phone numbers and the Agent Console ask LiveKit for the agent by this name
AGENT_NAME = "assistant"

# --- Voice: skills/tts-voice ---

# A voice id from https://www.assemblyai.com/docs/tts/voices, or one of your cloned voices
TTS_VOICE = "987db62e-a2c2-569a-9c4d-82460cdea1bd"  # Keegan

# The agent introduces itself by the voice's name; if you change one, change the other
ASSISTANT_NAME = "Keegan"

# --- Speech-to-text ---

# How quickly a turn ends versus how accurate the transcript is: "min_latency", "balanced"
# or "max_accuracy". See skills/turn-detection.
STT_MODE = "balanced"

# How loud speech must be to count, for transcription and for interrupting the agent. The
# STT and Silero use the same value. See skills/interruptions-and-vad.
VAD_THRESHOLD = 0.2

# Names and terms the STT should spell right. See skills/keyterms-and-prompt.
STT_KEYTERMS = [ASSISTANT_NAME]

# --- LLM: skills/llm-model ---

# Any model from https://llm-gateway.assemblyai.com/v1/models that supports tools
LLM_MODEL = "gemma-4-31b"
LLM_GATEWAY_URL = "https://llm-gateway.assemblyai.com/v1"

GREETING = f"Hi, I'm {ASSISTANT_NAME}. How can I help?"

INSTRUCTIONS = """\
You are {name}, a friendly voice assistant. You're talking with someone live, and everything \
you write is spoken aloud by a text-to-speech voice.

What you do: chat about anything and answer questions, and tell the time anywhere in the \
world with get_current_time.

How to talk:
- Keep each reply to one or two short sentences, and ask one question at a time.
- Don't use lists, markdown, emojis or abbreviations that sound odd aloud.
- When you read back a phone number, code or ID, separate every character with a space and \
group them with commas, like "5 1 2, 5 5 5, 0 1 3 4".
- If you didn't catch something, say so and ask again, rather than guessing.

Only state facts from your tools or that you're sure of. When the person has nothing else, \
say a short goodbye and call end_call."""


class Assistant(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions=INSTRUCTIONS.format(name=ASSISTANT_NAME),
            # Lets the agent hang up after saying goodbye, but not during the greeting
            tools=[EndCallTool(ignore_on_enter=True)],
        )

    async def on_enter(self) -> None:
        # A fixed greeting is spoken right away, without waiting on the LLM
        self.session.say(GREETING)

    @function_tool
    async def get_current_time(self, timezone: str) -> str:
        """Get the current date and time somewhere in the world.

        Args:
            timezone: The place's IANA time zone, such as "Europe/London" or "America/Chicago"
        """
        try:
            now = datetime.now(ZoneInfo(timezone))
        except (ZoneInfoNotFoundError, ValueError):
            raise ToolError(
                f"{timezone!r} isn't a time zone. Use an IANA name such as America/Chicago."
            ) from None
        hour = now.hour % 12 or 12
        meridiem = "AM" if now.hour < 12 else "PM"
        return f"It's {hour}:{now:%M} {meridiem} on {now:%A, %B} {now.day} in {timezone}."


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


@server.rtc_session(agent_name=AGENT_NAME)
async def entrypoint(ctx: JobContext) -> None:
    ctx.log_context_fields = {"room": ctx.room.name}

    tts = assemblyai.TTS(voice=TTS_VOICE)
    # Open the TTS connection now, so the greeting doesn't wait on the handshake
    tts.prewarm()

    session = AgentSession(
        stt=assemblyai.STT(
            model="universal-3-6-pro",
            mode=STT_MODE,
            vad_threshold=VAD_THRESHOLD,
            keyterms_prompt=STT_KEYTERMS,
            # More building blocks, off by default. Each skill says when to use it.
            # voice_focus="near-field",     # background noise: skills/voice-focus
            # prompt="...",                 # what calls are about: skills/keyterms-and-prompt
            # language_codes=["en", "es"],  # expected languages: skills/languages
            # domain="medical-v1",          # medical vocabulary: skills/medical-mode
        ),
        llm=llm_gateway(),
        tts=tts,
        vad=ctx.proc.userdata["vad"],
        turn_handling=TurnHandlingOptions(
            # Universal-3.6 Pro decides when the user has finished speaking...
            turn_detection="stt",
            # ...so LiveKit shouldn't add its own delay on top
            endpointing={"min_delay": 0},
            # A cough or an "uh-huh" pauses the reply instead of cutting it off
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
