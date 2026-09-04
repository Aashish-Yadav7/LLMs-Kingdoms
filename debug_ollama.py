"""
Standalone test -- completely bypasses the game to check ONE thing: can
Python's OpenAI client actually reach your local Ollama server the same way
the game does. This isolates the problem from all the fallback-chain and
game-logic complexity, so whatever error shows up here is the real,
unfiltered cause.

Run with:
    python debug_ollama.py
"""

from openai import OpenAI

print("Connecting to http://localhost:11434/v1 ...")
client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")

try:
    response = client.chat.completions.create(
        model="llama3.2",
        messages=[{"role": "user", "content": "Say hello in exactly 5 words."}],
        temperature=0.8,
    )
    print("\nSUCCESS -- Ollama responded correctly through Python:")
    print(response.choices[0].message.content)
except Exception as e:
    print(f"\nFAILED -- {type(e).__name__}: {e}")
    print("\nThis is the real, unfiltered error. Send me this exact output.")
