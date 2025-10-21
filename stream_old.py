import asyncio
from typing import Dict
from fastapi import WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState
from logger_config import get_logger
from services.event_emmiter import EventEmitter

logger = get_logger("Stream")

class StreamService(EventEmitter):
    def __init__(self, websocket: WebSocket):
        super().__init__()
        self.ws = websocket
        self.expected_audio_index = 0
        self.audio_buffer: Dict[int, str] = {}
        self.stream_sid = ''
        self.active = True  # Track WebSocket active state
        self.chunk_sequence = 1  # Track chunk sequence for media messages
        self.keep_alive_task = None  # Handle for keep-alive task
        self._last_media_received = None  # Track last media received time

    def set_stream_sid(self, stream_sid: str):
        self.stream_sid = stream_sid
        logger.info(f"Stream SID set to: {stream_sid}")
        # Start keep-alive task when stream SID is set
        if self.active and not self.keep_alive_task:
            self.keep_alive_task = asyncio.create_task(self._send_keep_alive())

    async def health_check(self) -> bool:
        """Check if the stream is healthy based on WebSocket state and activity."""
        try:
            if not self.active or self.ws.application_state == WebSocketState.DISCONNECTED:
                logger.debug(f"Health check failed for stream {self.stream_sid}: WebSocket inactive or disconnected")
                return False
            # Check if media has been received recently (within 10 seconds)
            if self._last_media_received:
                elapsed = asyncio.get_event_loop().time() - self._last_media_received
                if elapsed > 10:
                    logger.warning(f"No media received for {elapsed:.2f} seconds in stream {self.stream_sid}")
                    return False
            return True
        except Exception as e:
            logger.error(f"Error in health_check for stream {self.stream_sid}: {str(e)}")
            return False

    async def send_clear_signal(self):
        """Send a clear signal to stop current audio playback."""
        if not self.active:
            logger.warning(f"Attempted to send clear signal on inactive WebSocket for stream {self.stream_sid}")
            return
        try:
            await self.ws.send_json({
                "event": "clear",
                "streamSid": self.stream_sid,
                "sequenceNumber": str(self.chunk_sequence)
            })
            self.chunk_sequence += 1
            logger.info(f"Sent clear signal for stream {self.stream_sid}")
        except WebSocketDisconnect:
            logger.warning(f"WebSocket disconnected while sending clear signal for stream {self.stream_sid}")
            self.deactivate()
        except Exception as e:
            logger.error(f"Error sending clear signal for stream {self.stream_sid}: {str(e)}")

    async def buffer(self, index: int, audio: str):
        if not self.active:
            logger.warning(f"Attempted to buffer audio on inactive WebSocket for stream {self.stream_sid}")
            return

        try:
            if index is None:
                await self.send_audio(audio)
            elif index == self.expected_audio_index:
                await self.send_audio(audio)
                self.expected_audio_index += 1

                # Process any buffered audio in sequence
                while self.expected_audio_index in self.audio_buffer:
                    buffered_audio = self.audio_buffer[self.expected_audio_index]
                    await self.send_audio(buffered_audio)
                    del self.audio_buffer[self.expected_audio_index]
                    self.expected_audio_index += 1
            else:
                logger.debug(f"Buffering audio for index {index} in stream {self.stream_sid}")
                self.audio_buffer[index] = audio
        except Exception as e:
            logger.error(f"Error buffering audio for stream {self.stream_sid}: {str(e)}")

    def reset(self):
        logger.info(f"Resetting StreamService state for stream {self.stream_sid}")
        self.expected_audio_index = 0
        self.audio_buffer = {}
        self.chunk_sequence = 1

    async def send_audio(self, audio: str):
        if not self.active:
            logger.warning(f"Attempted to send audio on inactive WebSocket for stream {self.stream_sid}")
            return

        try:
            # Send media event with Cloudonix-required fields
            await self.ws.send_json({
                "streamSid": self.stream_sid,
                "event": "media",
                "sequenceNumber": str(self.chunk_sequence),
                "media": {
                    "track": "outbound",  # TTS audio is outbound
                    "chunk": str(self.chunk_sequence),
                    "timestamp": int(asyncio.get_event_loop().time() * 1000),
                    "payload": audio
                }
            })
            self.chunk_sequence += 1
            logger.debug(f"Sent media event for chunk {self.chunk_sequence - 1} in stream {self.stream_sid}")
            await self.emit('audiosent', self.chunk_sequence - 1)  # Emit chunk sequence instead of mark label
        except WebSocketDisconnect:
            logger.warning(f"WebSocket disconnected while sending audio for stream {self.stream_sid}")
            self.deactivate()
        except Exception as e:
            logger.error(f"Error sending audio for stream {self.stream_sid}: {str(e)}")
            self.deactivate()

    async def _send_keep_alive(self):
        """Send periodic keep-alive messages to prevent WebSocket closure."""
        while self.active:
            try:
                await asyncio.sleep(5)  # Send every 5 seconds
                if self.active:
                    await self.ws.send_json({
                        "streamSid": self.stream_sid,
                        "event": "media",
                        "sequenceNumber": str(self.chunk_sequence),
                        "media": {
                            "track": "outbound",
                            "chunk": str(self.chunk_sequence),
                            "timestamp": int(asyncio.get_event_loop().time() * 1000),
                            "payload": ""  # Empty payload for keep-alive
                        }
                    })
                    self.chunk_sequence += 1
                    logger.debug(f"Sent keep-alive message for stream {self.stream_sid}")
            except WebSocketDisconnect:
                logger.warning(f"WebSocket disconnected during keep-alive for stream {self.stream_sid}")
                self.deactivate()
                break
            except Exception as e:
                logger.error(f"Error sending keep-alive for stream {self.stream_sid}: {str(e)}")
                break

    def deactivate(self):
        """Mark the WebSocket as inactive and clean up."""
        if self.active:
            logger.info(f"Deactivating StreamService WebSocket for stream {self.stream_sid}")
            self.active = False
            if self.keep_alive_task:
                self.keep_alive_task.cancel()
                self.keep_alive_task = None
            logger.info(f"StreamService deactivated for stream {self.stream_sid}")

    def stop(self):
        """Stop the stream service and clean up resources."""
        self.deactivate()
        logger.info(f"StreamService stopped for stream {self.stream_sid}")