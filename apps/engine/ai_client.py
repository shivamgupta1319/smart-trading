"""The one place the engine talks to an AI model: through the AI router.

The AI router (https://ai.pseo.cloud, on work-pc) is an OpenAI-compatible gateway that
keeps track of which free models are actually answering and picks one. The engine used to
call OpenRouter and then Gemini itself, with its own fallback loop; when Gemini was busy
its raw error text ended up on the Sector page. All of that lives in the router now.

Settings (environment):
  AI_ROUTER_URL    base address ending in /v1. Default is the Docker host gateway, which is
                   how a container on work-pc reaches the router without leaving the machine.
  AI_ROUTER_KEY    this project's key (minted in the router: `mint-key.js mint smart-trading`).
  AI_ROUTER_MODEL  "auto" or a task alias such as "task:reasoning". Never a pinned model id:
                   free model ids die without notice, and the router exists to absorb that.
  AI_ROUTER_TIMEOUT_S  how long to wait for an answer.
"""
from __future__ import annotations

import os

import httpx

SYSTEM_PROMPT = (
    "You are an expert Indian Stock Market Quantitative Analyst. You provide concise, "
    "insightful, and highly technical fundamental, technical, and sentimental analysis."
)

NOT_CONFIGURED = (
    "> [!WARNING]\n> **AI analysis is not set up.**\n\n"
    "Add `AI_ROUTER_KEY` to the stack's settings file and restart the engine."
)


def _unavailable(detail: str) -> str:
    return (
        "> [!WARNING]\n> **AI analysis is unavailable right now.**\n\n"
        f"{detail} This is usually temporary. Try again in a minute."
    )


class AIClient:
    def __init__(self) -> None:
        self.base_url = os.getenv("AI_ROUTER_URL", "http://172.17.0.1:8771/v1").rstrip("/")
        self.key = os.getenv("AI_ROUTER_KEY", "")
        self.model = os.getenv("AI_ROUTER_MODEL", "auto")
        try:
            self.timeout = float(os.getenv("AI_ROUTER_TIMEOUT_S", "75"))
        except ValueError:
            self.timeout = 75.0

    async def generate(self, prompt: str) -> str:
        """The model's answer as markdown. On any failure, a plain-words notice instead:
        never a provider's raw error body, and never an exception."""
        if not self.key:
            return NOT_CONFIGURED
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        }
        headers = {"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"}
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(f"{self.base_url}/chat/completions", headers=headers, json=payload)
        except httpx.TimeoutException:
            return _unavailable("The AI router did not answer in time.")
        except httpx.HTTPError as exc:
            print(f"[ai] router unreachable: {type(exc).__name__}: {exc}")
            return _unavailable("The AI router could not be reached.")

        if resp.status_code == 401:
            print("[ai] router rejected the key (401)")
            return "> [!WARNING]\n> **AI analysis is not set up.**\n\nThe AI router rejected this project's key."
        if resp.status_code == 429:
            return _unavailable("Every AI model is busy.")
        if resp.status_code != 200:
            print(f"[ai] router HTTP {resp.status_code}: {resp.text[:300]}")
            return _unavailable("The AI router returned an error.")
        try:
            text = resp.json()["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError):
            print(f"[ai] unexpected router response: {resp.text[:300]}")
            return _unavailable("The AI router sent an answer that could not be read.")
        if not isinstance(text, str) or not text.strip():
            return _unavailable("The AI model returned an empty answer.")
        return text


llm = AIClient()
