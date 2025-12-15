# Voice Assistant

> A production-ready AI voice assistant with OpenRouter LLM support, browser-based WAV recording, and graceful speech-to-text fallback. Built with Flask and featuring a modern, responsive web UI.

[![Python 3.12+](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Flask](https://img.shields.io/badge/Flask-3.0.3-green.svg)](https://flask.palletsprojects.com/)

## ✨ Features

### Core Capabilities

- **OpenRouter LLM Integration** – Use any model from OpenRouter (Mistral, GPT-4, Claude, etc.) with your own API key
- **Browser WAV Recording** – Custom client-side audio encoder (16kHz mono PCM) with no server dependencies
- **Speech-to-Text** – Google STT with graceful fallback (returns "no speech" instead of errors)
- **Text-to-Speech** – pyttsx3 for natural voice synthesis
- **Multi-Provider Support** – Easy switching between OpenRouter, Gemini, Qwen, and Ollama

### User Experience

- **Voice Recording** – Browser-native audio capture with automatic 16kHz resampling and normalization
- **Automatic Silence Detection** – Stops recording after 1.2s of silence
- **Live Transcripts** – Real-time transcription display with language detection
- **Dark/Light Mode** – Theme preference persists across sessions
- **Service Info Panel** – Real-time health check showing LLM provider, model, STT/TTS status
- **Copy-to-Clipboard** – Quickly export AI responses
- **Responsive Design** – Mobile-first, works on desktop/tablet/phone

### Developer-Friendly

- **REST API** – Clean, predictable endpoints for all operations
- **Rate Limiting** – IP-based rate limiting (60 req/min)
- **CORS Enabled** – Cross-origin requests supported
- **Comprehensive Logging** – Detailed error and debug information with WAV metadata
- **Health Checks** – `/health` endpoint with service status and configuration
- **No FFmpeg Required** – Client-side WAV encoding eliminates server-side conversion

## 🚀 Quick Start

### Prerequisites

- Python 3.12+
- OpenRouter API key (get one free at [openrouter.ai](https://openrouter.ai))
- Modern browser with Web Audio API support

### Installation

```bash
# Clone repository
git clone https://github.com/yourusername/Voice-Assistant.git
cd Voice-Assistant

# Create virtual environment
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # macOS/Linux

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env and add your OPENROUTER_API_KEY

# Run application
python app.py
```

Visit http://localhost:5000

## 📋 Configuration

### Environment Variables (.env)

```bash
# LLM Provider (openrouter, gemini, qwen, ollama)
LLM_PROVIDER=openrouter

# OpenRouter Configuration
OPENROUTER_API_KEY=your_api_key_here
OPENROUTER_MODEL=mistralai/mistral-7b-instruct

# Optional: FFmpeg path (not required for basic functionality)
# FFMPEG_PATH=/path/to/ffmpeg

# Optional: Server settings
# PORT=5000
# REQUESTS_PER_MINUTE=60
```

Get your free OpenRouter API key at [openrouter.ai](https://openrouter.ai)

## 📋 API Endpoints

### Health Check

```http
GET /health
```

Returns service status, provider info, and configuration.

**Response:**

```json
{
  "status": "healthy",
  "provider": "openrouter",
  "model": "mistralai/mistral-7b-instruct",
  "ffmpeg_available": true,
  "stt_available": true,
  "tts_available": true
}
```

### Chat

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
  "reply": "Machine learning is a branch of AI...",
  "audio_url": "/static/audio/tts_1234567890.wav",
  "history": [...]
}
```

### Speech-to-Text

```http
POST /api/speech-to-text
Content-Type: multipart/form-data

file: <audio_file.wav>
language: en-US
```

**Response (Success):**

```json
{
  "status": "success",
  "transcript": "Hello world"
}
```

**Response (No Speech Detected):**

```json
{
  "status": "no_speech",
  "transcript": ""
}
```

### Text-to-Speech

```http
POST /api/text-to-speech
Content-Type: application/json

{
  "text": "Hello, world!"
}
```

**Response:**

```json
{
  "audio_url": "/static/audio/tts_1234567890.wav"
}
```

### Conversation Management

```http
GET /api/conversation
```

Get current conversation history.

```http
POST /api/conversation/reset
```

Clear conversation history.

## ⚙️ Advanced Configuration

All configuration is managed through the `.env` file:

### LLM Provider Settings

- `LLM_PROVIDER` – `openrouter`, `gemini`, `qwen`, or `ollama` (default: `openrouter`)
- `OPENROUTER_API_KEY` – Your OpenRouter API key
- `OPENROUTER_MODEL` – Model identifier (e.g., `mistralai/mistral-7b-instruct`)
- `GEMINI_API_KEY` – Google Gemini API key (if using Gemini)
- `QWEN_API_KEY` – Qwen API key (if using Qwen)

### Speech Settings

- `FFMPEG_PATH` – Path to ffmpeg binary (optional, not required for WAV)
- `REQUESTS_PER_MINUTE` – Rate limit per IP (default: `60`)
- `PORT` – Server port (default: `5000`)

### Switching Providers

Edit your `.env` file and change `LLM_PROVIDER`:

```bash
# Use OpenRouter (recommended)
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=your_key
OPENROUTER_MODEL=mistralai/mistral-7b-instruct

# Use Google Gemini
LLM_PROVIDER=gemini
GEMINI_API_KEY=your_key

# Use Qwen
LLM_PROVIDER=qwen
QWEN_API_KEY=your_key

# Use local Ollama
LLM_PROVIDER=ollama
```

## 📁 Project Structure

```
Voice-Assistant/
├── app.py                 # Flask backend with LLM services
├── requirements.txt       # Python dependencies
├── .env.example          # Environment template
├── .gitignore            # Git exclusions
├── README.md             # Documentation
├── static/
│   ├── css/
│   │   └── style.css     # Dark/light theme styling
│   ├── js/
│   │   └── voice.js      # Custom WAV encoder & UI
│   ├── favicon.svg       # App icon
│   └── audio/            # Generated TTS files (temporary)
└── templates/
    └── index.html        # Single-page application
```

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────┐
│  Browser (Web Audio API, ScriptProcessorNode)       │
│  ├─ Capture raw audio (48kHz/44.1kHz)              │
│  ├─ Resample to 16kHz mono                         │
│  ├─ Normalize amplitude                            │
│  └─ Encode RIFF/WAVE PCM headers                   │
└──────────────┬──────────────────────────────────────┘
               │ (WAV blob)
┌──────────────▼──────────────────────────────────────┐
│  Flask REST API (CORS, Rate Limiting)              │
├──────────────────────────────────────────────────────┤
│  ├─ /api/chat → OpenRouter/Gemini/Qwen/Ollama     │
│  ├─ /api/speech-to-text → Google STT (graceful)   │
│  ├─ /api/text-to-speech → pyttsx3                 │
│  ├─ /health → Service diagnostics                 │
│  └─ Conversation Management                        │
└──────────────┬──────────────────────────────────────┘
               │
    ┌──────────┼──────────┬──────────┐
    │          │          │          │
 ┌──▼──┐  ┌────▼──┐  ┌────▼──┐  ┌───▼────┐
 │Audio│  │OpenRouter│ │Google│ │pyttsx3│
 │Cache│  │ LLM API │  │ STT  │ │  TTS  │
 └─────┘  └─────────┘  └──────┘ └───────┘
```

## 🔧 Troubleshooting

### Speech-to-Text Returns "No Speech Detected"

**Common causes:**

- Google STT API quota/access restrictions
- Microphone permissions not granted in browser
- Silent or low-amplitude audio recordings
- Network connectivity issues

**Solutions:**

1. **Check browser permissions:** Click the lock icon in address bar → Allow microphone access
2. **Test audio quality:** Speak clearly and close to microphone
3. **Alternative STT engines:**
   - Install Vosk: `pip install vosk` (offline, fast)
   - Use Whisper API: `pip install openai-whisper` (more accurate)
   - Try alternative services: Azure Speech, AWS Transcribe

**Current behavior:** App returns HTTP 200 with `status: "no_speech"` instead of errors, allowing graceful UI handling.

### "Provider not configured" Error

**OpenRouter:**

```bash
# Verify .env has:
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=sk-or-v1-...
```

**Gemini:**

```bash
# Get free key at https://aistudio.google.com/app/apikey
LLM_PROVIDER=gemini
GEMINI_API_KEY=your_key
```

**Ollama:**

```bash
# Install from https://ollama.ai
ollama run mistral
# Then:
LLM_PROVIDER=ollama
```

### FFmpeg Not Found (Optional)

FFmpeg is **not required** for basic functionality (browser sends WAV directly). Only needed for:

- Converting non-WAV uploads (MP3, WebM, OGG)
- Advanced audio processing

**Installation:**

- **Windows:** Download from https://ffmpeg.org or use `winget install ffmpeg`
- **macOS:** `brew install ffmpeg`
- **Linux:** `sudo apt install ffmpeg`

### Rate Limiting Issues

Default: 60 requests/minute per IP. Adjust in `.env`:

```bash
REQUESTS_PER_MINUTE=120
```

### Port Already in Use

```bash
# Change port in .env
PORT=8080

# Or kill existing process (Windows)
netstat -ano | findstr :5000
taskkill /PID <pid> /F
```

## 🔐 Security Best Practices

- ✅ **Never commit `.env` files** – Use `.env.example` as template
- ✅ **Rotate API keys regularly** – Especially if exposed
- ⚠️ **CORS allows all origins** – Restrict in production:
  ```python
  CORS(app, resources={r"/api/*": {"origins": ["https://yourdomain.com"]}})
  ```
- ✅ **Rate limiting enabled** – Per-IP throttling prevents abuse
- ✅ **Audio cleanup enabled** – TTS files auto-delete after use
- ⚠️ **No authentication** – Add JWT/OAuth for public deployments

## 📊 Performance & Optimization

### Response Times (typical)

- **LLM (OpenRouter):** 0.5-3s depending on model
- **STT (Google):** 1-2s for 3-second audio clips
- **TTS (pyttsx3):** 0.2-0.8s for short responses
- **End-to-end voice query:** 2-6s

### Resource Usage

- **Memory:** ~200MB base + ~50MB per concurrent request
- **CPU:** Low idle, spikes during TTS synthesis
- **Storage:** Audio files cached in `static/audio/` (auto-cleanup)

### Optimization Tips

1. **Use faster models:** `mistralai/mistral-7b-instruct` is balanced
2. **Enable caching:** TTS responses are already cached
3. **CDN for static assets:** Serve CSS/JS from CDN in production
4. **Async processing:** Consider Celery for long-running tasks

## 📝 Usage Examples

### Python Client

```python
import requests

# Health check
health = requests.get('http://localhost:5000/health').json()
print(f"Provider: {health['provider']}, Model: {health['model']}")

# Text chat
response = requests.post('http://localhost:5000/api/chat', json={
    'message': 'Explain quantum computing in simple terms',
    'audio': True
})
print(response.json()['reply'])

# Speech-to-text
with open('recording.wav', 'rb') as f:
    files = {'file': ('recording.wav', f, 'audio/wav')}
    data = {'language': 'en-US'}
    response = requests.post('http://localhost:5000/api/speech-to-text',
                           files=files, data=data)
    result = response.json()
    if result['status'] == 'success':
        print(f"Transcript: {result['transcript']}")
```

### JavaScript Fetch API

```javascript
// Check health
const health = await fetch('/health').then((r) => r.json())
console.log(`${health.provider} - ${health.model}`)

// Send chat message
const chat = await fetch('/api/chat', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    message: 'What is the weather like?',
    audio: false,
  }),
})
const chatData = await chat.json()
console.log(chatData.reply)
```

### cURL Commands

```bash
# Health check
curl http://localhost:5000/health

# Chat request
curl -X POST http://localhost:5000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"Hello, how are you?","audio":false}'

# Upload audio for transcription
curl -X POST http://localhost:5000/api/speech-to-text \
  -F "file=@recording.wav" \
  -F "language=en-US"

# Generate speech
curl -X POST http://localhost:5000/api/text-to-speech \
  -H "Content-Type: application/json" \
  -d '{"text":"Hello world"}'
```

## 🎯 Key Features Explained

### Custom WAV Encoder

The browser-side WAV encoder eliminates server dependencies:

- Captures raw audio at native sample rate (48kHz/44.1kHz)
- Resamples to 16kHz mono using linear interpolation
- Normalizes amplitude to 0.9 max if below 0.2 threshold
- Writes proper RIFF/WAVE headers with PCM format
- No ffmpeg required on server

### Graceful STT Fallback

Instead of throwing 500 errors on STT failures:

```json
{
  "status": "no_speech",
  "transcript": ""
}
```

This allows UI to show "(no speech detected)" instead of error messages.

### Service Info Panel

Real-time health monitoring displays:

- Active LLM provider and model
- STT/TTS availability status
- FFmpeg detection (optional)
- Server connectivity

### Multi-Provider LLM Support

Switch between providers by changing `.env`:

- **OpenRouter:** Access 100+ models via unified API
- **Gemini:** Google's fast, free tier available
- **Qwen:** Chinese LLM alternative
- **Ollama:** Run models locally (no API key)

## 🚀 Deployment Recommendations

### Production Checklist

- [ ] Use environment-specific `.env` (never commit secrets)
- [ ] Enable HTTPS (Let's Encrypt/Cloudflare)
- [ ] Restrict CORS origins
- [ ] Add authentication (JWT/OAuth)
- [ ] Use production WSGI server (Gunicorn/uWSGI)
- [ ] Set up logging (ELK stack/CloudWatch)
- [ ] Configure reverse proxy (Nginx/Apache)
- [ ] Enable monitoring (Prometheus/Grafana)
- [ ] Implement backups for conversation history
- [ ] Use Redis for rate limiting in multi-server setups

### Cloud Platform Options

**Heroku:**

```bash
heroku create your-voice-assistant
heroku config:set OPENROUTER_API_KEY=your_key
git push heroku main
```

**Railway:**

```bash
railway init
railway add
# Add OPENROUTER_API_KEY in dashboard
railway up
```

**AWS EC2:**

```bash
# Install dependencies
sudo apt update && sudo apt install python3-pip
pip3 install -r requirements.txt

# Run with Gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

## 📄 License

MIT License – Free to use, modify, and distribute.

## 🤝 Contributing

Contributions are welcome! To contribute:

1. Fork the repository
2. Create feature branch: `git checkout -b feature/your-feature`
3. Make changes and test thoroughly
4. Commit: `git commit -m 'Add: your feature description'`
5. Push: `git push origin feature/your-feature`
6. Open Pull Request with detailed description

### Development Guidelines

- Follow PEP 8 style guide for Python
- Add docstrings for new functions
- Update README for new features
- Test across different browsers
- Keep dependencies minimal

## 📧 Support & Community

- **Bug Reports:** GitHub Issues
- **Feature Requests:** GitHub Discussions
- **Documentation:** Inline code comments + this README

## 🙏 Acknowledgments

- OpenRouter for unified LLM API access
- Flask community for excellent documentation
- Browser Web Audio API contributors
- Open source speech recognition libraries

---

**Built with ❤️ using Flask, OpenRouter, and vanilla JavaScript**
