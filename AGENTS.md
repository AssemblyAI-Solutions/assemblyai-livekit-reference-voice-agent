# AGENTS.md

A LiveKit Agents (Python) voice agent where every model is from AssemblyAI: Universal-3.6 Pro streaming speech-to-text, an LLM on AssemblyAI's LLM Gateway, and AssemblyAI streaming text-to-speech. The agent is Ava, a receptionist for a made-up clinic who takes patient intake and books appointments. See @README.md for setup and the reasoning behind each setting.

## Layout

- `src/agent.py`: the `Receptionist` agent (instructions, greeting, tools) and the `entrypoint` that builds the STT → LLM → TTS pipeline.
- `src/clinic.py`: the in-memory clinic the tools run against. It stands in for a practice management or EHR system; keep it free of LiveKit imports.
- `tests/test_clinic.py`: offline unit tests of the clinic.
- `tests/test_agent.py`: text-only tests of Ava through the LLM Gateway. Full calls are played against a simulated caller and checked against the clinic's records; single replies are judged by an LLM.

## Tooling

- Install with `uv sync`. LiveKit Agents and its plugins come from a fork, pinned in `[tool.uv.sources]` in `pyproject.toml`, until the AssemblyAI TTS plugin is released (livekit/agents#8040). Bump `rev` in all four entries together.
- Format and lint with `uv run ruff format` and `uv run ruff check`.
- Test with `uv run pytest`. The agent tests need `ASSEMBLYAI_API_KEY` in `.env.local` and are skipped without it.
- Try changes with `lk agent console --text` (type to Ava) or `lk agent console` (talk to her). Both need only the AssemblyAI key.

## Making changes

- When you change the instructions, a tool, or the model, run the agent tests, and run them more than once: LLM behavior varies between runs. For a new behavior, add a test first, then change the agent until it passes. Prefer checking the clinic's records (`session.userdata`) over judging wording.
- Tools are methods on `Receptionist` decorated with `@function_tool`. Their docstrings and type hints are the schema the LLM sees, so keep them accurate. Use `Literal` types for fixed choices. Raise `ToolError` with a message that tells the model how to recover.
- Per-call state lives in `CallState` (`context.userdata` in tools). Keep identifiers such as the current patient there, rather than having the LLM pass them between tools.
- Everything Ava writes is spoken. Tool outputs and instructions should produce short, plain sentences, with no markdown or lists.
- Don't log patient details. The agent logs patient IDs only.

## AssemblyAI specifics

- The LLM Gateway is OpenAI-compatible: `openai.LLM(base_url="https://llm-gateway.assemblyai.com/v1", api_key=ASSEMBLYAI_API_KEY)`. Model IDs have no provider prefix (`gemma-4-31b`, `claude-haiku-4-5-20251001`); `GET /v1/models` lists them. The EU Gateway (`llm-gateway.eu.assemblyai.com`) serves only Anthropic and Google Gemini models.
- Turn detection is Universal-3.6 Pro's own (`turn_detection="stt"`), so LiveKit's `endpointing.min_delay` stays `0`. Tune turn-taking with the STT's `mode`, `min_turn_silence` and `max_turn_silence`, not LiveKit's endpointing.
- Silero's `activation_threshold` matches the STT's `vad_threshold` (`0.2`, the Universal-3.6 Pro default). Change them together.
- Medical Mode (`domain="medical-v1"`) supports English, Spanish, German and French, and is billed as an add-on.
- AssemblyAI docs: https://www.assemblyai.com/docs. Universal-3.6 Pro with LiveKit: https://www.assemblyai.com/docs/voice-agents/livekit-universal-3-6-pro

## LiveKit documentation

Check the current LiveKit docs rather than relying on memory: `lk docs search "<query>"` and `lk docs get-page <path>`, or LiveKit's [docs MCP server](https://docs.livekit.io/reference/developer-tools/docs-mcp/). LiveKit also publishes [agent skills](https://github.com/livekit/agent-skills) for building, testing and debugging LiveKit agents.
