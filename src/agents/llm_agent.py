"""
One agent class for every kingdom, regardless of which model plays it.
Routes to the right provider based on a prefix on the model string:

    "ollama/llama3.1"        -> local Ollama, no API key, runs on your machine, fully free
    "groq/llama-3.3-70b"     -> Groq's free tier, very fast, needs GROQ_API_KEY
    "custom/your-model-id"   -> any OpenAI-compatible endpoint you host yourself
    anything else            -> OpenRouter (Claude, GPT, Gemini, Grok, DeepSeek,
                                 Kimi, Qwen, GLM, etc, including OpenRouter's
                                 own free-tier routes)

All of these speak the same OpenAI-compatible chat completions API, so one
agent class handles every provider -- just change the model string.
"""

import json
import os
import re
import time

import openai
from openai import OpenAI

from src.agents.base_agent import BaseAgent

PROVIDER_PREFIXES = {
    "ollama/": {
        "base_url_env": "OLLAMA_BASE_URL",
        "default_base_url": "http://localhost:11434/v1",
        "api_key_env": None,          # Ollama doesn't check the key at all
        "default_api_key": "ollama",  # OpenAI client requires a non-empty string regardless
    },
    "groq/": {
        "base_url_env": "GROQ_BASE_URL",
        "default_base_url": "https://api.groq.com/openai/v1",
        "api_key_env": "GROQ_API_KEY",
        "default_api_key": None,
    },
    "cerebras/": {
        "base_url_env": "CEREBRAS_BASE_URL",
        "default_base_url": "https://api.cerebras.ai/v1",
        "api_key_env": "CEREBRAS_API_KEY",
        "default_api_key": None,
    },
    "nvidia/": {
        "base_url_env": "NVIDIA_BASE_URL",
        "default_base_url": "https://integrate.api.nvidia.com/v1",
        "api_key_env": "NVIDIA_API_KEY",
        "default_api_key": None,
    },
    "custom/": {
        "base_url_env": "CUSTOM_MODEL_BASE_URL",
        "default_base_url": None,
        "api_key_env": "CUSTOM_MODEL_API_KEY",
        "default_api_key": "not-needed",
    },
}


class LLMAgent(BaseAgent):
    def __init__(self, model: str, kingdom_name: str, personality: str):
        self.model = model
        self.kingdom_name = kingdom_name
        self.personality = personality

        provider = next((p for prefix, p in PROVIDER_PREFIXES.items() if model.startswith(prefix)), None)

        if provider:
            prefix = next(pfx for pfx in PROVIDER_PREFIXES if model.startswith(pfx))
            self.model_id = model.removeprefix(prefix)
            base_url = os.environ.get(provider["base_url_env"], provider["default_base_url"])
            api_key = (
                os.environ.get(provider["api_key_env"], provider["default_api_key"])
                if provider["api_key_env"] else provider["default_api_key"]
            )
            if not base_url:
                raise RuntimeError(
                    f"No base URL configured for {kingdom_name} ({model}). "
                    f"Set {provider['base_url_env']} in .env"
                )
        else:
            base_url = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
            api_key = os.environ.get("OPENROUTER_API_KEY")
            self.model_id = model

        if not api_key:
            raise RuntimeError(
                f"No API key found for {kingdom_name} ({model}). "
                f"Check the matching *_API_KEY variable in .env"
            )

        self.client = OpenAI(base_url=base_url, api_key=api_key)

    def decide(self, prompt: str, schema_hint: str, max_retries: int = 3) -> dict:
        system_prompt = (
            f"You are the ruler of {self.kingdom_name}. Personality: {self.personality}\n"
            "You are playing a turn-based strategy game with a real, enforced economy. "
            "You cannot exceed your treasury, ignore tech prerequisites, or build units "
            "you haven't unlocked -- the game engine will reject illegal actions.\n"
            "Respond with ONLY a single JSON object, no prose, no markdown fences, "
            f"matching this shape:\n{schema_hint}"
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]

        # A 404 (model doesn't exist / was renamed) or a connection failure
        # (e.g. Ollama isn't running) will NEVER succeed on retry -- retrying
        # those with backoff just burns real time for a guaranteed failure.
        # Only genuinely transient errors (rate limits, timeouts) get the
        # retry treatment; everything else fails fast.
        try:
            response = self.client.chat.completions.create(
                model=self.model_id, messages=messages, temperature=0.8,
            )
            return _extract_json(response.choices[0].message.content)
        except openai.NotFoundError as e:
            # Model slug is stale/wrong. If this wasn't already a call to
            # OpenRouter's auto-router, try that exactly once before giving up
            # -- "openrouter/free" always resolves to something live.
            is_openrouter_call = self.client.base_url and "openrouter.ai" in str(self.client.base_url)
            if is_openrouter_call and self.model_id != "openrouter/free":
                print(f"[WARN] {self.kingdom_name}: model '{self.model_id}' not found, "
                      f"falling back to openrouter/free for this turn.")
                try:
                    response = self.client.chat.completions.create(
                        model="openrouter/free", messages=messages, temperature=0.8,
                    )
                    return _extract_json(response.choices[0].message.content)
                except Exception as e2:
                    print(f"[WARN] {self.kingdom_name}: fallback also failed: {e2}")
                    return {"action": "pass", "reasoning": f"agent_error: {e2}"}
            print(f"[WARN] {self.kingdom_name} ({self.model}): model not found -- {e}")
            return {"action": "pass", "reasoning": f"agent_error: model not found"}
        except (openai.APIConnectionError, ConnectionError) as e:
            print(f"[WARN] {self.kingdom_name} ({self.model}): can't connect -- is it running/reachable? {e}")
            return {"action": "pass", "reasoning": "agent_error: connection failed"}
        except Exception as e:
            last_error = e
            for attempt in range(max_retries - 1):
                time.sleep(2 ** attempt)  # backoff, for genuinely transient errors like 429s
                try:
                    response = self.client.chat.completions.create(
                        model=self.model_id, messages=messages, temperature=0.8,
                    )
                    return _extract_json(response.choices[0].message.content)
                except Exception as e2:
                    last_error = e2
            print(f"[WARN] {self.kingdom_name} ({self.model}) failed after retries: {last_error}")
            return {"action": "pass", "reasoning": f"agent_error: {last_error}"}


def _extract_json(text: str) -> dict:
    """Models sometimes wrap JSON in ```json fences despite instructions -- strip them."""
    text = text.strip()
    text = re.sub(r"^```(json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # last resort: grab the first {...} block
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise