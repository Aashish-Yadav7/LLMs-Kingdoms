"""
One agent class for every kingdom, regardless of which model plays it.
Uses OpenRouter's OpenAI-compatible endpoint so Claude, GPT, Gemini, Grok,
DeepSeek, Kimi, Qwen, GLM, or your own hosted model are all reachable the
same way -- just a different `model` string and possibly a different
base_url/api_key for a custom-hosted model.
"""

import json
import os
import re
import time

from openai import OpenAI

from src.agents.base_agent import BaseAgent


class LLMAgent(BaseAgent):
    def __init__(self, model: str, kingdom_name: str, personality: str):
        self.model = model
        self.kingdom_name = kingdom_name
        self.personality = personality

        if model.startswith("custom/"):
            base_url = os.environ.get("CUSTOM_MODEL_BASE_URL")
            api_key = os.environ.get("CUSTOM_MODEL_API_KEY", "not-needed")
            self.model_id = model.removeprefix("custom/")
        else:
            base_url = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
            api_key = os.environ.get("OPENROUTER_API_KEY")
            self.model_id = model

        if not api_key:
            raise RuntimeError(
                f"No API key found for {kingdom_name} ({model}). "
                f"Set OPENROUTER_API_KEY (or CUSTOM_MODEL_API_KEY) in .env"
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

        last_error = None
        for attempt in range(max_retries):
            try:
                response = self.client.chat.completions.create(
                    model=self.model_id,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.8,
                )
                text = response.choices[0].message.content
                return _extract_json(text)
            except Exception as e:
                last_error = e
                time.sleep(2 ** attempt)  # backoff for rate limits (429s on free tiers)

        # If the model fails entirely, fall back to a safe no-op so the game
        # loop doesn't crash on one kingdom's bad turn.
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
