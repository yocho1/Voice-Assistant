# Voice Assistant (Gemini + Whisper + Coqui TTS)

A production-ready voice assistant that pairs Google Gemini with local Whisper speech-to-text and Coqui TTS speech synthesis. Built with Flask and a modern web UI featuring voice recording, transcripts, dark/light mode, and audio playback.

## Features

- Gemini conversation with short-term memory (last 5 exchanges)
- Local Whisper STT (multi-format via ffmpeg) and Coqui TTS with optional voice selection
- Modern chat UI: mic with waveform + silence auto-stop, copy-to-clipboard, loading states, dark/light with persistence
- REST API with health, chat, STT, TTS, and conversation reset
- Dockerized (multi-stage build) with audio volume mount and healthcheck
- Basic rate limiting and CORS

## Quickstart (Local)

1. Copy environment template and fill keys:
   - `cp .env.example .env`
2. Install Python 3.11+ dependencies:
   - `python -m venv .venv && .venv/Scripts/activate` (Windows) or `source .venv/bin/activate`
   - `pip install -r requirements.txt`
3. Run the app:
   - `python app.py`
4. Open http://localhost:5000 to use the UI.

## Quickstart (Docker)

```bash
docker-compose up --build
```

The app listens on port 5000 and mounts `static/audio` for generated clips.

## API

- `GET /health` – service status
- `POST /api/chat` – body: `{ "message": string, "audio": bool }`
- `POST /api/speech-to-text` – form-data: `file` (audio), optional `language`
- `POST /api/text-to-speech` – body: `{ "text": string, "voice"?: string }`
- `GET /api/conversation` – current trimmed history
- `POST /api/conversation/reset` – clear history

## Configuration

All options live in `.env`:

- Gemini: `GEMINI_API_KEY`, `GEMINI_MODEL`, `GEMINI_TEMPERATURE`, `GEMINI_MAX_TOKENS`
- Whisper STT: `WHISPER_MODEL` (tiny/base/small/medium/large)
- Coqui TTS: `TTS_MODEL`, `TTS_VOICE`, `AUDIO_FORMAT` (wav/mp3)
- Server: `FLASK_SECRET_KEY`, `PORT`, `REQUESTS_PER_MINUTE`, `CONVERSATION_WINDOW`, `MAX_AUDIO_AGE_MINUTES`, `MAX_UPLOAD_MB`

## Notes

- Recorded and synthesized audio is stored under `static/audio` and pruned by age.
- Rate limiting is IP-based; adjust `REQUESTS_PER_MINUTE` as needed.
- If any provider credentials are missing, the relevant routes return `503` gracefully.
- Whisper and Coqui models download at first run; ensure adequate disk/RAM. ffmpeg is required for audio conversion.
