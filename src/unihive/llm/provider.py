"""Replaceable structured-output transport; all network access stays here."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Literal, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from pydantic import JsonValue


class ProviderError(ValueError):
    """A safe, credential-free provider failure suitable for CLI output."""


def strict_output_schema(schema: dict[str, JsonValue]) -> dict[str, JsonValue]:
    """Require all output fields even when local readers support old defaults."""

    def visit(value: JsonValue) -> JsonValue:
        if isinstance(value, list):
            return [visit(item) for item in value]
        if isinstance(value, dict):
            result = {
                key: visit(item) for key, item in value.items() if key != "default"
            }
            properties = result.get("properties")
            if isinstance(properties, dict):
                result["required"] = list(properties)
            return result
        return value

    result = visit(schema)
    assert isinstance(result, dict)
    return result


@dataclass(frozen=True)
class Completion:
    text: str
    response_id: str
    model: str


class StructuredClient(Protocol):
    provider: str
    model: str

    def complete(
        self,
        *,
        instructions: str,
        payload: str,
        schema: dict[str, JsonValue],
        name: str,
    ) -> Completion: ...


class _NoRedirect(HTTPRedirectHandler):
    # Do not forward a credential or student document to a redirected host.
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class CompatibleChatClient:
    """OpenAI-compatible chat endpoint, including compatible local servers.

    Configure JSON mode explicitly for servers without JSON Schema support.
    Never silently downgrade constraints after a provider error.
    """

    provider = "openai-compatible"

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str | None = None,
        output_mode: Literal["json_schema", "json_object", "prompt"] = "json_schema",
        timeout: float = 60,
        max_tokens: int = 8192,
        ollama_native: bool = False,
        context_tokens: int = 16384,
    ) -> None:
        parsed = urlsplit(base_url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ProviderError("Use a plain HTTP(S) API base URL without credentials")
        if parsed.scheme == "http" and parsed.hostname not in {
            "localhost",
            "127.0.0.1",
            "::1",
        }:
            raise ProviderError("Remote endpoints must use HTTPS")
        if not model.strip():
            raise ProviderError("A model name is required")
        if timeout <= 0 or max_tokens <= 0:
            raise ProviderError("Timeout and output budget must be positive")
        if context_tokens <= max_tokens:
            raise ProviderError("Context must exceed the output token budget")
        if ollama_native and (
            parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
            or "cloud" in model.lower()
        ):
            raise ProviderError(
                "Native Ollama mode requires a local model and endpoint"
            )
        self.model = model
        self.base_url = base_url.rstrip("/")
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._api_key = api_key
        self._output_mode = output_mode
        self._timeout = timeout
        self._max_tokens = max_tokens
        self._ollama_native = ollama_native
        self._context_tokens = context_tokens
        if ollama_native:
            self.provider = "ollama-local"
            self._url = self.base_url + "/api/chat"

    @classmethod
    def from_environment(cls) -> CompatibleChatClient:
        base_url = os.getenv("UNIHIVE_LLM_BASE_URL", "")
        model = os.getenv("UNIHIVE_LLM_MODEL", "")
        mode = os.getenv("UNIHIVE_LLM_OUTPUT_MODE", "json_schema")
        if not base_url or not model:
            raise ProviderError("Set UNIHIVE_LLM_BASE_URL and UNIHIVE_LLM_MODEL")
        if mode not in {"json_schema", "json_object", "prompt"}:
            raise ProviderError(
                "UNIHIVE_LLM_OUTPUT_MODE must be json_schema, json_object or prompt"
            )
        key = os.getenv("UNIHIVE_LLM_API_KEY")
        if urlsplit(base_url).hostname == "api.openai.com":
            key = key or os.getenv("OPENAI_API_KEY")
        return cls(
            base_url=base_url,
            model=model,
            api_key=key,
            output_mode=mode,
            timeout=float(os.getenv("UNIHIVE_LLM_TIMEOUT", "60")),
            ollama_native=os.getenv("UNIHIVE_LLM_PROVIDER") == "ollama",
            context_tokens=int(os.getenv("UNIHIVE_LLM_CONTEXT", "16384")),
        )

    def complete(
        self,
        *,
        instructions: str,
        payload: str,
        schema: dict[str, JsonValue],
        name: str,
    ) -> Completion:
        schema = strict_output_schema(schema)
        response_format: dict[str, JsonValue]
        if self._output_mode == "json_schema":
            response_format = {
                "type": "json_schema",
                "json_schema": {"name": name, "strict": True, "schema": schema},
            }
        else:
            response_format = {"type": "json_object"}
        body = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": instructions
                    + "\nReturn JSON matching this schema:\n"
                    + json.dumps(schema),
                },
                {"role": "user", "content": payload},
            ],
            "response_format": response_format,
            "max_tokens": self._max_tokens,
            "stream": False,
        }
        if self._output_mode == "prompt":
            # Ollama Cloud does not currently support constrained outputs.
            # The same strict local schema/provenance validation still applies.
            del body["response_format"]
        if self._ollama_native:
            body.pop("response_format", None)
            body.pop("max_tokens")
            body["format"] = schema
            body["think"] = False
            body["options"] = {
                "num_ctx": self._context_tokens,
                "num_predict": self._max_tokens,
                "temperature": 0,
            }
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = "Bearer " + self._api_key
        request = Request(
            self._url,
            data=json.dumps(body).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with build_opener(_NoRedirect()).open(
                request, timeout=self._timeout
            ) as reply:
                raw = reply.read(4_000_001)
                if len(raw) > 4_000_000:
                    raise ProviderError("Provider response exceeded size limit")
        except HTTPError as exc:
            raise ProviderError(
                f"Model endpoint returned HTTP {exc.code}; check configuration"
            ) from None
        except (URLError, TimeoutError, OSError):
            raise ProviderError("Model endpoint unavailable or timed out") from None
        try:
            result = json.loads(raw)
            if self._ollama_native:
                if (
                    result.get("done") is not True
                    or result.get("done_reason") != "stop"
                ):
                    raise ProviderError("Local model did not finish its response")
                content = result["message"]["content"]
                if not isinstance(content, str) or not content.strip():
                    raise ProviderError("Local model returned no structured content")
                return Completion(
                    text=content,
                    response_id=str(result.get("created_at", "")),
                    model=str(result.get("model", self.model)),
                )
            choice = result["choices"][0]
            message = choice["message"]
            if choice.get("finish_reason") != "stop" or message.get("refusal"):
                raise ProviderError(
                    "Model refused or did not finish its structured response"
                )
            content = message["content"]
            if not isinstance(content, str) or not content.strip():
                raise ProviderError("Model returned no structured content")
            return Completion(
                text=content,
                response_id=str(result.get("id", "")),
                model=str(result.get("model", self.model)),
            )
        except (ValueError, KeyError, IndexError, TypeError):
            raise ProviderError(
                "Model returned an invalid or incomplete response"
            ) from None
