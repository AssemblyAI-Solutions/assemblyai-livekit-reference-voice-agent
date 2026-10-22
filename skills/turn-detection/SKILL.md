---
name: turn-detection
description: Choose how quickly Universal-3.6 Pro decides the user has finished speaking, with the STT mode preset (min_latency, balanced, max_accuracy) and min_turn_silence / max_turn_silence. Use when setting up a new agent, when the agent feels slow to reply or replies before the user has finished, when users get cut off mid-sentence or while reading out numbers, emails or addresses, or when the user asks about latency, endpointing or turn-taking.
---

# Turn detection

Universal-3.6 Pro decides when the user's turn has ended, reading the words as well as the silence (`turn_detection="stt"` in `src/agent.py`). After a short pause (`min_turn_silence`) it checks whether the turn reads as finished: a complete sentence ends the turn there; an unfinished one stays open. After a long pause (`max_turn_silence`) the turn ends regardless.

**Entity-aware endpointing** is built in and needs no settings: when a turn ends in something still in progress, such as digits, a spelled code, an email, an address, a date or a name, the turn is held open until `max_turn_silence`. AssemblyAI measured it cutting phone-number errors from 7.0% to 2.2%, with the median reply time unchanged.

## The preset

```python
STT_MODE = "balanced"  # src/agent.py
```

| `STT_MODE` | `min_turn_silence` | `max_turn_silence` | First partial (`interruption_delay` + 256 ms) | Use for |
|---|---|---|---|---|
| `"min_latency"` | 128 ms | 640 ms | ~256 ms | Fast back-and-forth with short answers: quick Q&A, menus, confirmations. Long pauses split turns. |
| `"balanced"` (default) | 128 ms | 1280 ms | ~756 ms | Most voice agents. |
| `"max_accuracy"` | 512 ms | 2560 ms | ~756 ms | Users who dictate (IDs, addresses, emails), think aloud, or speak slowly, where a slower reply is acceptable. |

`STT_MODE` is fixed when the connection opens.

## Ask

- What will users say: short answers, or long explanations, numbers, emails, addresses?
- Do they pause to think or look things up mid-sentence (older callers, people reading from a card)?
- Which matters more when they conflict: replying fast, or never cutting the user off?

## Fine-tuning

Set either value on `assemblyai.STT(...)` to override the preset's:

```python
assemblyai.STT(..., mode=STT_MODE, max_turn_silence=2000)
```

- **Users cut off mid-thought or while dictating:** raise `max_turn_silence` (try 2000, up to about 4000). Turns that are held open then take that long to end.
- **Turns end early on a pause after something that looks complete,** such as a spelled email ("It's John." "Smith."): raise `min_turn_silence` (try 400).
- **Replies feel slow:** lower `max_turn_silence`, or use `"min_latency"`. Expect more split turns; an LLM usually copes with a split sentence, but not with a split ID.

## Only while waiting for something long

To be patient only when the agent has asked for something like a phone number, change the values mid-call, without reconnecting:

```python
stt.update_options(max_turn_silence=3000)  # after the agent asks for a number
stt.update_options(max_turn_silence=1280)  # afterwards: back to balanced
```

Keep the STT in a variable (`stt = assemblyai.STT(...)`, then `AgentSession(stt=stt, ...)`) and call these from a `conversation_item_added` handler that looks at the agent's latest message, or from a tool. In testing, a phone number read with a 2.2-second pause arrived as two turns on `balanced` and as one with `max_turn_silence=3000`; the agent then replied about 3 seconds after the number ended.

## Keep as they are

- `endpointing={"min_delay": 0}` in `TurnHandlingOptions`. LiveKit's own delay would be added on top of the STT's.
- To use LiveKit's turn detector model instead (`turn_detection=MultilingualModel()`), remove `mode=` so the plugin hands transcripts over immediately, and set `endpointing={"min_delay": 0.5, "max_delay": 3.0}`. See [Universal-3.6 Pro with LiveKit](https://www.assemblyai.com/docs/voice-agents/livekit-universal-3-6-pro).

## Check it

Run `lk agent console` and talk: pause mid-sentence for a second, read out a phone number in chunks. Turns should end where the user expects.
