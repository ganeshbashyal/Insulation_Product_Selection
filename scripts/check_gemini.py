"""Diagnose Gemini API access: list models, test a plain call, test grounding."""
import os
import sys

key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
if not key:
    print("GEMINI_API_KEY not set")
    sys.exit(1)

from google import genai
from google.genai import types

client = genai.Client(api_key=key)
model = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
print(f"model: {model}")

print("\n[1] plain generate_content (no tools) ...")
try:
    r = client.models.generate_content(model=model, contents="Reply with the single word: ok")
    print("  OK ->", (r.text or "").strip()[:50])
except Exception as e:
    print("  FAIL:", str(e)[:300])

print("\n[2] generate_content WITH google_search grounding ...")
try:
    r = client.models.generate_content(
        model=model,
        contents="What is 2+2? Reply with just the number.",
        config=types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())]),
    )
    print("  OK ->", (r.text or "").strip()[:50])
except Exception as e:
    print("  FAIL:", str(e)[:300])
