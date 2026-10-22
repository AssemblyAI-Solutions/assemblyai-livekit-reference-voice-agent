# tests

```console
uv run pytest
```

[`test_agent.py`](test_agent.py) sends the agent one line of text at a time through the LLM Gateway, with no audio, and checks what it does:

- It calls `get_current_time` to tell the time, with the right place.
- It doesn't make up a time for somewhere without a time zone.
- Its replies are short and speakable, with no lists or markdown.
- It hangs up after the user says goodbye.

Tool calls are checked exactly; wording is judged by another LLM. The tests need `ASSEMBLYAI_API_KEY` in `.env.local` and are skipped without it.

Run them whenever you change the instructions, a tool or the model, and more than once, since an LLM doesn't answer the same way every time. For each new tool or behavior, add a test like these; the [add-a-tool skill](../skills/add-a-tool/SKILL.md) has an example. See [LiveKit's testing docs](https://docs.livekit.io/testing/unit-tests/) for what else a test can check.
