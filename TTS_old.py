import base64
import os
from abc import ABC, abstractmethod
from typing import Any, Dict
import aiohttp
import numpy as np
from dotenv import load_dotenv
from logger_config import get_logger
from services.event_emmiter import EventEmitter
import asyncio
import time
load_dotenv()
logger = get_logger("TTS")
class AbstractTTSService(EventEmitter, ABC):
    """Abstract base class for TTS services, extending EventEmitter."""
    @abstractmethod
    async def generate(self, llm_reply: Dict[str, Any], interaction_count: int) -> None:
        """Generate TTS audio from an LLM reply and emit speech events."""
        pass
    @abstractmethod
    async def set_voice(self, voice_id: str) -> None:
        """Set the voice ID for the TTS service."""
        pass
    @abstractmethod
    async def disconnect(self) -> None:
        """Disconnect the TTS service, if required."""
        pass
    @abstractmethod
    async def stop(self) -> None:
        """Interrupt/stop any ongoing audio generation/streaming immediately."""
        pass
class ElevenLabsTTS(AbstractTTSService):
    """TTS service implementation for ElevenLabs."""
    def __init__(self):
        super().__init__()
        self.voice_id = os.getenv("ELEVENLABS_VOICE_ID")
        self.api_key = os.getenv("ELEVENLABS_API_KEY")
        self.model_id = os.getenv("ELEVENLABS_MODEL_ID")
        self.speech_buffer = {}
        self._stop_event = asyncio.Event()
        self.pre_buffer_chunks = 10  # ~200ms buffer; adjust based on testing
    async def set_voice(self, voice_id: str) -> None:
        """Set the ElevenLabs voice ID."""
        self.voice_id = voice_id
        logger.info(f"Set ElevenLabs voice to {voice_id}")
    async def disconnect(self) -> None:
        """No explicit disconnection required for ElevenLabs."""
        logger.debug("ElevenLabsTTS service disconnected")
    async def stop(self) -> None:
        """Signal any running generate() to stop as soon as possible."""
        logger.debug("ElevenLabsTTS stop requested")
        self._stop_event.set()
        # emit an event so other parts can know it stopped
        await self.emit('speech_stopped')
    async def generate(self, llm_reply: Dict[str, Any], interaction_count: int) -> None:
        """Generate streaming TTS audio from ElevenLabs and emit speech events."""
        # clear previous stop flag at start of a new generation
        self._stop_event.clear()
        partial_response_index = llm_reply.get('partialResponseIndex')
        partial_response = llm_reply.get('partialResponse')
        if not partial_response:
            logger.debug(f"No partial response for interaction {interaction_count}")
            return
        try:
            url = f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}/stream"
            headers = {
                "xi-api-key": self.api_key,
                "Content-Type": "application/json",
                "Accept": "audio/mulaw"
            }
            params = {
                "output_format": "ulaw_8000",
                "optimize_streaming_latency": 2  # Lowered for better latency
            }
            data = {
                "model_id": self.model_id,
                "text": partial_response
            }
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
                async with session.post(url, headers=headers, params=params, json=data) as response:
                    if response.status == 200:
                        chunk_size = 160  # 20ms at 8000 Hz mu-law
                        buffer = b""
                        response_index = 0
                        start_time = time.monotonic()  # Track start for rate limiting
                        expected_time = 0.0  # Cumulative expected time for chunks
                        pre_buffer = []  # List to hold initial chunks
                        async for chunk in response.content.iter_chunked(1024):
                            if self._stop_event.is_set():
                                logger.debug(f"ElevenLabsTTS generation interrupted at chunk {response_index} for interaction {interaction_count}")
                                return
                            buffer += chunk
                            while len(buffer) >= chunk_size:
                                audio_chunk = buffer[:chunk_size]
                                buffer = buffer[chunk_size:]
                                audio_base64 = base64.b64encode(audio_chunk).decode('utf-8')
                                chunk_args = (partial_response_index, audio_base64, partial_response, interaction_count)
                                chunk_start = time.monotonic()
                                logger.debug(f"Processing TTS chunk {response_index} for interaction {interaction_count}, size={len(audio_chunk)} bytes")
                                if len(pre_buffer) < self.pre_buffer_chunks:
                                    pre_buffer.append(chunk_args)
                                else:
                                    # Emit pre-buffered chunks if full
                                    if pre_buffer:
                                        for args in pre_buffer:
                                            # Rate limit
                                            current_time = time.monotonic() - start_time
                                            expected_time += 0.02
                                            if current_time < expected_time:
                                                await asyncio.sleep(expected_time - current_time)
                                            await self.emit('speech', *args)
                                        pre_buffer = []
                                    # Emit current
                                    current_time = time.monotonic() - start_time
                                    expected_time += 0.02
                                    if current_time < expected_time:
                                        await asyncio.sleep(expected_time - current_time)
                                    await self.emit('speech', *chunk_args)
                                response_index += 1
                                logger.debug(f"Chunk {response_index} processed in {time.monotonic() - chunk_start:.4f}s")
                        # Handle remaining buffer
                        if buffer and not self._stop_event.is_set():
                            logger.debug(f"Padding partial TTS chunk of {len(buffer)} bytes for interaction {interaction_count}")
                            audio_chunk = buffer + b'\xff' * (chunk_size - len(buffer))
                            audio_base64 = base64.b64encode(audio_chunk).decode('utf-8')
                            chunk_args = (partial_response_index, audio_base64, partial_response, interaction_count)
                            if pre_buffer:
                                pre_buffer.append(chunk_args)
                        # Emit any remaining pre_buffer
                        if pre_buffer and not self._stop_event.is_set():
                            for args in pre_buffer:
                                current_time = time.monotonic() - start_time
                                expected_time += 0.02
                                if current_time < expected_time:
                                    await asyncio.sleep(expected_time - current_time)
                                await self.emit('speech', *args)
                    else:
                        logger.error(f"ElevenLabs TTS error: {await response.text()}")
        except Exception as err:
            logger.error(f"Error in ElevenLabs TTS service: {str(err)}", exc_info=True)
class DeepgramTTS(AbstractTTSService):
    """TTS service implementation for Deepgram."""
    def __init__(self):
        super().__init__()
        self.api_key = os.getenv("DEEPGRAM_API_KEY")
        self.model = os.getenv("DEEPGRAM_MODEL", "aura-asteria-en")
        self._stop_event = asyncio.Event()
        self.pre_buffer_chunks = 10  # ~200ms buffer; adjust based on testing
    async def set_voice(self, voice_id: str) -> None:
        """Log attempt to set voice; Deepgram uses models for voice selection."""
        self.model = voice_id  # Assuming voice_id corresponds to a Deepgram model name
        logger.info(f"Set Deepgram model/voice to {voice_id}")
    async def disconnect(self) -> None:
        """No explicit disconnection required for Deepgram."""
        logger.debug("DeepgramTTS service disconnected")
    async def stop(self) -> None:
        """Signal any running generate() to stop as soon as possible."""
        logger.debug("DeepgramTTS stop requested")
        self._stop_event.set()
        await self.emit('speech_stopped')
    async def generate(self, llm_reply: Dict[str, Any], interaction_count: int) -> None:
        """Generate streaming TTS audio from Deepgram and emit speech events in 160-byte chunks."""
        # clear previous stop flag at start of a new generation
        self._stop_event.clear()
        partial_response_index = llm_reply.get('partialResponseIndex')
        partial_response = llm_reply.get('partialResponse')
        if not partial_response:
            logger.debug(f"No partial response for interaction {interaction_count}")
            return
        try:
            url = "https://api.deepgram.com/v1/speak"
            headers = {
                "Authorization": f"Token {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "audio/mulaw"
            }
            params = {
                "model": self.model,
                "encoding": "mulaw",
                "sample_rate": 8000,
                "container": "none"
            }
            data = {
                "text": partial_response
            }
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
                async with session.post(url, headers=headers, params=params, json=data) as response:
                    if response.status == 200:
                        chunk_size = 160  # 20ms at 8000 Hz mu-law
                        buffer = b""
                        response_index = 0
                        start_time = time.monotonic()  # Track start for rate limiting
                        expected_time = 0.0  # Cumulative expected time for chunks
                        pre_buffer = []  # List to hold initial chunks
                        async for chunk in response.content.iter_chunked(1024):  # Fetch larger chunks from server, then split locally
                            if self._stop_event.is_set():
                                logger.debug(f"DeepgramTTS generation interrupted at chunk {response_index} for interaction {interaction_count}")
                                return
                            buffer += chunk
                            while len(buffer) >= chunk_size:
                                audio_chunk = buffer[:chunk_size]
                                buffer = buffer[chunk_size:]
                                audio_base64 = base64.b64encode(audio_chunk).decode('utf-8')
                                chunk_args = (partial_response_index, audio_base64, partial_response, interaction_count)
                                chunk_start = time.monotonic()
                                logger.debug(f"Processing TTS chunk {response_index} for interaction {interaction_count}, size={len(audio_chunk)} bytes")
                                if len(pre_buffer) < self.pre_buffer_chunks:
                                    pre_buffer.append(chunk_args)
                                else:
                                    # Emit pre-buffered chunks if full
                                    if pre_buffer:
                                        for args in pre_buffer:
                                            # Rate limit
                                            current_time = time.monotonic() - start_time
                                            expected_time += 0.02
                                            if current_time < expected_time:
                                                await asyncio.sleep(expected_time - current_time)
                                            await self.emit('speech', *args)
                                        pre_buffer = []
                                    # Emit current
                                    current_time = time.monotonic() - start_time
                                    expected_time += 0.02
                                    if current_time < expected_time:
                                        await asyncio.sleep(expected_time - current_time)
                                    await self.emit('speech', *chunk_args)
                                response_index += 1
                                logger.debug(f"Chunk {response_index} processed in {time.monotonic() - chunk_start:.4f}s")
                        # Handle remaining buffer
                        if buffer and not self._stop_event.is_set():
                            logger.debug(f"Padding partial TTS chunk of {len(buffer)} bytes for interaction {interaction_count}")
                            audio_chunk = buffer + b'\xff' * (chunk_size - len(buffer))
                            audio_base64 = base64.b64encode(audio_chunk).decode('utf-8')
                            chunk_args = (partial_response_index, audio_base64, partial_response, interaction_count)
                            if pre_buffer:
                                pre_buffer.append(chunk_args)
                        # Emit any remaining pre_buffer
                        if pre_buffer and not self._stop_event.is_set():
                            for args in pre_buffer:
                                current_time = time.monotonic() - start_time
                                expected_time += 0.02
                                if current_time < expected_time:
                                    await asyncio.sleep(expected_time - current_time)
                                await self.emit('speech', *args)
                    else:
                        logger.error(f"Deepgram TTS error: {await response.text()}")
        except Exception as e:
            logger.error(f"Error in Deepgram TTS generation: {str(e)}", exc_info=True)
class TTSFactory:
    """Factory to create TTS service instances."""
    @staticmethod
    def get_tts_service(service_name: str) -> AbstractTTSService:
        """Create and return a TTS service instance based on the service name."""
        if service_name.lower() == "elevenlabs":
            return ElevenLabsTTS()
        elif service_name.lower() == "deepgram":
            return DeepgramTTS()
        else:
            raise ValueError(f"Unsupported TTS service: {service_name}")
# Usage in main application
tts_service_name = os.getenv("TTS_SERVICE", "deepgram")  # Default to deepgram
tts_service = TTSFactory.get_tts_service(tts_service_name)