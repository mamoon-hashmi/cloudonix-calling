import asyncio
import base64
import json
import os
from collections import deque
from typing import Dict
import dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from logger_config import get_logger
from services.call_context import CallContext
from services.llm_service import LLMFactory
from services.stream_service import StreamService
from services.transcription_service import TranscriptionService
from services.tts_service import TTSFactory

dotenv.load_dotenv()
app = FastAPI()
logger = get_logger("App")

# Global dictionary to store call contexts (should be replaced with a database in production)
global call_contexts
call_contexts = {}

# Route for Cloudonix CXML to initiate stream
@app.post("/incoming")
async def incoming_call() -> HTMLResponse:
    server = os.environ.get("SERVER")
    response = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Connect>
        <Stream url="wss://{server}/connection" track="both_tracks" statusCallback="https://{server}/stream_status"/>
    </Connect>
</Response>"""
    return HTMLResponse(content=response, status_code=200)

# Status callback endpoint for Cloudonix stream events
@app.post("/stream_status")
async def stream_status(request: Dict):
    """Handle Cloudonix stream status callbacks."""
    logger.info(f"Stream status callback: {request}")
    stream_event = request.get("StreamEvent")
    stream_sid = request.get("StreamSid")
    call_sid = request.get("CallSid")
    error = request.get("StreamError")
    if stream_event == "stream-error" and error:
        logger.error(f"Stream error for {stream_sid} (CallSid: {call_sid}): {error}")
    return {"status": "received"}

# WebSocket route for Cloudonix stream
@app.websocket("/connection")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    llm_service_name = os.getenv("LLM_SERVICE", "openai")
    tts_service_name = os.getenv("TTS_SERVICE", "deepgram")
    logger.info(f"Using LLM service: {llm_service_name}")
    logger.info(f"Using TTS service: {tts_service_name}")
    llm_service = LLMFactory.get_llm_service(llm_service_name, CallContext())
    stream_service = StreamService(websocket)
    transcription_service = TranscriptionService()
    tts_service = TTSFactory.get_tts_service(tts_service_name)
    
    sent_chunks = deque(maxlen=100)  # Track sent chunk sequences instead of marks
    interaction_count = 0
    await transcription_service.connect()
    
    async def process_media(msg):
        await transcription_service.send(base64.b64decode(msg['media']['payload']))

    async def handle_transcription(text):
        nonlocal interaction_count
        if not text:
            return
        logger.info(f"Interaction {interaction_count} – STT -> LLM: {text}")
        await llm_service.completion(text, interaction_count)
        interaction_count += 1

    async def handle_llm_reply(llm_reply, icount):
        logger.info(f"Interaction {icount}: LLM -> TTS: {llm_reply['partialResponse']}")
        await tts_service.generate(llm_reply, icount)

    async def handle_speech(response_index, audio, label, icount):
        logger.info(f"Interaction {icount}: TTS -> CLOUDONIX: {label}")
        await stream_service.buffer(response_index, audio)

    async def handle_audio_sent(chunk_sequence):
        sent_chunks.append(chunk_sequence)
        logger.debug(f"Audio sent with chunk sequence: {chunk_sequence}")

    async def handle_utterance(text, stream_sid):
        try:
            if len(sent_chunks) > 0 and text.strip():
                logger.info("Interruption detected, clearing system.")
                await websocket.send_json({
                    "streamSid": stream_sid,
                    "event": "clear"
                })
                # Reset states
                stream_service.reset()
                llm_service.reset()
                sent_chunks.clear()
        except Exception as e:
            logger.error(f"Error while handling utterance: {e}")

    transcription_service.on('utterance', handle_utterance)
    transcription_service.on('transcription', handle_transcription)
    llm_service.on('llmreply', handle_llm_reply)
    tts_service.on('speech', handle_speech)
    stream_service.on('audiosent', handle_audio_sent)

    # Queue for incoming WebSocket messages
    message_queue = asyncio.Queue()

    async def websocket_listener():
        try:
            while True:
                data = await websocket.receive_text()
                await message_queue.put(json.loads(data))
        except WebSocketDisconnect:
            logger.info("WebSocket disconnected")
            stream_service.deactivate()

    async def message_processor():
        while True:
            msg = await message_queue.get()
            if msg['event'] == 'connected':
                logger.info("Cloudonix -> WebSocket connected")
            elif msg['event'] == 'start':
                stream_sid = msg['streamSid']
                call_sid = msg['start']['callSid']
                # Verify media format
                media_format = msg['start'].get('mediaFormat', {})
                logger.info(f"Media format: {media_format}")
                if media_format.get('encoding') != 'audio/x-mulaw' or \
                   media_format.get('sampleRate') != 8000 or \
                   media_format.get('channels') != 1:
                    logger.warning("Media format may not match expected: audio/x-mulaw, 8000 Hz, 1 channel")
                
                call_context = CallContext()
                if call_sid not in call_contexts:
                    # Inbound call
                    call_context.system_message = os.environ.get("SYSTEM_MESSAGE")
                    call_context.initial_message = os.environ.get("INITIAL_MESSAGE")
                    call_context.call_sid = call_sid
                    call_contexts[call_sid] = call_context
                else:
                    # Call from UI, reuse the existing context
                    call_context = call_contexts[call_sid]

                llm_service.set_call_context(call_context)
                stream_service.set_stream_sid(stream_sid)
                transcription_service.set_stream_sid(stream_sid)
                logger.info(f"Cloudonix -> Starting Media Stream for {stream_sid}")
                await tts_service.generate({
                    "partialResponseIndex": None,
                    "partialResponse": call_context.initial_message
                }, 1)
            elif msg['event'] == 'media':
                asyncio.create_task(process_media(msg))
            elif msg['event'] == 'stop':
                logger.info(f"Cloudonix -> Media stream {stream_sid} ended.")
                stream_service.deactivate()
                break
            message_queue.task_done()

    try:
        listener_task = asyncio.create_task(websocket_listener())
        processor_task = asyncio.create_task(message_processor())
        await asyncio.gather(listener_task, processor_task)
    except asyncio.CancelledError:
        logger.info("Tasks cancelled")
        stream_service.deactivate()
    finally:
        await transcription_service.disconnect()

# API route to initiate a call via UI
@app.post("/start_call")
async def start_call(request: Dict[str, str]):
    """Initiate a call with custom system and initial messages."""
    to_number = request.get("to_number")
    system_message = request.get("system_message")
    initial_message = request.get("initial_message")
    logger.info(f"Initiating call to {to_number}")
    service_url = f"https://{os.getenv('SERVER')}/incoming"
    if not to_number:
        return {"error": "Missing 'to_number' in request"}
    
    try:
        # Placeholder for Cloudonix API call initiation
        call_sid = f"cloudonix_{to_number}_{int(asyncio.get_event_loop().time())}"
        call_context = CallContext()
        call_contexts[call_sid] = call_context
        
        call_context.system_message = system_message or os.getenv("SYSTEM_MESSAGE")
        call_context.initial_message = initial_message or os.getenv("INITIAL_MESSAGE")
        call_context.call_sid = call_sid
        return {"call_sid": call_sid}
    except Exception as e:
        logger.error(f"Error initiating call: {str(e)}")
        return {"error": f"Failed to initiate call: {str(e)}"}

# API route to get the status of a call
@app.get("/call_status/{call_sid}")
async def get_call_status(call_sid: str):
    """Get the status of a call."""
    try:
        call_context = call_contexts.get(call_sid)
        if call_context:
            return {"status": "active"}
        return {"status": "completed"}
    except Exception as e:
        logger.error(f"Error fetching call status: {str(e)}")
        return {"error": f"Failed to fetch call status: {str(e)}"}

# API route to end a call
@app.post("/end_call")
async def end_call(request: Dict[str, str]):
    """End a call."""
    try:
        call_sid = request.get("call_sid")
        if call_sid in call_contexts:
            del call_contexts[call_sid]
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Error ending call {str(e)}")
        return {"error": f"Failed to end requested call: {str(e)}"}

# API call to get the transcript for a specific call
@app.get("/transcript/{call_sid}")
async def get_transcript(call_sid: str):
    """Get the entire transcript for a specific call."""
    call_context = call_contexts.get(call_sid)
    if not call_context:
        logger.info(f"[GET] Call not found for call SID: {call_sid}")
        return {"error": "Call not found"}
    return {"transcript": call_context.user_context}

# API route to get all call transcripts
@app.get("/all_transcripts")
async def get_all_transcripts():
    """Get a list of all current call transcripts."""
    try:
        transcript_list = []
        for call_sid, context in call_contexts.items():
            transcript_list.append({
                "call_sid": call_sid,
                "transcript": context.user_context,
            })
        return {"transcripts": transcript_list}
    except Exception as e:
        logger.error(f"Error fetching all transcripts: {str(e)}")
        return {"error": f"Failed to fetch all transcripts: {str(e)}"}

if __name__ == "__main__":
    import uvicorn
    logger.info("Starting server...")
    logger.info(f"Backend server address set to: {os.getenv('SERVER')}")
    port = int(os.getenv("PORT", 3000))
    uvicorn.run(app, host="0.0.0.0", port=port)