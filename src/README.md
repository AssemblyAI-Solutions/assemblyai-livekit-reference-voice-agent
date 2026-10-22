# src

[`agent.py`](agent.py) is the whole agent:

- **Settings**, at the top: the voice, the speech-to-text settings and the LLM. Each names the skill that explains it.
- **`Assistant`**: the instructions, the greeting and the tools.
- **`entrypoint`**: builds the speech-to-text → LLM → text-to-speech pipeline for each call.

Run it from the repo root with `lk agent console`. Here's why each default is what it is.

## Text-to-speech

- **The greeting doesn't wait for the LLM.** `on_enter` speaks a fixed greeting with `session.say()`, on a TTS connection that `tts.prewarm()` opened while the call was being set up.
- **Interruptions are remembered word by word.** AssemblyAI TTS sends the time of every word it speaks. With `use_tts_aligned_transcript=True`, an interrupted reply is kept in the chat history only up to the words the user heard.
- **Replies are written to be heard.** The instructions ask for one or two short sentences, and `tts_text_transforms` strips any markdown or emojis that slip through.

## Speech-to-text

- **Universal-3.6 Pro decides when the user is done** (`turn_detection="stt"`), from the words as well as the silence, and `endpointing={"min_delay": 0}` stops LiveKit adding its own wait on top. `mode="balanced"` ends a turn after at most 1.28 seconds of silence.
- **The STT knows what the agent just asked.** The plugin passes each reply to Universal-3.6 Pro as context, so after "What's your email?" it expects an email. That needs no code.
- **One speech threshold.** `VAD_THRESHOLD` (0.2, Universal-3.6 Pro's default) is used by both the STT and Silero, which handles interruptions, so the two agree on what counts as speech.
- **The agent's name is a key term**, so it's spelled right when users say it.

## The LLM and tools

- **The LLM Gateway is used through the OpenAI plugin.** `llm_gateway()` is `openai.LLM` with the Gateway's URL and your AssemblyAI key.
- **Tools are methods** decorated with `@function_tool`, whose docstrings are what the LLM sees. `get_current_time` is the example; a `ToolError` tells the LLM how to recover.
- **The agent can hang up** with LiveKit's `EndCallTool`, after saying goodbye.
- **A cough doesn't cut the agent off.** With `resume_false_interruption`, a noise pauses the reply, which carries on if no words follow.
