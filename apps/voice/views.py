"""
HTTP API views for DRC Voice processing (Whisper ASR).
Provides:
1. POST /api/voice/transcribe/ : Accepts audio blob (WebM/WAV) and transcribes with faster-whisper.
"""

import logging
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.voice.audio_utils import transcribe_audio_bytes

logger = logging.getLogger(__name__)


@csrf_exempt
@require_http_methods(["POST"])
def transcribe_voice_api(request):
    """
    Accepts audio data via multipart/form-data ('audio' or 'file') or raw body bytes,
    and returns faster-whisper transcription with confidence score.
    """
    language = request.POST.get('language') or request.GET.get('language') or 'fr'
    audio_bytes = None

    # 1. Try uploaded file
    if 'audio' in request.FILES:
        audio_file = request.FILES['audio']
        audio_bytes = audio_file.read()
    elif 'file' in request.FILES:
        audio_file = request.FILES['file']
        audio_bytes = audio_file.read()
    elif request.body:
        audio_bytes = request.body

    if not audio_bytes:
        return JsonResponse({
            "status": "error",
            "message": "Aucun fichier audio reçu dans la requête."
        }, status=400)

    try:
        result = transcribe_audio_bytes(audio_bytes, language=language)
        return JsonResponse(result)
    except Exception as e:
        logger.error(f"Error during voice transcription: {e}")
        return JsonResponse({
            "status": "error",
            "message": f"Erreur de transcription audio : {str(e)}"
        }, status=500)

