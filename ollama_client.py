import asyncio
import json
from typing import Any

import httpx

from config import OLLAMA_MODEL, OLLAMA_TIMEOUT, OLLAMA_URL


class OllamaError(Exception):
    pass


async def chat_json(system: str, user: str, temperature: float = 0.2) -> dict[str, Any]:
    """Запрос к Ollama в режиме format=json. Возвращает разобранный JSON-объект."""
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "format": "json",
        "stream": False,
        "options": {"temperature": temperature},
    }
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT) as client:
                resp = await client.post(f"{OLLAMA_URL}/api/chat", json=payload)
                resp.raise_for_status()
                data = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            last_error = exc
            await asyncio.sleep(1.5 * (attempt + 1))
            continue

        content = data.get("message", {}).get("content", "")
        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            last_error = exc
            break

    raise OllamaError(f"Не удалось получить JSON от модели: {last_error}")


async def ping() -> tuple[bool, str]:
    """Проверка доступности Ollama и списка моделей."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{OLLAMA_URL}/api/tags")
            resp.raise_for_status()
            models = [m["name"] for m in resp.json().get("models", [])]
    except (httpx.HTTPError, ValueError) as exc:
        return False, f"Ollama недоступен: {exc}"
    status = f"Ollama OK, модель: {OLLAMA_MODEL}" + (
        "" if OLLAMA_MODEL in models else f" (доступны: {', '.join(models) or 'нет'})"
    )
    return True, status
