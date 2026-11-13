"""
Django Channels WebSocket consumer for streaming real-time voice audio blobs.
Handles audio ingestion, faster-whisper transcription, confidence check,
and streaming RAG answer back to the client.
"""

import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import sync_to_async

from apps.voice.audio_utils import transcribe_audio_bytes
from apps.rag_engine.services import DRCRagService

logger = logging.getLogger(__name__)


class VoiceAssistantConsumer(AsyncWebsocketConsumer):
    """
    WebSocket endpoint: /ws/voice/
    Accepts:
    - Binary audio chunks (WebM/WAV)
    - JSON control messages: {"action": "start", "language": "fr"}
    """
    async def connect(self):
        self.language = "fr"
        self.audio_buffer = bytearray()
        await self.accept()
        await self.send(text_data=json.dumps({
            "type": "connection_established",
            "message": "Canal audio WebSocket connecté à l'assistant officiel RDC."
        }))

    async def disconnect(self, close_code):
        self.audio_buffer.clear()
        logger.info(f"Voice WebSocket disconnected with code {close_code}")

    async def receive(self, text_data=None, bytes_data=None):
        if bytes_data:
            # Accumulate raw audio chunk
            self.audio_buffer.extend(bytes_data)

        elif text_data:
            try:
                payload = json.loads(text_data)
                action = payload.get("action")

                if action == "config":
                    self.language = payload.get("language", "fr")
                    await self.send(text_data=json.dumps({
                        "type": "config_updated",
                        "language": self.language
                    }))

                elif action == "finish_recording":
                    if not self.audio_buffer:
                        await self.send(text_data=json.dumps({
                            "type": "error",
                            "message": "Aucun flux audio reçu."
                        }))
                        return

                    # Transcribe accumulated audio on host GPU
                    await self.send(text_data=json.dumps({
                        "type": "status",
                        "message": "Transcription en cours…"
                    }))

                    audio_bytes = bytes(self.audio_buffer)
                    self.audio_buffer.clear()

                    transcription = await sync_to_async(transcribe_audio_bytes)(
                        audio_bytes,
                        language=self.language
                    )

                    if transcription.get("status") != "success" or not transcription.get("text"):
                        await self.send(text_data=json.dumps({
                            "type": "asr_failed",
                            "message": "La parole n'a pas pu être reconnue avec clarté."
                        }))
                        return

                    # Enforce Low-Confidence Guardrail (EF-02.14)
                    if transcription.get("requires_clarification"):
                        await self.send(text_data=json.dumps({
                            "type": "clarification_required",
                            "transcript": transcription["text"],
                            "confidence": transcription["confidence"],
                            "clarification_message": transcription["clarification_message"]
                        }))
                        return

                    # Send recognized text to client
                    await self.send(text_data=json.dumps({
                        "type": "transcript_ready",
                        "transcript": transcription["text"],
                        "confidence": transcription["confidence"]
                    }))

                    # Run RAG answer pipeline
                    rag_service = DRCRagService()
                    rag_result = await sync_to_async(rag_service.answer_query)(
                        query=transcription["text"],
                        user_language=self.language
                    )

                    await self.send(text_data=json.dumps({
                        "type": "rag_response",
                        "answer": rag_result.get("answer", ""),
                        "sources": rag_result.get("sources", []),
                        "fallback_used": rag_result.get("fallback_used", False)
                    }))

            except json.JSONDecodeError:
                await self.send(text_data=json.dumps({"error": "Payload JSON invalide."}))
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
                await self.send(text_data=json.dumps({"error": str(e)}))

