"""
images/
-------
Varsity Ad Engine — Nerdy / Gauntlet — v2 Image generation package
-------------------------------------------------------------------
Contains the image generator that produces companion ad creatives
for every passing ad using the image_prompt field from AdCopy.
Uses google-genai + gemini-2.5-flash-image (Nano Banana) only here.
Only runs on ads that have passed the 7.0 quality threshold.

Modules:
  image_generator.py — AdImageGenerator class, generate_image() call
"""
