#!/usr/bin/env python3
import google.generativeai as genai
import os
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    print("ERROR: GEMINI_API_KEY not set in .env")
    exit(1)

print(f"Using API Key: {api_key[:20]}...")
genai.configure(api_key=api_key)

try:
    print("\nAvailable Models:")
    for model in genai.list_models():
        print(f"  - {model.name}")
except Exception as e:
    print(f"Error listing models: {e}")
    print("\nThe API key might be invalid or expired.")
    print("Get a new one from: https://aistudio.google.com/app/apikey")
