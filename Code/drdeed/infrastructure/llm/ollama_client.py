"""Small standard-library client for Ollama's local chat endpoint."""

import json
from collections.abc import Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class OllamaChatClient:
    def __init__(
        self,
        model_name: str = "qwen3:8b",
        base_url: str = "http://localhost:11434",
        timeout_seconds: float = 120.0,
    ) -> None:
        self._model_name = model_name
        self._endpoint = f"{base_url.rstrip('/')}/api/chat"
        self._timeout_seconds = timeout_seconds

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        response_schema: dict[str, object],
    ) -> str:
        payload = {
            "model": self._model_name,
            "stream": False,
            "format": response_schema,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "options": {"temperature": 0},
        }
        request = Request(
            self._endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                result = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"Ollama returned HTTP {error.code}: {detail}"
            ) from error
        except URLError as error:
            raise RuntimeError(
                "Could not reach Ollama at "
                f"{self._endpoint}. Start Ollama and make sure the model "
                f"{self._model_name!r} is available. Details: {error.reason}"
            ) from error
        except (TimeoutError, OSError) as error:
            raise RuntimeError(f"Ollama request failed: {error}") from error
        except json.JSONDecodeError as error:
            raise RuntimeError("Ollama returned an invalid JSON response.") from error

        if not isinstance(result, Mapping):
            raise RuntimeError("Ollama response must be a JSON object.")
        try:
            content = result["message"]["content"]
        except (KeyError, TypeError) as error:
            raise RuntimeError(
                "Ollama response did not contain message content."
            ) from error
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("Ollama returned an empty model response.")
        return content
