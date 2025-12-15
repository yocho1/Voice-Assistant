# Voice Assistant

> A production-ready AI voice assistant combining Google Gemini's conversation capabilities with local Whisper speech-to-text and Coqui TTS speech synthesis. Built with Flask and featuring a modern, responsive web UI.

[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Docker](https://img.shields.io/badge/Docker-Available-blue.svg)](Dockerfile)

## ✨ Features

### Core Capabilities
- **Gemini-Powered Conversations** – Uses Google's Gemini API with 5-message short-term memory
- **Local Speech-to-Text** – OpenAI Whisper with multi-format audio support (WAV, WebM, MP3, OGG)
- **Natural Speech Synthesis** – Coqui TTS for audio responses with optional voice selection
- **Cross-Platform Audio** – Auto-converts audio formats via ffmpeg for seamless processing

### User Experience
- **Voice Recording** – Browser-native MediaRecorder with waveform visualization
- **Automatic Silence Detection** – Audio stops recording after 1.2s of silence
- **Live Transcripts** – Real-time transcription display with language detection
- **Dark/Light Mode** – Theme preference persists across sessions
- **Copy-to-Clipboard** – Quickly export AI responses
- **Responsive Design** – Mobile-first, works on desktop/tablet/phone

### Developer-Friendly
- **REST API** – Clean, predictable endpoints for all operations
- **Rate Limiting** – IP-based rate limiting (configurable per minute)
- **CORS Enabled** – Cross-origin requests supported
- **Comprehensive Logging** – Detailed error and debug information
- **Docker Support** – Multi-stage build with optimized image size
- **Health Checks** – Built-in service status monitoring

## 🚀 Quick Start

### Option 1: Docker (Recommended)

```bash
# Clone and enter directory
git clone https://github.com/yocho1/Voice-Assistant.git
cd Voice-Assistant

# Copy environment template
cp .env.example .env

# Get a free Gemini API key from https://aistudio.google.com/app/apikey
# Edit .env and update GEMINI_API_KEY

# Build and run
docker-compose up --build
```

Visit http://localhost:5000

### Option 2: Local Development

**Requirements:** Python 3.11+, ffmpeg, espeak-ng

```bash
# Create virtual environment
python -m venv .venv
.venv\Scripts\activate  # Windows
# OR
source .venv/bin/activate  # macOS/Linux

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your Gemini API key

# Run
python app.py
```

Visit http://localhost:5000

## 📋 API Documentation

### Health & Status
```http
GET /health
```
Returns service status and model availability.

### Chat Endpoint
```http
POST /api/chat
Content-Type: application/json

{
  "message": "What is machine learning?",
  "audio": true
}
```
**Response:**
```json
{
  "reply": "Machine learning is...",
  "audio_url": "/static/audio/tts-abc123.wav",
  "history": [...]
}
```

### Speech-to-Text
```http
POST /api/speech-to-text
Content-Type: multipart/form-data

file: <audio_file>
language: en (optional)
```
**Response:**
```json
{
  "transcript": "hello world",
  "segments": [
    {
      "text": "hello",
      "start": 0.0,
      "end": 0.5
    }
  ],
  "language": "en"
}
```

### Text-to-Speech
```http
POST /api/text-to-speech
Content-Type: application/json

{
  "text": "Hello, world!",
  "voice": "en-US"
}
```
**Response:**
```json
{
  "audio_url": "/static/audio/tts-xyz789.wav"
}
```

### Conversation Management
```http
GET /api/conversation
```
Get current conversation history (trimmed).

```http
POST /api/conversation/reset
```
Clear all conversation history.

## ⚙️ Configuration

Create a `.env` file based on `.env.example`:

### Gemini Settings
- `GEMINI_API_KEY` – API key from https://aistudio.google.com/app/apikey
- `GEMINI_MODEL` – Model to use (default: `gemini-1.5-flash`)
- `GEMINI_TEMPERATURE` – Creativity level 0.0–2.0 (default: `0.7`)
- `GEMINI_MAX_TOKENS` – Max response length (default: `512`)

### Speech Settings
- `WHISPER_MODEL` – Model size: `tiny`, `base`, `small`, `medium`, `large` (default: `base`)
- `TTS_MODEL` – Coqui model path (default: `tts_models/en/ljspeech/tacotron2-DDC`)
- `TTS_VOICE` – Voice ID for synthesis (default: `en-US`)
- `AUDIO_FORMAT` – Output format: `wav` or `mp3` (default: `wav`)

### Server Settings
- `FLASK_SECRET_KEY` – Session encryption key
- `PORT` – Server port (default: `5000`)
- `REQUESTS_PER_MINUTE` – Rate limit (default: `60`)
- `CONVERSATION_WINDOW` – Messages to retain (default: `5`)
- `MAX_AUDIO_AGE_MINUTES` – Audio cleanup age (default: `60`)
- `MAX_UPLOAD_MB` – Max upload size (default: `25`)

## 📁 Project Structure

```
voice-assistant/
├── app.py                 # Flask backend with API routes
├── requirements.txt       # Python dependencies
├── Dockerfile             # Container definition
├── docker-compose.yml     # Multi-service orchestration
├── .env.example          # Environment template
├── .gitignore            # Git exclusions
├── README.md             # This file
├── static/
│   ├── css/
│   │   └── style.css     # Dark/light theme with animations
│   ├── js/
│   │   └── voice.js      # Browser audio & API client
│   └── audio/            # Generated audio files (temp)
└── templates/
    └── index.html        # Single-page application
```

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────┐
│  Browser (MediaRecorder, Web Audio API)             │
└──────────────┬──────────────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────────┐
│  Flask REST API (Rate Limiting, CORS)              │
├──────────────────────────────────────────────────────┤
│  ├─ Chat Route → Gemini API                        │
│  ├─ STT Route → Whisper (ffmpeg conversion)        │
│  ├─ TTS Route → Coqui (audio synthesis + caching)  │
│  └─ Conversation Management                        │
└──────────────┬──────────────────────────────────────┘
               │
    ┌──────────┼──────────┬──────────┐
    │          │          │          │
 ┌──▼──┐  ┌────▼──┐  ┌────▼──┐  ┌───▼──┐
 │Audio│  │Gemini │  │Whisper│  │Coqui │
 │Files│  │  API  │  │Models │  │ TTS  │
 └─────┘  └───────┘  └───────┘  └──────┘
```

## 🐳 Docker Deployment

### Build
```bash
docker-compose build
```

### Run
```bash
docker-compose up
```

### Logs
```bash
docker-compose logs -f voice-assistant
```

### Stop
```bash
docker-compose down
```

The Docker image includes:
- Python 3.11 slim base
- ffmpeg for audio conversion
- espeak-ng for text-to-speech
- All Python dependencies
- Optimized multi-stage build (~2GB final image)

## 🔧 Troubleshooting

### Models take too long to load
- First run downloads Whisper (~300MB) and Coqui models (~1GB)
- Gunicorn timeout increased to 5 minutes for model initialization
- Subsequent runs use cached models (much faster)

### "Gemini not configured" error
- Verify `GEMINI_API_KEY` is set in `.env`
- Check API key validity at https://aistudio.google.com/app/apikey
- Ensure key has quota available

### "ffmpeg is required" error
- **Ubuntu/Debian:** `sudo apt-get install ffmpeg espeak-ng`
- **macOS:** `brew install ffmpeg espeak-ng`
- **Windows:** Download from https://ffmpeg.org/download.html or use WSL2 + apt

### Audio transcription fails
- Ensure file is valid audio (WAV, MP3, WebM, OGG)
- Check file size < 25MB (configurable via `MAX_UPLOAD_MB`)
- Try different language or audio quality

### Rate limiting too strict
- Adjust `REQUESTS_PER_MINUTE` in `.env`
- Note: Gunicorn uses in-memory limiter (not recommended for production clusters)

## 🔐 Security Considerations

- **API Keys:** Never commit `.env` files; use `.env.example` as template
- **CORS:** Currently allows all origins; restrict in production
- **Rate Limiting:** IP-based and per-route; use Redis for multi-server deployments
- **File Uploads:** Validate MIME types and enforce size limits
- **Audio Cleanup:** Old files auto-pruned; adjust retention via `MAX_AUDIO_AGE_MINUTES`

## 📊 Performance Notes

- **STT Latency:** Whisper "base" ~5-15s for 30s audio on CPU; larger models slower
- **TTS Latency:** Coqui synthesis ~1-3s per response; caches recent phrases
- **Memory:** ~2GB for all models in memory; use smaller models for constrained environments
- **Concurrency:** Single-worker Docker setup; add workers/load balancer for production

## 📝 API Examples

### Python
```python
import requests

# Chat
response = requests.post('http://localhost:5000/api/chat', json={
    'message': 'Hello!',
    'audio': True
})
print(response.json()['reply'])

# Voice input
with open('recording.wav', 'rb') as f:
    files = {'file': f}
    response = requests.post('http://localhost:5000/api/speech-to-text', files=files)
    print(response.json()['transcript'])
```

### JavaScript
```javascript
// Chat with audio
const response = await fetch('/api/chat', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ message: 'Hi', audio: true })
});
const data = await response.json();
console.log(data.reply);
```

### cURL
```bash
# Health check
curl http://localhost:5000/health

# Chat
curl -X POST http://localhost:5000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"Hello","audio":true}'
```

## 📄 License

MIT License – see [LICENSE](LICENSE) file for details.

## 🤝 Contributing

Contributions welcome! Please:
1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📧 Support

- **Issues:** GitHub Issues for bug reports
- **Discussions:** GitHub Discussions for feature requests
- **Documentation:** See inline code comments

## 🗺️ Roadmap

- [ ] Streaming audio responses
- [ ] Multi-turn conversation context window expansion
- [ ] Additional TTS voices and language support
- [ ] Real-time waveform visualization improvements
- [ ] WebSocket support for lower-latency communication
- [ ] Conversation export (PDF/JSON)
- [ ] User authentication and persistent history
- [ ] Mobile native apps (React Native)
