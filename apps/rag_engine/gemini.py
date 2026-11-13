"""LangChain Gemini integration with compatibility for existing Ollama options."""
from functools import lru_cache

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from langchain_google_genai import ChatGoogleGenerativeAI


class GeminiChat(ChatGoogleGenerativeAI):
    """Translate shared JSON/token options; LangChain handles messages and streaming."""

    def bind(self, **kwargs):
        options = kwargs.pop('options', {})
        for source, target in [('num_predict', 'max_output_tokens'), ('temperature', 'temperature')]:
            if source in options:
                kwargs[target] = options[source]
        output_format = kwargs.pop('format', None)
        if output_format:
            kwargs['response_mime_type'] = 'application/json'
            if isinstance(output_format, dict):
                kwargs['response_json_schema'] = output_format
        return super().bind(**kwargs)


@lru_cache(maxsize=4)
def _client(api_key, model, timeout, temperature, max_output_tokens):
    return GeminiChat(
        google_api_key=api_key, model=model, vertexai=False,
        timeout=timeout, temperature=temperature,
        max_output_tokens=max_output_tokens, thinking_budget=0,
        include_thoughts=False, max_retries=2,
    )


def get_gemini_chat():
    if not settings.GEMINI_API_KEY:
        raise ImproperlyConfigured('Set GEMINI_API_KEY in .env or the server environment to use Gemini.')
    return _client(settings.GEMINI_API_KEY, settings.GEMINI_MODEL, settings.GEMINI_TIMEOUT,
                   settings.GEMINI_TEMPERATURE, settings.GEMINI_MAX_OUTPUT_TOKENS)
