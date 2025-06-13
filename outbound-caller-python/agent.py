from __future__ import annotations

import asyncio
import logging
from dotenv import load_dotenv
import json
import os
from typing import Any

from livekit import rtc, api
from livekit.agents import (
    AgentSession,
    Agent,
    JobContext,
    function_tool,
    RunContext,
    get_job_context,
    cli,
    WorkerOptions,
    RoomInputOptions,
)
from livekit.plugins import (
    deepgram,
    openai,
    cartesia,
    silero,
    noise_cancellation,  # noqa: F401
)
from livekit.plugins.turn_detector.english import EnglishModel


# load environment variables, this is optional, only used for local development
load_dotenv(dotenv_path=".env.local")
logger = logging.getLogger("outbound-caller")
logger.setLevel(logging.INFO)


outbound_trunk_id = os.getenv("SIP_OUTBOUND_TRUNK_ID")
logger.info(f"Using outbound_trunk_id: {outbound_trunk_id}")

class OutboundCaller(Agent):
    def __init__(
        self,
        *,
        name: str,
        appointment_time: str,
        dial_info: dict[str, Any],
    ):
        super().__init__(
            instructions="""
You are an empathetic AI voice assistant for Moolchand Hospital, calling patients recently discharged after surgery for a follow-up check. Your goals are to:
- Greet the patient by name and introduce yourself as the hospital's AI assistant.
- Inquire about their recovery and how they are feeling since discharge.
- Respond empathetically to both positive and negative feedback about their health.
- Ask if they are experiencing any discomfort, pain, or symptoms, and suggest a follow-up consultation if needed.
- Collect feedback about their last hospital visit, responding positively or constructively as appropriate.
- Offer to schedule a follow-up appointment with their doctor if needed, and confirm details if the patient agrees.
- Optionally, promote a wellness program for post-surgery patients and offer to send more details if interested.
- Close the call warmly, reminding the patient they can reach out for help at any time.

Scripted flow:
1. Greeting: "Hello Mr. Rahul Sharma, this is Moolchand Hospital's AI assistant calling to check in on your health after your recent knee replacement surgery. How are you feeling today?"
2. Health Inquiry: "We hope your recovery is going smoothly. Could you share how you've been feeling since your discharge?"
   - If positive: "That's wonderful to hear! Recovery is an important step, and we're here to support you throughout the process."
   - If concerns: "I'm sorry to hear that. Could you please tell me more about the issue you're facing? This will help us guide you better."
3. Follow-Up: "Are you experiencing any discomfort, pain, or other symptoms that we should be aware of?"
   - If symptoms: "Thank you for sharing that. Based on what you've mentioned, it might be a good idea to schedule a follow-up consultation with Dr. Priya Mehra to ensure everything is on track."
4. Feedback: "May I also ask about your experience during your last visit to Moolchand Hospital? Was there anything we could have done better?"
   - If positive: "That's great to hear! We're always striving to provide the best care possible."
   - If constructive: "Thank you for sharing your thoughts. I'll make sure your feedback reaches the right team so we can improve."
5. Service Recommendation: "Based on our conversation, I'd recommend scheduling a follow-up appointment with Dr. Priya Mehra. Would you like me to book it for you now?"
   - If yes: "Perfect! I'll book an appointment for next Monday at 11am with Dr. Priya Mehra. You'll receive a confirmation via SMS shortly."
   - If no: "No problem at all. If you change your mind or need assistance later, feel free to contact us at 1800-123-4567."
6. Wellness Program (optional): "By the way, we're also offering a wellness program designed for post-surgery patients like yourself. It includes guided physiotherapy sessions and nutritional counseling to help speed up recovery. Would you like more details?"
   - If yes: "I'll send you all the details via WhatsApp or email, and you can enroll at your convenience."
7. Closing: "Thank you for taking the time to speak with me today, Mr. Sharma. Your health and well-being are very important to us. If there's anything else we can assist you with, please don't hesitate to reach out. Have a great day! Take care."

Always be empathetic, professional, and supportive. Personalize the conversation with the patient's name and reference their recent surgery. If the patient requests a human agent, confirm and transfer the call. Allow the user to end the conversation at any time.
"""
        )
        # keep reference to the participant for transfers
        self.participant: rtc.RemoteParticipant | None = None

        self.dial_info = dial_info

    def set_participant(self, participant: rtc.RemoteParticipant):
        self.participant = participant

    async def hangup(self):
        """Helper function to hang up the call by deleting the room"""

        job_ctx = get_job_context()
        await job_ctx.api.room.delete_room(
            api.DeleteRoomRequest(
                room=job_ctx.room.name,
            )
        )

    @function_tool()
    async def transfer_call(self, ctx: RunContext):
        """Transfer the call to a human agent, called after confirming with the user"""

        transfer_to = self.dial_info["transfer_to"]
        if not transfer_to:
            return "cannot transfer call"

        logger.info(f"transferring call to {transfer_to}")

        # let the message play fully before transferring
        await ctx.session.generate_reply(
            instructions="let the user know you'll be transferring them"
        )

        job_ctx = get_job_context()
        try:
            await job_ctx.api.sip.transfer_sip_participant(
                api.TransferSIPParticipantRequest(
                    room_name=job_ctx.room.name,
                    participant_identity=self.participant.identity,
                    transfer_to=f"tel:{transfer_to}",
                )
            )

            logger.info(f"transferred call to {transfer_to}")
        except Exception as e:
            logger.error(f"error transferring call: {e}")
            await ctx.session.generate_reply(
                instructions="there was an error transferring the call."
            )
            await self.hangup()

    @function_tool()
    async def end_call(self, ctx: RunContext):
        """Called when the user wants to end the call"""
        logger.info(f"ending the call for {self.participant.identity}")

        # let the agent finish speaking
        current_speech = ctx.session.current_speech
        if current_speech:
            await current_speech.wait_for_playout()

        await self.hangup()

    @function_tool()
    async def look_up_availability(
        self,
        ctx: RunContext,
        date: str,
    ):
        """Called when the user asks about alternative appointment availability

        Args:
            date: The date of the appointment to check availability for
        """
        logger.info(
            f"looking up availability for {self.participant.identity} on {date}"
        )
        await asyncio.sleep(3)
        return {
            "available_times": ["1pm", "2pm", "3pm"],
        }

    @function_tool()
    async def confirm_appointment(
        self,
        ctx: RunContext,
        date: str,
        time: str,
    ):
        """Called when the user confirms their appointment on a specific date.
        Use this tool only when they are certain about the date and time.

        Args:
            date: The date of the appointment
            time: The time of the appointment
        """
        logger.info(
            f"confirming appointment for {self.participant.identity} on {date} at {time}"
        )
        return "reservation confirmed"

    @function_tool()
    async def detected_answering_machine(self, ctx: RunContext):
        """Called when the call reaches voicemail. Use this tool AFTER you hear the voicemail greeting"""
        logger.info(f"detected answering machine for {self.participant.identity}")
        await self.hangup()


async def entrypoint(ctx: JobContext):
    logger.info(f"connecting to room {ctx.room.name}")
    await ctx.connect()

    # when dispatching the agent, we'll pass it the approriate info to dial the user
    # dial_info is a dict with the following keys:
    # - phone_number: the phone number to dial
    # - transfer_to: the phone number to transfer the call to when requested
    dial_info = json.loads(ctx.job.metadata)
    participant_identity = phone_number = dial_info["phone_number"]

    # look up the user's phone number and appointment details
    agent = OutboundCaller(
        name="Jayden",
        appointment_time="next Tuesday at 3pm",
        dial_info=dial_info,
    )

    # the following uses GPT-4o, Deepgram and Cartesia
    session = AgentSession(
        turn_detection=EnglishModel(),
        vad=silero.VAD.load(),
        stt=deepgram.STT(),
        # you can also use OpenAI's TTS with openai.TTS()
        tts=cartesia.TTS(),
        llm=openai.LLM(model="gpt-4o"),
        # you can also use a speech-to-speech model like OpenAI's Realtime API
        # llm=openai.realtime.RealtimeModel()
    )

    # start the session first before dialing, to ensure that when the user picks up
    # the agent does not miss anything the user says
    session_started = asyncio.create_task(
        session.start(
            agent=agent,
            room=ctx.room,
            room_input_options=RoomInputOptions(
                # enable Krisp background voice and noise removal
                noise_cancellation=noise_cancellation.BVCTelephony(),
            ),
        )
    )

    # `create_sip_participant` starts dialing the user
    try:
        await ctx.api.sip.create_sip_participant(
            api.CreateSIPParticipantRequest(
                room_name=ctx.room.name,
                sip_trunk_id=outbound_trunk_id,
                sip_call_to=phone_number,
                sip_number="+17345214522",
                participant_identity=participant_identity,
                # function blocks until user answers the call, or if the call fails
                wait_until_answered=True,
            )
        )

        # wait for the agent session start and participant join
        await session_started
        participant = await ctx.wait_for_participant(identity=participant_identity)
        logger.info(f"participant joined: {participant.identity}")

        agent.set_participant(participant)

    except api.TwirpError as e:
        logger.error(
            f"error creating SIP participant: {e.message}, "
            f"SIP status: {e.metadata.get('sip_status_code')} "
            f"{e.metadata.get('sip_status')}"
        )
        ctx.shutdown()


if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            agent_name="outbound-caller",
        )
    )
