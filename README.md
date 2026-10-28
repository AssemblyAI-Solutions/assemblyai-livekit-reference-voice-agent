# AssemblyAI voice agent starter for LiveKit

A voice agent template for [LiveKit Agents](https://github.com/livekit/agents) where the voice, the ears and the brain are all AssemblyAI, on one API key. Talk to it in five minutes, then shape it into your own agent with a coding agent.

| | AssemblyAI model | |
|---|---|---|
| **Voice** | [Streaming text-to-speech](https://www.assemblyai.com/docs/tts/getting-started/quickstart) | 4,000+ voices in six languages, or your own cloned voice. Word timings mean an interrupted reply is remembered only up to the words the user heard. |
| **Ears** | [Universal-3.6 Pro](https://www.assemblyai.com/docs/voice-agents/livekit-universal-3-6-pro) | Streaming speech-to-text that also decides when the user has finished talking, and holds the turn open while they read out a number or an email. |
| **Brain** | [LLM Gateway](https://www.assemblyai.com/docs/llm-gateway/quickstart) | 50 models from Google, OpenAI, Anthropic and others, with tool calling, behind one OpenAI-compatible API. |

Using Pipecat? See [assemblyai-pipecat-reference-voice-agent](https://github.com/dan-ince-aai/assemblyai-pipecat-reference-voice-agent).

## Get started

### 1. Install

You need [uv](https://docs.astral.sh/uv/getting-started/installation/), [Git LFS](https://git-lfs.com), the [LiveKit CLI](https://docs.livekit.io/intro/basics/cli/) (`brew install livekit-cli`) and an [AssemblyAI API key](https://www.assemblyai.com/dashboard/api-keys).

```console
git clone https://github.com/AssemblyAI/assemblyai-livekit-reference-voice-agent.git
cd assemblyai-livekit-reference-voice-agent
uv sync
cp .env.example .env.local
```

Put your API key in `.env.local`.

### 2. Talk to it

```console
lk agent console
```

Wear headphones so the agent doesn't hear itself, or add `--text` to type. Ask what time it is in Tokyo, interrupt it mid-sentence, then say goodbye.

### 3. Hear other voices

```console
export ASSEMBLYAI_API_KEY=<your key>
curl -sS https://tts.us.assemblyai.com/v1/speech \
  -H "Authorization: $ASSEMBLYAI_API_KEY" -H "Content-Type: application/json" \
  -d '{"text": "Hi, I am Kyla. How can I help?", "voice_id": "37e65973-9d96-5aab-adcd-01bf56ab5af9", "container": "wav"}' \
  -o voice.wav && afplay voice.wav
```

Browse the library by language with `curl -s "https://tts.us.assemblyai.com/v1/voices?scope=public&language=spanish" -H "Authorization: $ASSEMBLYAI_API_KEY"`, then set `TTS_VOICE` in [`src/agent.py`](src/agent.py) to a voice's `id`.

### 4. Call it from a browser or a phone

```console
lk cloud auth
lk app env --write --destination .env.local
lk agent dev
```

Open the [Agent Console](https://cloud.livekit.io/projects/p_/agents/console?autoStart=true&agentName=assistant) to talk to it in your browser. The agent registers as `assistant`, which is how a [web app](https://github.com/livekit-examples/agent-starter-react) or a [phone number](https://docs.livekit.io/telephony/) reaches it.

## Build your agent

Open the repo in Claude Code, Cursor or Codex and describe the agent you want. [`AGENTS.md`](AGENTS.md) tells the coding agent what to ask you (who the agent is for, where its users are, what they'll say) and which building blocks to apply. Each building block is a skill in [`skills/`](skills/):

| Building block | Default | Skill |
|---|---|---|
| Voice | Kyla | [tts-voice](skills/tts-voice/SKILL.md) |
| Turn detection | `balanced` | [turn-detection](skills/turn-detection/SKILL.md) |
| Speech threshold and interruptions | `0.2` | [interruptions-and-vad](skills/interruptions-and-vad/SKILL.md) |
| Noise suppression | Off | [voice-focus](skills/voice-focus/SKILL.md) |
| Key terms and context | The agent's name | [keyterms-and-prompt](skills/keyterms-and-prompt/SKILL.md) |
| Languages | Any, replies in English | [languages](skills/languages/SKILL.md) |
| Medical vocabulary | Off | [medical-mode](skills/medical-mode/SKILL.md) |
| LLM | `gemma-4-31b` | [llm-model](skills/llm-model/SKILL.md) |
| Data residency | US | [data-residency](skills/data-residency/SKILL.md) |
| Tools | `get_current_time` | [add-a-tool](skills/add-a-tool/SKILL.md) |

## How it works

```
user ──▶ Universal-3.6 Pro ──▶ LLM Gateway ──▶ AssemblyAI TTS ──▶ user
         speech-to-text,        reply and        word-timed
         end of turn            tool calls       speech
```

The whole agent is [`src/agent.py`](src/agent.py). [`src/README.md`](src/README.md) explains each default.

## Test

```console
uv run pytest
```

See [`tests/README.md`](tests/README.md).

## Deploy

```console
lk agent create --secrets ASSEMBLYAI_API_KEY=<your key>
```

This builds the [`Dockerfile`](Dockerfile) and deploys it to LiveKit Cloud. See [Deploying to LiveKit Cloud](https://docs.livekit.io/deploy/agents/). The image also runs on any container host, given `ASSEMBLYAI_API_KEY` and the `LIVEKIT_*` variables.

## License

[MIT](LICENSE)
