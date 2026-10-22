# tests

```console
uv run pytest
```

| File | What it checks | Needs |
|---|---|---|
| [`test_clinic.py`](test_clinic.py) | The made-up clinic: finding and registering patients, open times, booking | Nothing |
| [`test_agent.py`](test_agent.py) | The receptionist, as text through the LLM Gateway | `ASSEMBLYAI_API_KEY` in `.env.local` |

The agent tests don't use audio. Two of them play out a whole call against a simulated caller, another LLM given a persona, then check what ended up in the clinic's records:

- **A new patient**, whose intake details must be saved exactly as given, and an afternoon new patient visit booked.
- **Maria Garcia, a returning patient**, who must get a morning follow-up with Dr. Nakamura.

The rest check single replies, judged by an LLM: the agent doesn't invent a patient it can't find, sends an emergency to 911, and gives no medical advice.

## When to run them

Run them whenever you change the instructions, a tool or the model, and run them more than once, because an LLM doesn't answer the same way every time. Without a key, the agent tests are skipped.

## Adding a test

For a new behavior, write the test first, then change the agent until it passes. Check the clinic's records (`session.userdata`) where you can, rather than the agent's wording:

```python
async def test_books_a_cardiology_consultation(session, judge):
    appointment = await simulate_call(
        session,
        judge,
        "You're Maria Garcia, born March 14, 1985, and your heart races sometimes.",
        until=_booked(session),
    )
    assert appointment.slot.provider.name == "Dr. Okafor"
```

See [LiveKit's testing docs](https://docs.livekit.io/testing/unit-tests/) for what else a test can check, such as which tool was called and with what arguments.
