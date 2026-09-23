"""Shared OpenAI client setup.

One place to look up the key and build a client, so every AI feature fails the
same way — with a message that says what to do about it — instead of each one
inventing its own.

A key can come from two places, and resolve_key() reports which: a key typed
into settings beats OPENAI_API_KEY in the environment, on the grounds that
typing one here is the more deliberate act. The settings dialog shows the source
rather than an empty box, so "I already put it in .env" never looks like "no key
set", and a forgotten stored key can't quietly shadow the environment.
"""

import json
import os

from db import get_setting

SETTINGS_KEY = "openai_api_key"
ENV_VAR = "OPENAI_API_KEY"

FROM_SETTINGS = "settings"
FROM_ENVIRONMENT = "environment"

# A stuck connection must eventually surface as an error, not hang forever —
# but meeting transcripts can be long, so give the model room to work before
# giving up. One retry keeps the worst case bounded (~2x this) instead of the
# SDK's default of three attempts.
REQUEST_TIMEOUT_SECONDS = 600.0
MAX_RETRIES = 1


def stored_key():
    """The key saved in settings, if any."""
    return (get_setting(SETTINGS_KEY) or "").strip()


def environment_key():
    """The key from OPENAI_API_KEY — which .env files are loaded into at startup."""
    return (os.environ.get(ENV_VAR) or "").strip()


def resolve_key():
    """(key, source) for the key actually in use. Source is None when there isn't one."""
    stored = stored_key()
    if stored:
        return stored, FROM_SETTINGS
    environment = environment_key()
    if environment:
        return environment, FROM_ENVIRONMENT
    return "", None


def api_key():
    return resolve_key()[0]


def has_api_key():
    return bool(api_key())


def client():
    """Build an OpenAI client, raising a user-facing RuntimeError if not set up."""
    key = api_key()
    if not key:
        raise RuntimeError(
            "No OpenAI API key set.\n\n"
            f"Use the ⚙ settings button (Ctrl+,) or set {ENV_VAR} in your "
            "environment or .env file."
        )
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError(
            "The openai package is not installed.\n\n"
            "Run: pip install openai"
        ) from exc
    return OpenAI(api_key=key, timeout=REQUEST_TIMEOUT_SECONDS, max_retries=MAX_RETRIES)


def _friendly_error(exc):
    """Turn an OpenAI SDK exception into a message a user can act on."""
    from openai import APIConnectionError, APITimeoutError, AuthenticationError, OpenAIError

    if isinstance(exc, APITimeoutError):
        minutes = int(REQUEST_TIMEOUT_SECONDS // 60)
        return RuntimeError(
            f"The AI request timed out after {minutes} minutes with no response.\n\n"
            "This can happen on a slow or dropped connection. Check your network "
            "and try again — for a long meeting, the transcript may also be worth "
            "trimming before retrying."
        )
    if isinstance(exc, APIConnectionError):
        return RuntimeError(
            "Could not reach the AI service. Check your internet connection and try again."
        )
    if isinstance(exc, AuthenticationError):
        return RuntimeError(
            "The AI service rejected the API key.\n\n"
            f"Use the ⚙ settings button (Ctrl+,) or check {ENV_VAR}."
        )
    if isinstance(exc, OpenAIError):
        return RuntimeError(str(exc) or "The AI request failed.")
    return exc


def chat_completion(ai_client, **kwargs):
    """client.chat.completions.create(), with SDK errors mapped to user-facing ones."""
    try:
        return ai_client.chat.completions.create(**kwargs)
    except Exception as exc:
        raise _friendly_error(exc) from exc


def transcription(ai_client, **kwargs):
    """client.audio.transcriptions.create(), with SDK errors mapped to user-facing ones."""
    try:
        return ai_client.audio.transcriptions.create(**kwargs)
    except Exception as exc:
        raise _friendly_error(exc) from exc


def parse_json_reply(response):
    """Read a JSON-object completion, with a message a user can act on."""
    content = response.choices[0].message.content or "{}"
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise RuntimeError("AI returned invalid JSON. Try again.") from exc


def string_list(value):
    """Coerce a model's list-ish field into a clean list of non-empty strings.

    A null in the list must be dropped, not stringified — str(None) is "None",
    which is neither empty nor something anyone wants on their agenda.
    """
    if not isinstance(value, list):
        return []
    cleaned = []
    for item in value:
        if item is None:
            continue
        text = str(item).strip()
        if text:
            cleaned.append(text)
    return cleaned
