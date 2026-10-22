---
name: languages
description: Make the agent understand and speak languages other than English (Spanish, German, French, Italian, Portuguese and more), or several at once, by setting Universal-3.6 Pro's language_codes, the TTS language and voice, and the instructions together. Use when users will speak a language other than English, switch between languages, or when the agent should reply in another language.
---

# Languages

Three parts of the agent each need to know the language. Change them together in `src/agent.py`.

## Ask

- Which languages will users speak? One, or a mix (for example English and Spanish)?
- Which language should the agent reply in? The user's, or always one?

## 1. Speech-to-text

Universal-3.6 Pro recognizes many languages and switches between them on its own, with no settings. When you know which to expect, steer it toward them for better accuracy on short or ambiguous answers:

```python
assemblyai.STT(
    ...,
    language_codes=["es"],          # one language
    # language_codes=["en", "es"],  # or a mix, still switching between them
)
```

ISO 639-1 codes, up to 10. Leave it unset for anything-goes multilingual. It can change mid-call with `stt.update_options(language_codes=[...])`.

## 2. Text-to-speech

AssemblyAI TTS speaks English, Spanish, German, French, Italian and Portuguese:

```python
tts = assemblyai.TTS(voice=TTS_VOICE, language="es")  # "es" or "spanish"
```

The voice must speak the language. The eleven featured voices (`aai-jane`, `aai-michael` and the rest) speak all six; every other library voice, and every cloned voice, speaks only the language it was recorded in. To find voices recorded in a language, see the [tts-voice skill](../tts-voice/SKILL.md) (`&language=spanish`).

With a single-language library or cloned voice, leave `language` out: the voice's own language is used.

## 3. The words

- Translate `GREETING`.
- Add to `INSTRUCTIONS` which language to reply in: "Always reply in Spanish." or "Reply in the language the user speaks."
- Write `prompt` (if set) in the expected language.

## Mixed-language calls

Universal-3.6 Pro follows a user who switches languages mid-call. The TTS speaks one language per connection, so for an agent that replies in the user's language, prefer a featured voice and tell the user that the reply language is fixed per call unless they want to build switching.

## Check it

Run `lk agent console` and speak the language. Check the transcript in the console and listen to the reply. Add a test in `tests/test_agent.py` with a user line in that language, judging that the reply is in the right language.
