from abc import ABC, abstractmethod


class BaseAgent(ABC):
    """Anything that can play a kingdom implements this -- LLM-backed or not."""

    @abstractmethod
    def decide(self, prompt: str, schema_hint: str) -> dict:
        """Given a text prompt describing the current state and a description
        of the required JSON response shape, return a parsed dict."""
        raise NotImplementedError
