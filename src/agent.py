"""A medical receptionist voice agent that runs every model on AssemblyAI, with one API key.

Keegan, the receptionist, answers the phone for a (made-up) clinic: takes a new patient's
intake details or looks up a returning patient, finds an open slot and books the appointment.

- Speech-to-text: Universal-3.6 Pro streaming with Medical Mode, which also decides when the
  caller's turn ends
- LLM: LLM Gateway, an OpenAI-compatible API for models from Google, OpenAI, Anthropic and more
- Text-to-speech: AssemblyAI Streaming TTS, with word-level timings

    uv run src/agent.py console   # talk to the agent in your terminal
    uv run src/agent.py dev       # connect it to LiveKit Cloud, for a web or phone frontend
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    JobContext,
    JobProcess,
    RunContext,
    ToolError,
    TurnHandlingOptions,
    cli,
    function_tool,
)
from livekit.agents.beta.tools import EndCallTool
from livekit.plugins import assemblyai, openai, silero

from clinic import (
    CLINIC_NAME,
    PROVIDERS,
    Clinic,
    Patient,
    SlotUnavailableError,
    TimeOfDay,
    VisitType,
)

load_dotenv(Path(__file__).parents[1] / ".env.local")

logger = logging.getLogger("agent")

# Frontends, phone numbers and the Agent Console ask LiveKit for the agent by this name
AGENT_NAME = "receptionist"

# Any model from https://llm-gateway.assemblyai.com/v1/models; see the README for how a few
# compare on time to first token.
LLM_MODEL = "gemma-4-31b"
LLM_GATEWAY_URL = "https://llm-gateway.assemblyai.com/v1"

# A voice id from https://www.assemblyai.com/docs/tts/voices, or one of your cloned voices
TTS_VOICE = "987db62e-a2c2-569a-9c4d-82460cdea1bd"  # Keegan

# The receptionist is named after the voice; if you change one, change the other
RECEPTIONIST_NAME = "Keegan"

# Silero (used for barge-in) should agree with AssemblyAI's own VAD on what counts as speech,
# so both use the STT's default threshold on Universal-3.6 Pro.
VAD_THRESHOLD = 0.2

GREETING = (
    f"Thanks for calling {CLINIC_NAME}, this is {RECEPTIONIST_NAME}. "
    "Are you a new patient, or have you been seen here before?"
)

INSTRUCTIONS = """\
You are {name}, the receptionist for {clinic}, a primary care and cardiology clinic. You're on a \
phone call, and everything you write is spoken aloud by a text-to-speech voice. Today is \
{today}.

How to talk:
- Keep each reply to one or two short sentences, and ask one question at a time.
- Don't use lists, markdown, emojis or abbreviations that sound odd aloud.
- Write dates and times normally, like "Tuesday, October 27 at 9:30 AM".
- When you read back a phone number, member ID or confirmation number, separate every \
character with a space and group them with commas, like "5 1 2, 5 5 5, 0 1 3 4".

Safety comes first. If the caller describes possible emergency symptoms, such as chest pain \
or pressure, trouble breathing, signs of a stroke, severe bleeding or thoughts of harming \
themselves, tell them to hang up and call 911 right away, and don't book anything. Never give \
medical advice, such as about symptoms, diagnoses or medications; offer an appointment instead.

Returning patients: ask for their first and last name and date of birth, then call \
find_patient.

New patients: collect these one at a time, briefly confirming each:
1. First and last name. Ask them to spell the last name.
2. Date of birth.
3. Best callback phone number. Read it back.
4. Insurance carrier and member ID. Read the member ID back.
5. Current medications, with doses.
6. Medication allergies.
Then call register_patient with everything, exactly as the caller confirmed it.

Booking: ask what the visit is for. Primary care visits are with {primary_care}, and new \
patients start with a new patient visit. Heart concerns are a cardiology consultation with \
{cardiology}. Call check_availability, offer the caller at most two of the times it returns, \
and when they choose one, call book_appointment. Then tell them the date, time and \
confirmation number, and ask if there's anything else.

Only use what the tools tell you; never make up patients, times or confirmation numbers. When \
the caller has nothing else, say a short goodbye and call end_call."""


@dataclass
class CallState:
    clinic: Clinic = field(default_factory=Clinic)
    # The patient this call is about, once they've been found or registered
    patient: Patient | None = None


class Receptionist(Agent):
    def __init__(self, today: date | None = None) -> None:
        today = today or date.today()
        super().__init__(
            instructions=INSTRUCTIONS.format(
                name=RECEPTIONIST_NAME,
                clinic=CLINIC_NAME,
                today=f"{today:%A, %B} {today.day}, {today.year}",
                primary_care=_providers_for("follow-up"),
                cardiology=_providers_for("cardiology consultation"),
            ),
            # Lets the receptionist hang up after saying goodbye, but not during the greeting
            tools=[EndCallTool(ignore_on_enter=True)],
        )

    async def on_enter(self) -> None:
        # A fixed greeting is spoken right away, without waiting on the LLM
        self.session.say(GREETING)

    @function_tool
    async def find_patient(
        self, context: RunContext[CallState], first_name: str, last_name: str, date_of_birth: str
    ) -> str:
        """Look up a returning patient's record.

        Args:
            first_name: The patient's first name
            last_name: The patient's last name, as they spelled it
            date_of_birth: The patient's date of birth, as YYYY-MM-DD
        """
        clinic = context.userdata.clinic
        patient = clinic.find_patient(first_name, last_name, _parse_date(date_of_birth))
        if patient is None:
            raise ToolError(
                "No patient has that name and date of birth. Check the spelling and the date "
                "with the caller, or offer to register them as a new patient."
            )
        context.userdata.patient = patient

        appointments = clinic.upcoming_appointments(patient)
        if not appointments:
            return f"Found {patient.full_name}. They have no upcoming appointments."
        booked = "; ".join(f"a {a.visit_type} on {a.slot.describe()}" for a in appointments)
        return f"Found {patient.full_name}. Their upcoming appointments: {booked}."

    @function_tool
    async def register_patient(
        self,
        context: RunContext[CallState],
        first_name: str,
        last_name: str,
        date_of_birth: str,
        phone_number: str,
        insurance_carrier: str,
        insurance_member_id: str,
        medications: list[str],
        allergies: list[str],
    ) -> str:
        """Register a new patient with the intake details they've confirmed.

        Args:
            first_name: The patient's first name
            last_name: The patient's last name, as they spelled it
            date_of_birth: The patient's date of birth, as YYYY-MM-DD
            phone_number: The best callback number, digits only
            insurance_carrier: The name of their insurance company
            insurance_member_id: Their insurance member ID
            medications: Each current medication with its dose, or an empty list if none
            allergies: Each medication allergy, or an empty list if none
        """
        patient = context.userdata.clinic.register_patient(
            first_name=first_name,
            last_name=last_name,
            date_of_birth=_parse_date(date_of_birth),
            phone_number=phone_number,
            insurance_carrier=insurance_carrier,
            insurance_member_id=insurance_member_id,
            medications=medications,
            allergies=allergies,
        )
        context.userdata.patient = patient
        logger.info("registered patient %s", patient.id)
        return f"Registered {patient.full_name} as a new patient."

    @function_tool
    async def check_availability(
        self,
        context: RunContext[CallState],
        visit_type: VisitType,
        earliest_date: str | None = None,
        time_of_day: TimeOfDay | None = None,
    ) -> str:
        """Find the soonest open appointment times for a visit.

        Args:
            visit_type: The kind of visit
            earliest_date: The first day the caller could come in, as YYYY-MM-DD; for a
                specific day, that day
            time_of_day: Whether the caller prefers mornings or afternoons, if they said
        """
        slots = context.userdata.clinic.open_slots(
            visit_type,
            earliest_date=_parse_date(earliest_date) if earliest_date else None,
            time_of_day=time_of_day,
        )
        if not slots:
            return "No openings match. Ask the caller about other days or times."
        return "Open times, by slot ID: " + "; ".join(f"{s.id}: {s.describe()}" for s in slots)

    @function_tool
    async def book_appointment(
        self, context: RunContext[CallState], slot_id: str, visit_type: VisitType, reason: str
    ) -> str:
        """Book the patient into an open slot from check_availability.

        Args:
            slot_id: The slot's ID, such as "S12"
            visit_type: The kind of visit, as passed to check_availability
            reason: Why the patient is coming in, in a few words
        """
        patient = context.userdata.patient
        if patient is None:
            raise ToolError("Find or register the patient before booking.")
        try:
            appointment = context.userdata.clinic.book(patient, slot_id, visit_type, reason)
        except SlotUnavailableError:
            raise ToolError(
                "That slot isn't available. Call check_availability for current times."
            ) from None
        logger.info("booked %s for patient %s", appointment.slot.id, patient.id)
        return (
            f"Booked a {visit_type} on {appointment.slot.describe()}. "
            f"Confirmation number {appointment.confirmation_number}."
        )


def _providers_for(visit_type: VisitType) -> str:
    return " and ".join(p.name for p in PROVIDERS if visit_type in p.visit_types)


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ToolError(f"{value!r} isn't a date; use YYYY-MM-DD.") from None


def llm_gateway(model: str = LLM_MODEL) -> openai.LLM:
    """An LLM served by AssemblyAI's LLM Gateway, through its OpenAI-compatible API."""
    api_key = os.getenv("ASSEMBLYAI_API_KEY")
    if not api_key:
        raise ValueError("Set ASSEMBLYAI_API_KEY in .env.local or the environment")
    return openai.LLM(model=model, base_url=LLM_GATEWAY_URL, api_key=api_key)


server = AgentServer()


def prewarm(proc: JobProcess) -> None:
    proc.userdata["vad"] = silero.VAD.load(activation_threshold=VAD_THRESHOLD)


server.setup_fnc = prewarm


@server.rtc_session(agent_name=AGENT_NAME)
async def entrypoint(ctx: JobContext) -> None:
    ctx.log_context_fields = {"room": ctx.room.name}

    tts = assemblyai.TTS(voice=TTS_VOICE)
    # Open the TTS connection now, so the greeting doesn't wait on the handshake
    tts.prewarm()

    session = AgentSession[CallState](
        userdata=CallState(),
        stt=assemblyai.STT(
            model="universal-3-6-pro",
            # Medical Mode (a paid add-on) for drug names, conditions and dosages
            domain="medical-v1",
            # What the calls are about, and the names they'll mention
            prompt=(
                "Phone call to a primary care and cardiology clinic. A patient gives their "
                "name, date of birth, phone number, insurance details, medications with doses "
                "and allergies, and books an appointment."
            ),
            keyterms_prompt=[CLINIC_NAME, RECEPTIONIST_NAME, *(p.name for p in PROVIDERS)],
            # "balanced" waits up to 1.28 s of silence before ending a turn, so a caller can
            # pause while reading out a phone number or member ID; "min_latency" waits 0.64 s.
            mode="balanced",
            vad_threshold=VAD_THRESHOLD,
        ),
        llm=llm_gateway(),
        tts=tts,
        vad=ctx.proc.userdata["vad"],
        turn_handling=TurnHandlingOptions(
            # Universal-3.6 Pro decides when the caller has finished speaking...
            turn_detection="stt",
            # ...so LiveKit shouldn't add its own delay on top
            endpointing={"min_delay": 0},
            # A cough or an "uh-huh" pauses the reply instead of cutting it off
            interruption={"resume_false_interruption": True},
        ),
        tts_text_transforms=["filter_emoji", "filter_markdown"],
        # When the caller interrupts, keep only the words they heard in the chat history,
        # using the TTS's word timings
        use_tts_aligned_transcript=True,
    )

    async def log_usage() -> None:
        logger.info("usage: %s", session.usage)

    ctx.add_shutdown_callback(log_usage)

    await session.start(agent=Receptionist(), room=ctx.room)


if __name__ == "__main__":
    cli.run_app(server)
