---
name: wait-longer-for-numbers
description: Give callers more time to finish reading out phone numbers, member IDs, dates of birth and spellings, by slowing Universal-3.6 Pro's turn detection only while the agent waits for one. Use when callers get cut off mid-number, a number is split across two turns, the agent replies before the caller has finished an ID, or the user asks to slow down or tune turn detection or endpointing.
---

# Wait longer for numbers

Universal-3.6 Pro decides when the caller has finished talking (`turn_detection="stt"` in `src/agent.py`). With `mode="balanced"` it ends a turn after at most 1.28 seconds of silence (`max_turn_silence=1280`). That's right for most answers, but people pause while they read a number off a card: "4 1 5, 5 5 5 ... 0 1 9 9". If the pause is longer than 1.28 seconds, the number arrives as two turns, and the agent answers the first half.

The fix is to wait longer only when the agent has just asked for something like that. The agent's own question says when: the moment it asks for a phone number, raise `max_turn_silence`; when it asks anything else, put it back. Every other turn keeps its speed.

Tested against the live API: a phone number read with a 2.2-second pause arrived as two turns ("415-555." then "0199.") at the default, and as one ("415-555-0199.") with `max_turn_silence=3000`.

## Steps

### 1. Add the switch to `src/agent.py`

Add `import re` to the imports, and `ConversationItemAddedEvent` to the `livekit.agents` import. Then, next to the other settings near the top:

```python
# The agent's questions whose answers callers read out slowly: numbers, IDs, dates, spellings
ASKS_FOR_DETAILS = re.compile(r"phone|number|member id|date of birth|birthday|spell", re.IGNORECASE)
# How long a pause can be before the caller's turn ends, in ms, after one of those questions
PATIENT_MAX_TURN_SILENCE = 3000
# ...and after any other question: what mode="balanced" uses
BALANCED_MAX_TURN_SILENCE = 1280
```

And a function, after `llm_gateway()`:

```python
def wait_longer_for_details(session: AgentSession, stt: assemblyai.STT) -> None:
    """Give the caller longer to finish their turn after the agent asks for a number or ID."""

    @session.on("conversation_item_added")
    def _on_item_added(ev: ConversationItemAddedEvent) -> None:
        if ev.item.type != "message" or ev.item.role != "assistant":
            return
        text = ev.item.text_content or ""
        asks = "?" in text and ASKS_FOR_DETAILS.search(text) is not None
        stt.update_options(
            max_turn_silence=PATIENT_MAX_TURN_SILENCE if asks else BALANCED_MAX_TURN_SILENCE
        )
```

`update_options` sends the change to the open stream as an `UpdateConfiguration` message. It doesn't reconnect.

### 2. Wire it up in `entrypoint`

The STT is created inline in `AgentSession(...)`. Move it into a variable first, so the function can reach it:

```python
    stt = assemblyai.STT(
        model="universal-3-6-pro",
        ...  # unchanged
    )

    session = AgentSession[CallState](
        userdata=CallState(),
        stt=stt,
        ...  # unchanged
    )
    wait_longer_for_details(session, stt)
```

### 3. Fit the pattern to the agent

`ASKS_FOR_DETAILS` matches the receptionist's questions about phone numbers, member IDs, dates of birth and spelling. If the agent collects other things read out slowly, such as order numbers, card numbers, postcodes or email addresses, add words from those questions. Only questions count (`"?"`), so "Your confirmation number is 4 1 2 0 7." doesn't slow the next turn.

## Check it

1. `uv run pytest` still passes (the change doesn't affect text-only tests).
2. Talk to the agent with `lk agent console`, as a new patient. When it asks for your phone number, read it with a two-second pause in the middle: it should wait for the whole number and read it back in full.
3. To test without speaking, this check runs in an `AgentSession` with no audio. Keep the STT in a variable `stt` and call `wait_longer_for_details(session, stt)` in the `session` fixture of `tests/test_agent.py` (wrap the fixture's `async with` in `livekit.agents.utils.http_context.open()`, which an STT needs outside a LiveKit job):
   ```python
   async def test_waits_longer_for_a_phone_number(session):
       await session.run(user_input="I'm new. Jordan Lee, that's L E E.")
       await session.run(user_input="June 2nd, 1990.")
       assert session.stt._opts.max_turn_silence == PATIENT_MAX_TURN_SILENCE
   ```

## Tuning

- **3000 ms** suits a caller reading from a card. In testing, the agent then replied about 3 seconds after the caller finished the number, rather than about 1.3, so the agent feels slower on exactly these answers. Go lower if that's too slow, or higher (up to about 5000) for callers who look things up mid-call.
- If turns end on a pause after something that looks complete, such as "415-555.", also raise `min_turn_silence` in the same `update_options` call (balanced uses 128 ms), and set it back with the other value.
- For the best accuracy on the numbers themselves, add the [sync-second-pass skill](../sync-second-pass/SKILL.md) too. It needs the whole number in one turn, which this skill provides.
