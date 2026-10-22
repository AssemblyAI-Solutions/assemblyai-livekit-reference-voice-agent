---
name: sync-second-pass
description: Make the transcription of phone numbers, member IDs, dates of birth and spelled names more accurate with a second pass through AssemblyAI's Sync API, uploaded live from the agent's STT node while the caller speaks. Use when the user wants higher accuracy on numbers, IDs or entities, mentions the Sync API, "second pass", re-transcription or the STT node, or the agent mishears IDs that the caller reads out.
---

# Sync second pass

Universal-3.6 Pro streaming transcribes every turn as the caller speaks, which is what lets the agent answer quickly. For the few turns where one wrong character is costly, such as a phone number or member ID, this adds a second transcript of the same audio from the [Sync API](https://www.assemblyai.com/docs/sync-stt/getting-started/transcribe-live-audio) and uses it instead.

The audio is uploaded to the Sync API *while the caller is still talking*, by tapping the agent's `stt_node`. So when the turn ends, the Sync transcript is nearly ready. In testing it arrived 80 to 200 ms after the streaming one, and those milliseconds are added only to the turns that get a second pass.

Tested against the live API in a real `AgentSession`: a member ID read as "W, eight seven three, four five one, two six" came back from streaming as "W873-451-26" and from the Sync API as "W87345126", and that is what the LLM received.

## Before you start

**Apply the [wait-longer-for-numbers skill](../wait-longer-for-numbers/SKILL.md) first.** This skill uses its `ASKS_FOR_DETAILS` pattern to choose which turns get a second pass. It also keeps a number in one turn: given half a number, cut off by a pause, the Sync API was seen to complete it ("415-555" became "415-555-5555"). It needs the whole answer.

Each second pass is billed as Sync transcription, on top of the streaming transcription of the same audio, for those turns only.

## Steps

### 1. Install the AssemblyAI SDK

```console
uv add "assemblyai>=1.6.5"
```

### 2. Create `src/second_pass.py`

```python
"""A second, more accurate transcript of the turns that matter, from AssemblyAI's Sync API.

Universal-3.6 Pro streaming transcribes the caller as they speak. For a turn where one wrong
character is costly, such as a phone number, member ID or date of birth, `SecondPass` also
uploads the same audio to the Sync API while the caller is still talking, and when the turn
ends it swaps the streaming transcript for the Sync one. Because the upload happens live, the
Sync transcript is ready shortly after the caller stops.

It sits in the agent's `stt_node`: `tee()` passes the caller's audio on to the streaming STT
and uploads it during the turns that want a second pass, and `process()` passes the STT's
events on, with the Sync transcript in place of the streaming one.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from collections import deque
from collections.abc import AsyncIterable, AsyncIterator, Callable

import assemblyai as aai
from livekit import rtc
from livekit.agents import stt

logger = logging.getLogger("second-pass")

# The Sync API takes at most 120 s of audio per request
MAX_TURN_SECONDS = 100


class SecondPass:
    def __init__(
        self,
        *,
        wanted: Callable[[], bool],
        context: Callable[[], list[str]] = list,
        prompt: str | None = None,
        keyterms: list[str] | None = None,
        model: str = "universal-3-6-pro",
        timeout: float = 2.0,
        preroll: float = 1.0,
    ) -> None:
        """
        Args:
            wanted: Called as each turn starts; True if the turn should get a second pass,
                for example because the agent just asked for a phone number.
            context: Called as each turn starts; the conversation so far, oldest first, sent
                as `conversation_context` so the Sync API knows what the caller is answering.
            prompt: What the call is about, as for the streaming STT.
            keyterms: Names and terms to spell right, as for the streaming STT.
            model: The Sync API model.
            timeout: How long to wait for the Sync transcript once the turn ends, before
                keeping the streaming one.
            preroll: Seconds of audio from before the turn started to include, since the
                start of speech is reported a little after the caller starts talking.
        """
        self._wanted = wanted
        self._context = context
        self._config = {"model": model, "prompt": prompt, "keyterms_prompt": keyterms}
        self._timeout = timeout
        self._preroll_seconds = preroll
        self._transcriber = aai.AsyncSyncTranscriber(api_key=os.environ["ASSEMBLYAI_API_KEY"])
        self._preroll: deque[rtc.AudioFrame] = deque()
        self._session: aai.AsyncLiveSession | None = None
        self._opened_at = 0.0

    async def tee(self, audio: AsyncIterable[rtc.AudioFrame]) -> AsyncIterator[rtc.AudioFrame]:
        """Pass the caller's audio through, uploading it to the Sync API during a turn."""
        async for frame in audio:
            if self._session is not None:
                self._session.write(frame.data)
                if time.monotonic() - self._opened_at > MAX_TURN_SECONDS:
                    await self._discard()
            else:
                self._preroll.append(frame)
                while sum(f.duration for f in self._preroll) > self._preroll_seconds:
                    self._preroll.popleft()
            yield frame

    async def process(
        self, events: AsyncIterable[stt.SpeechEvent]
    ) -> AsyncIterator[stt.SpeechEvent]:
        """Pass the STT's events through, with the Sync transcript in place of the final one."""
        async for event in events:
            if event.type == stt.SpeechEventType.START_OF_SPEECH:
                if self._session is None and self._wanted():
                    self._open()
            elif event.type == stt.SpeechEventType.FINAL_TRANSCRIPT and self._session is not None:
                await self._replace_transcript(event)
            yield event

    async def aclose(self) -> None:
        await self._discard()
        await self._transcriber.aclose()

    def _open(self) -> None:
        if not self._preroll:
            return
        first = self._preroll[0]
        config = aai.SyncTranscriptionConfig(
            **self._config,
            sample_rate=first.sample_rate,
            channels=first.num_channels,
            conversation_context=self._context() or None,
        )
        self._session = self._transcriber.open_live(config)
        self._opened_at = time.monotonic()
        for frame in self._preroll:
            self._session.write(frame.data)
        self._preroll.clear()

    async def _replace_transcript(self, event: stt.SpeechEvent) -> None:
        session, self._session = self._session, None
        assert session is not None
        started = time.monotonic()
        try:
            result = await asyncio.wait_for(session.result(), self._timeout)
        except Exception as e:
            logger.warning("second pass failed, keeping the streaming transcript: %r", e)
            await session.abort()
            return
        text = (result.text or "").strip()
        if not text or not event.alternatives:
            return
        logger.info(
            "second pass in %.0f ms: %r -> %r",
            (time.monotonic() - started) * 1000,
            event.alternatives[0].text,
            text,
        )
        event.alternatives[0].text = text

    async def _discard(self) -> None:
        session, self._session = self._session, None
        if session is not None:
            await session.abort()
```

### 3. Share the STT's prompt and key terms

In `src/agent.py`, move the `prompt` and `keyterms_prompt` passed to `assemblyai.STT(...)` in `entrypoint` into constants near the top, after `GREETING`, so the second pass uses the same ones:

```python
# What calls are about, and the names they mention, for speech-to-text
STT_PROMPT = (
    "Phone call to a primary care and cardiology clinic. A patient gives their name, date "
    "of birth, phone number, insurance details, medications with doses and allergies, and "
    "books an appointment."
)
STT_KEYTERMS = [CLINIC_NAME, RECEPTIONIST_NAME, *(p.name for p in PROVIDERS)]
```

and in `entrypoint`: `prompt=STT_PROMPT, keyterms_prompt=STT_KEYTERMS`.

### 4. Tap the STT node

In `src/agent.py`, add `from second_pass import SecondPass` after the `clinic` import, and these two methods to `Receptionist`:

```python
    async def stt_node(self, audio, model_settings):
        # Re-transcribe the answers to questions about numbers and IDs with the Sync API
        second_pass = SecondPass(
            wanted=lambda: ASKS_FOR_DETAILS.search(self._last_reply()) is not None,
            context=lambda: [self._last_reply()],
            prompt=STT_PROMPT,
            keyterms=STT_KEYTERMS,
        )
        try:
            events = Agent.default.stt_node(self, second_pass.tee(audio), model_settings)
            async for event in second_pass.process(events):
                yield event
        finally:
            await second_pass.aclose()

    def _last_reply(self) -> str:
        for item in reversed(self.chat_ctx.items):
            if item.type == "message" and item.role == "assistant":
                return item.text_content or ""
        return ""
```

`context` passes the agent's question to the Sync API as `conversation_context`, so it knows the caller is answering "What's your member ID?".

Add `"second_pass"` to `known-first-party` under `[tool.ruff.lint.isort]` in `pyproject.toml`, and to the `COPY` in the `Dockerfile` if it copies files one by one (it copies `.`, so it doesn't by default).

## Check it

1. `uv run ruff check` and `uv run pytest` pass. The text-only tests don't use the STT node, so they're unaffected.
2. Run `lk agent console` as a new patient and read out your phone number and member ID. The log shows a line per second pass, with the streaming and Sync transcripts:
   ```
   second pass in 156 ms: "Sure, it's W873-451-26." -> "Sure, it's W87345126."
   ```
   and Keegan reads back the Sync version.
3. Other turns, such as "I'd like a follow-up", log nothing and are as fast as before.

## Tuning

- **Which turns.** `wanted` decides at the start of each turn. Widen `ASKS_FOR_DETAILS` for more kinds of question, or return `True` to re-transcribe every turn, which costs more and adds the Sync wait to every reply.
- **`timeout`** (2 s): if the Sync API hasn't answered by then, the streaming transcript is kept and a warning is logged. The agent never waits longer than this.
- **Data residency.** The SDK uses `https://sync.assemblyai.com`. To keep audio in the EU, set `aai.settings.sync_base_url = "https://sync.eu.assemblyai.com"` before the agent starts.
- **Only the final transcript changes.** The interim transcripts the agent sees while the caller speaks still come from streaming. That only matters if something acts on interim transcripts.
