import os
import asyncio
import json
from deepgram import DeepgramClient, LiveOptions, LiveTranscriptionEvents
from logger_config import get_logger
from services.event_emmiter import EventEmitter

logger = get_logger("Transcription")

class TranscriptionService(EventEmitter):
    def __init__(self):
        super().__init__()
        self.client = DeepgramClient(os.getenv("DEEPGRAM_API_KEY"))
        self.deepgram_live = None
        self.final_result = ""
        self.speech_final = False
        self.stream_sid = None
        self.is_connected = False
        self.keep_alive_task = None

    def set_stream_sid(self, stream_id):
        self.stream_sid = stream_id

    def get_stream_sid(self):
        return self.stream_sid

    async def connect(self):
        try:
            self.deepgram_live = self.client.listen.asynclive.v("1")
            await self.deepgram_live.start(LiveOptions(
                model="nova-2", 
                language="en-US", 
                encoding="mulaw",
                sample_rate=8000,
                channels=1,
                punctuate=True,
                interim_results=True,
                endpointing=200,
                utterance_end_ms=1000
            ))
            self.is_connected = True
            logger.info(f"Deepgram WebSocket connected for stream {self.stream_sid}")
            self.keep_alive_task = asyncio.create_task(self._send_keep_alive())
            self.deepgram_live.on(LiveTranscriptionEvents.Transcript, self.handle_transcription)
            self.deepgram_live.on(LiveTranscriptionEvents.Error, self.handle_error)
            self.deepgram_live.on(LiveTranscriptionEvents.Close, self.handle_close)
            self.deepgram_live.on(LiveTranscriptionEvents.Warning, self.handle_warning)
            self.deepgram_live.on(LiveTranscriptionEvents.Metadata, self.handle_metadata)
            self.deepgram_live.on(LiveTranscriptionEvents.UtteranceEnd, self.handle_utterance_end)
        except Exception as e:
            self.is_connected = False
            logger.error(f"Failed to connect to Deepgram for stream {self.stream_sid}: {str(e)}", exc_info=True)
            raise

    async def _send_keep_alive(self):
        """Send keep-alive messages to Deepgram every 5 seconds."""
        while self.is_connected and self.deepgram_live:
            try:
                # Serialize JSON and send as text
                keep_alive_message = json.dumps({"type": "KeepAlive"})
                await self.deepgram_live.send(keep_alive_message.encode('utf-8'))
                logger.debug(f"Sent Deepgram keep-alive message for stream {self.stream_sid}")
                await asyncio.sleep(5)
            except Exception as e:
                logger.error(f"Failed to send keep-alive for stream {self.stream_sid}: {str(e)}", exc_info=True)
                self.is_connected = False
                await self.emit('error', str(e))
                break

    async def handle_utterance_end(self, self_obj, utterance_end):
        try:
            if not self.speech_final and self.final_result.strip():
                logger.info(f"UtteranceEnd received for stream {self.stream_sid}, emitting text: {self.final_result}")
                await self.emit('transcription', self.final_result)
                self.final_result = ''
                self.speech_final = True
        except Exception as e:
            logger.error(f"Error handling utterance end for stream {self.stream_sid}: {str(e)}", exc_info=True)

    async def handle_transcription(self, self_obj, result):
        try:
            alternatives = result.channel.alternatives if hasattr(result, 'channel') else []
            text = alternatives[0].transcript if alternatives else ""
            if result.is_final and text.strip():
                self.final_result += f" {text}"
                if result.speech_final:
                    self.speech_final = True
                    logger.info(f"Final transcription for stream {self.stream_sid}: {self.final_result}")
                    await self.emit('transcription', self.final_result)
                    self.final_result = ''
                else:
                    self.speech_final = False
            else:
                if text.strip():
                    logger.debug(f"Interim utterance for stream {self.stream_sid}: {text}")
                    await self.emit('utterance', text, self.stream_sid)
        except Exception as e:
            logger.error(f"Error handling transcription for stream {self.stream_sid}: {str(e)}", exc_info=True)

    async def handle_error(self, self_obj, error):
        logger.error(f"Deepgram error for stream {self.stream_sid}: {error}")
        self.is_connected = False
        await self.emit('error', error)

    async def handle_warning(self, self_obj, warning):
        logger.info(f"Deepgram warning for stream {self.stream_sid}: {warning}")

    async def handle_metadata(self, self_obj, metadata):
        logger.info(f"Deepgram metadata for stream {self.stream_sid}: {metadata}")

    async def handle_close(self, self_obj, close):
        logger.info(f"Deepgram connection closed for stream {self.stream_sid}")
        self.is_connected = False
        await self.emit('close', close)

    async def send(self, payload: bytes):
        try:
            if not payload:
                logger.warning(f"Empty audio payload for stream {self.stream_sid}")
                return
            if self.is_connected and self.deepgram_live:
                await self.deepgram_live.send(payload)
                logger.debug(f"Sent audio data to Deepgram for stream {self.stream_sid}, length: {len(payload)}")
            else:
                logger.error(f"Cannot send audio: Deepgram not connected for stream {self.stream_sid}")
        except Exception as e:
            logger.error(f"Error sending audio to Deepgram for stream {self.stream_sid}: {str(e)}", exc_info=True)
            self.is_connected = False
            await self.emit('error', str(e))

    async def disconnect(self):
        if hasattr(self, 'is_disconnecting') and self.is_disconnecting:
            logger.debug(f"Already disconnecting Deepgram for stream {self.stream_sid}, skipping")
            return
        self.is_disconnecting = True
        try:
            if self.keep_alive_task:
                self.keep_alive_task.cancel()
                self.keep_alive_task = None
            if self.deepgram_live:
                await self.deepgram_live.finish()
                self.deepgram_live = None
            self.is_connected = False
            logger.info(f"Disconnected from Deepgram for stream {self.stream_sid}")
        except Exception as e:
            logger.error(f"Error disconnecting from Deepgram for stream {self.stream_sid}: {str(e)}", exc_info=True)
        finally:
            self.is_disconnecting = False