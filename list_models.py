"""
list_models.py
--------------
Varsity Ad Engine — List Gemini models available for your Google API key
-----------------------------------------------------------------
Run: python list_models.py
Shows model names for the Drafter (Generate). Judge uses Claude — set JUDGE_MODEL in .env.
"""

import os
from dotenv import load_dotenv

load_dotenv()
api_key = os.environ.get("GOOGLE_API_KEY")
if not api_key:
    print("GOOGLE_API_KEY not set in .env")
    exit(1)

import google.generativeai as genai
genai.configure(api_key=api_key)

print("Gemini models for Drafter (generateContent). Use one for DRAFTER_MODEL in .env:\n")
for m in genai.list_models():
    if "generateContent" in (m.supported_generation_methods or []):
        print(f"  {m.name}")
print("\nDefault Drafter: gemini-2.0-flash. Judge uses Claude (ANTHROPIC_API_KEY, JUDGE_MODEL=claude-sonnet-4-5).")
