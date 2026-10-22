---
name: interruptions-and-vad
description: Tune what counts as speech (the VAD threshold, shared by Universal-3.6 Pro and Silero) and how the agent handles being interrupted (barge-in). Use when setting up an agent for a noisy or quiet environment, when background noise, TV, other people or echo make the agent stop talking or hear things, when quiet speakers aren't heard, when interruptions feel slow or too eager, or when some messages must not be interrupted.
---

# Interruptions and VAD

Two things decide when the user is speaking: Universal-3.6 Pro's own voice activity detection (`vad_threshold`) and Silero's in LiveKit (`activation_threshold`), which makes interruptions fast. They should agree, so both come from one setting in `src/agent.py`:

```python
VAD_THRESHOLD = 0.2  # used for assemblyai.STT(vad_threshold=...) and silero.VAD.load(activation_threshold=...)
```

`0.2` is Universal-3.6 Pro's default in every mode. Always change the two together: if they differ, one hears speech the other doesn't, and interruptions lag.

## Ask

- Where will users be? A quiet room, a car, the street, a busy office or call center, a shop floor, a kiosk?
- On what device: phone handset, headset, laptop or speakerphone?
- Can the agent hear itself (speakerphone, laptop speakers without echo cancellation)?

## Choose

| Situation | What to do |
|---|---|
| Quiet room, headset or phone | Keep `0.2`. |
| Background noise or chatter makes the agent stop mid-reply, or hear words nobody said | Turn on the [voice-focus skill](../voice-focus/SKILL.md) first. If it still happens, raise `VAD_THRESHOLD` to `0.3`, then `0.4`. |
| Quiet or distant speakers aren't heard | Lower `VAD_THRESHOLD` to `0.15`. |
| Coughs or "uh-huh"s cut the agent off | Keep `resume_false_interruption` on (it is), and raise `min_duration` (below). |
| Interruptions feel slow | Lower `interruption_delay` (below). |

Higher thresholds miss soft speech; lower ones react to noise. Move in steps of about 0.1 and test with real audio from the target environment.

## Interruption settings

In `TurnHandlingOptions(interruption={...})`:

| Key | Default | Effect |
|---|---|---|
| `resume_false_interruption` | `True` | A noise that pauses the agent, with no words after it, lets the agent carry on |
| `false_interruption_timeout` | `2.0` s | Silence after a pause before it counts as a false interruption |
| `min_duration` | `0.5` s | Speech shorter than this doesn't interrupt; raise to `0.8` for noisy places |
| `min_words` | `0` | Words needed to interrupt; `2` ignores single-word backchannels |
| `enabled` | `True` | `False` makes the agent impossible to interrupt |

On LiveKit Cloud and in `lk agent dev`, LiveKit's [adaptive interruption handling](https://docs.livekit.io/agents/logic/turns/adaptive-interruption-handling/) also tells real interruptions from backchannels; console mode doesn't have it.

`interruption_delay` on `assemblyai.STT(...)` sets how soon the first partial transcript arrives (0 to 1000 ms; the server adds 256 ms). `"balanced"` uses 500. Lower it (`0`) for faster barge-in; raise it for more confident first partials in noise.

For a message that must be heard in full, such as a legal disclosure: `self.session.say(text, allow_interruptions=False)`.

## Check it

Run `lk agent console` with the noise the agent will face (play a recording of it if needed). Talk over the agent, cough, say "uh-huh", and stay silent while the noise plays. The agent should stop for real interruptions only.
