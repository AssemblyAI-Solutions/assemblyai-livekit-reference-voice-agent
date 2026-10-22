# src

The agent, in two files short enough to read top to bottom.

| File | What's in it |
|---|---|
| [`agent.py`](agent.py) | Keegan: the instructions, the greeting, the four tools, and `entrypoint`, which builds the speech-to-text → LLM → text-to-speech pipeline |
| [`clinic.py`](clinic.py) | The made-up clinic the tools work on: two doctors, two weeks of open times, and one returning patient. It has no LiveKit code in it, so you can swap it for your real systems |

Run the agent from the repo root with `lk agent console` (or `uv run src/agent.py console`). Here's what each part does, and why.

## Text-to-speech

**The greeting doesn't wait for the LLM.** `on_enter` speaks a fixed greeting with `session.say()` as soon as the caller joins, on a connection that `tts.prewarm()` opened while the call was being set up.

**Interruptions are remembered word by word.** AssemblyAI TTS sends the time of every word it speaks. With `use_tts_aligned_transcript=True`, when the caller cuts the agent off, the chat history keeps only the words the caller heard, so the LLM doesn't think it said things it didn't.

**The voice is one setting.** `TTS_VOICE` is a voice id from the [voice library](https://www.assemblyai.com/docs/tts/voices) or a voice you've cloned. `RECEPTIONIST_NAME` is the name the agent introduces itself by, so change them together. To speak another language, pass it to the TTS, for example `assemblyai.TTS(voice=..., language="es")`, and pick a voice that speaks it.

**Replies are written to be heard.** The instructions ask for one or two short sentences with no lists or markdown, and `tts_text_transforms` strips any that slip through. Numbers to check are read one character at a time, in groups: "4 1 5, 5 5 5, 0 1 9 9".

## Speech-to-text

**Medical Mode, a description of the call, and the names it will hear.** `domain="medical-v1"` turns on [Medical Mode](https://www.assemblyai.com/docs/streaming/medical-mode) for medications, conditions and doses. It's a paid add-on; remove it to compare. `prompt` describes what a call is about, and `keyterms_prompt` lists the clinic's and doctors' names so they're spelled right.

**Universal-3.6 Pro decides when the caller is done.** `turn_detection="stt"` uses AssemblyAI's end-of-turn detection, which reads the words as well as the silence: a caller who pauses partway through a phone number has said an unfinished number, so the turn stays open. `mode="balanced"` ends a turn after at most 1.28 seconds of silence; `"min_latency"` cuts that to 0.64 seconds. `endpointing={"min_delay": 0}` stops LiveKit adding its own wait on top. To give callers longer while they read out numbers, use the [wait-longer-for-numbers skill](../skills/wait-longer-for-numbers/SKILL.md).

**The STT knows what the agent just asked.** The plugin passes each of the agent's replies to Universal-3.6 Pro as context, so after "What's your date of birth?" it expects a date. That's on by default and needs no code.

**Silero and AssemblyAI agree on what speech is.** Silero's voice activity detection decides when the caller is interrupting. Its threshold matches the STT's own (`VAD_THRESHOLD = 0.2`), so the two don't disagree about quiet speech. Change them together.

**A cough doesn't cut the agent off.** With `resume_false_interruption`, a noise or an "uh-huh" pauses the reply, which carries on if no words follow. In `lk agent dev` and on LiveKit Cloud the agent also gets LiveKit's [adaptive interruption handling](https://docs.livekit.io/agents/logic/turns/adaptive-interruption-handling/), which tells a real interruption from background talk. In console mode it stops whenever the caller speaks.

## The conversation

**The instructions are the receptionist's playbook.** `INSTRUCTIONS` covers how to talk on the phone, the safety rules (send emergencies to 911, give no medical advice), the order of the intake questions and how to book.

**Tools change the clinic's records.** `find_patient`, `register_patient`, `check_availability` and `book_appointment` are methods on `Receptionist` decorated with `@function_tool`. Their docstrings and type hints are what the LLM sees, so keep them accurate. `visit_type` is a `Literal`, so the LLM can only pass a visit type the clinic offers.

**The patient is kept in the call's state, not passed around by the LLM.** `CallState` holds the clinic and the patient the call is about, so the LLM can't book an appointment for the wrong person. Tools read it as `context.userdata`.

**Errors tell the LLM how to recover.** A tool raises `ToolError` with a message such as "Check the spelling and the date with the caller, or offer to register them as a new patient", and the LLM passes that on to the caller.

**The LLM Gateway is used through the OpenAI plugin.** The Gateway speaks the OpenAI Chat Completions API, so `llm_gateway()` is `openai.LLM` with the Gateway's URL and your AssemblyAI key. `LLM_MODEL` picks the model.

**The agent can hang up.** LiveKit's `EndCallTool` lets the agent end the call after saying goodbye.

**Patient details stay out of the logs.** The agent logs patient IDs only.
