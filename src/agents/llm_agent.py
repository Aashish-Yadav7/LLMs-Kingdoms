"""
One agent class for every kingdom, regardless of which model plays it.
Routes to the right provider based on a prefix on the model string:

    "ollama/llama3.1"        -> local Ollama, no API key, runs on your machine, fully free
    "groq/llama-3.3-70b"     -> Groq's free tier, needs GROQ_API_KEY
    "cerebras/gpt-oss-120b"  -> Cerebras's free tier, needs CEREBRAS_API_KEY
    "nvidia/meta/..."        -> NVIDIA Build's free tier, needs NVIDIA_API_KEY
    "xai/grok-..."           -> NOT FREE, needs XAI_API_KEY, real billing
    "custom/your-model-id"   -> any OpenAI-compatible endpoint you host yourself
    anything else            -> OpenRouter, needs OPENROUTER_API_KEY

All of these speak the same OpenAI-compatible chat completions API.

FALLBACK CHAIN: if a kingdom's configured model fails for ANY reason (wrong
key, payment required, model not found, can't connect, rate limited), this
does not just give up -- it automatically tries the next provider in
FALLBACK_CHAIN below, skipping any provider whose required key isn't set in
.env, until one works or the chain runs out. This means you can have several
provider keys sitting in .env at once and the game will just use whichever
one actually works that turn, no manual swapping needed.
"""

import json
import os
import re

import openai
from openai import OpenAI

from src.agents.base_agent import BaseAgent

PROVIDER_PREFIXES = {
    "ollama/": {
        "base_url_env": "OLLAMA_BASE_URL",
        "default_base_url": "http://localhost:11434/v1",
        "api_key_env": None,
        "default_api_key": "ollama",
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
    "xai/": {
        "base_url_env": "XAI_BASE_URL",
        "default_base_url": "https://api.x.ai/v1",
        "api_key_env": "XAI_API_KEY",
        "default_api_key": None,
    },
    "custom/": {
        "base_url_env": "CUSTOM_MODEL_BASE_URL",
        "default_base_url": None,
        "api_key_env": "CUSTOM_MODEL_API_KEY",
        "default_api_key": "not-needed",
    },
}

FALLBACK_CHAIN = [
    "groq/llama-3.3-70b-versatile",
    "openrouter/free",
    "nvidia/meta/llama-3.1-70b-instruct",
    "cerebras/gpt-oss-120b",
    "ollama/llama3.2",
]


def _resolve(model: str):
    provider = next((p for prefix, p in PROVIDER_PREFIXES.items() if model.startswith(prefix)), None)

    if provider:
        prefix = next(pfx for pfx in PROVIDER_PREFIXES if model.startswith(pfx))
        model_id = model.removeprefix(prefix)
        base_url = os.environ.get(provider["base_url_env"], provider["default_base_url"])
        api_key = (
            os.environ.get(provider["api_key_env"], provider["default_api_key"])
            if provider["api_key_env"] else provider["default_api_key"]
        )
        if not base_url or not api_key:
            return None
        return base_url, api_key, model_id

    base_url = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        return None
    return base_url, api_key, model


class LLMAgent(BaseAgent):
    def __init__(self, model: str, kingdom_name: str, personality: str):
        self.model = model
        self.kingdom_name = kingdom_name
        self.personality = personality

    def decide(self, prompt: str, schema_hint: str) -> dict:
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

        candidates = [self.model] + [m for m in FALLBACK_CHAIN if m != self.model]

        attempt_errors = []  # (candidate, error) for every real attempt -- not just the last
        for candidate in candidates:
            resolved = _resolve(candidate)
            if resolved is None:
                continue
            base_url, api_key, model_id = resolved
            try:
                client = OpenAI(base_url=base_url, api_key=api_key)
                response = client.chat.completions.create(
                    model=model_id, messages=messages, temperature=0.8,
                )
                if candidate != self.model:
                    print(f"[INFO] {self.kingdom_name}: '{self.model}' unavailable, used fallback '{candidate}' instead.")
                return _extract_json(response.choices[0].message.content)
            except Exception as e:
                attempt_errors.append((candidate, e))
                continue

        if attempt_errors:
            print(f"[WARN] {self.kingdom_name}: every provider failed. Full breakdown:")
            for candidate, err in attempt_errors:
                print(f"    - {candidate}: {err}")
        else:
            print(f"[WARN] {self.kingdom_name}: no provider had a usable key/config at all -- check your .env")
        return {"action": "pass", "reasoning": "agent_error: all providers failed, see console for per-provider breakdown"}


def _extract_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise