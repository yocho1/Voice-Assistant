import logging
import os
import subprocess
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import requests
import speech_recognition as sr
import pyttsx3

# Load environment early so defaults and type coercion work below.
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
AUDIO_DIR = BASE_DIR / "static" / "audio"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
GEMINI_TEMPERATURE = float(os.getenv("GEMINI_TEMPERATURE", "0.7"))
GEMINI_MAX_TOKENS = int(os.getenv("GEMINI_MAX_TOKENS", "512"))
CONVERSATION_WINDOW = int(os.getenv("CONVERSATION_WINDOW", "5"))
REQUESTS_PER_MINUTE = os.getenv("REQUESTS_PER_MINUTE", "60")
MAX_AUDIO_AGE_MINUTES = int(os.getenv("MAX_AUDIO_AGE_MINUTES", "60"))
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "25"))

WHISPER_MODEL = os.getenv("WHISPER_MODEL", "SpeechRecognition")
TTS_MODEL = os.getenv("TTS_MODEL", "pyttsx3")
TTS_VOICE = os.getenv("TTS_VOICE", "default")
AUDIO_FORMAT = os.getenv("AUDIO_FORMAT", "wav")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "mistral")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY", "change-me")
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024

# Security: basic rate limiting per client IP.
limiter = Limiter(get_remote_address, app=app, default_limits=[f"{REQUESTS_PER_MINUTE} per minute"])
CORS(app, resources={r"/api/*": {"origins": "*"}})

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("voice-assistant")

conversation_history: List[Dict[str, str]] = []
ollama_model = None
stt_service = None
tts_service = None


def configure_ollama():
    """Check if Ollama is running."""
    try:
        response = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=5)
        if response.status_code == 200:
            logger.info("Ollama is running and ready")
            return True
    except Exception as exc:
        logger.warning("Ollama is not running at %s: %s", OLLAMA_HOST, exc)
    return False


class STTService:
    def __init__(self, model_size: str = "default"):
        self.recognizer = sr.Recognizer()
        self.model_size = model_size

    def transcribe(self, path: Path, language: Optional[str] = None) -> Dict:
        try:
            with sr.AudioFile(str(path)) as source:
                audio = self.recognizer.record(source)
            
            language_code = language if language else "en-US"
            text = self.recognizer.recognize_google(audio, language=language_code)
            
            return {
                "text": text.strip(),
                "segments": [{"text": text.strip(), "start": 0.0, "end": 0.0}],
                "language": language_code,
            }
        except sr.UnknownValueError:
            raise RuntimeError("Could not understand audio")
        except sr.RequestError as exc:
            raise RuntimeError(f"Speech recognition service error: {exc}")


class TTSService:
    def __init__(self, model_name: str, default_voice: str, audio_format: str):
        self.model_name = model_name
        self.default_voice = default_voice
        self.audio_format = audio_format.lower()
        self.engine = pyttsx3.init()
        self.cache: Dict[Tuple[str, str], Path] = {}
        self.cache_limit = 20

    def synthesize(self, text: str, voice: Optional[str] = None) -> Path:
        key = (text, voice or self.default_voice)
        cached = self.cache.get(key)
        if cached and cached.exists():
            return cached

        audio_path = AUDIO_DIR / f"tts-{uuid.uuid4().hex}.wav"
        try:
            self.engine.save_to_file(text, str(audio_path))
            self.engine.runAndWait()
        except Exception as exc:
            raise RuntimeError(f"TTS synthesis failed: {exc}")

        self.cache[key] = audio_path
        self._evict_cache()
        return audio_path

    def _evict_cache(self):
        if len(self.cache) <= self.cache_limit:
            return
        oldest_key = next(iter(self.cache))
        try:
            self.cache[oldest_key].unlink(missing_ok=True)
        finally:
            self.cache.pop(oldest_key, None)


def prune_audio(max_age_minutes: int = MAX_AUDIO_AGE_MINUTES) -> None:
    cutoff = datetime.utcnow() - timedelta(minutes=max_age_minutes)
    for path in AUDIO_DIR.glob("*"):
        try:
            if datetime.utcfromtimestamp(path.stat().st_mtime) < cutoff:
                path.unlink(missing_ok=True)
        except Exception:
            logger.debug("Skipping cleanup for %s", path)


def allowed_audio(mimetype: str) -> bool:
    return mimetype.startswith("audio/") or mimetype in {
        "application/octet-stream",
    }


def save_audio_file(file_storage) -> Path:
    ext = (Path(file_storage.filename).suffix or ".wav").lower()
    filename = f"{uuid.uuid4().hex}{ext}"
    path = AUDIO_DIR / filename
    file_storage.save(path)
    return path


def append_history(role: str, content: str) -> None:
    conversation_history.append({"role": role, "content": content})
    if len(conversation_history) > CONVERSATION_WINDOW * 2:
        del conversation_history[0 : len(conversation_history) - CONVERSATION_WINDOW * 2]


def build_prompt(user_message: str) -> List[Dict[str, str]]:
    history = conversation_history[-(CONVERSATION_WINDOW * 2) :]
    return [
        {"role": "system", "content": "You are a concise, helpful voice assistant."},
        *history,
        {"role": "user", "content": user_message},
    ]


def chat_completion(message: str) -> str:
    if not ollama_model:
        raise RuntimeError("Ollama not configured or running")
    
    history_context = "\n".join([f"{m['role']}: {m['content']}" for m in conversation_history[-(CONVERSATION_WINDOW * 2):]])
    prompt = f"You are a concise, helpful voice assistant.\n\nConversation history:\n{history_context}\n\nuser: {message}\nassistant:"
    
    try:
        response = requests.post(
            f"{OLLAMA_HOST}/api/generate",
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "temperature": GEMINI_TEMPERATURE,
            },
            timeout=60
        )
        response.raise_for_status()
        result = response.json()
        return result.get("response", "").strip()
    except requests.exceptions.RequestException as exc:
        raise RuntimeError(f"Ollama request failed: {exc}")


@app.route("/")
@limiter.exempt
def index():
    return render_template("index.html")


@app.route("/health")
@limiter.exempt
def health():
    return jsonify(
        {
            "status": "ok",
            "ollama": bool(ollama_model),
            "stt": bool(stt_service),
            "tts": bool(tts_service),
            "ollama_model": OLLAMA_MODEL,
            "ollama_host": OLLAMA_HOST,
        }
    )


@app.route("/api/conversation", methods=["GET"])
def get_conversation():
    return jsonify({"history": conversation_history[-(CONVERSATION_WINDOW * 2):]})


@app.route("/api/conversation/reset", methods=["POST"])
def reset_conversation():
    conversation_history.clear()
    return jsonify({"status": "reset"})


@app.route("/api/chat", methods=["POST"])
@limiter.limit("30 per minute")
def chat():
    if not ollama_model:
        return jsonify({"error": "Ollama not running. Start it with: ollama run mistral"}), 503

    payload = request.get_json(silent=True) or {}
    message = (payload.get("message") or "").strip()
    wants_audio = bool(payload.get("audio"))

    if not message:
        return jsonify({"error": "Message is required"}), 400

    try:
        reply = chat_completion(message)
        append_history("user", message)
        append_history("assistant", reply)
    except Exception as exc:
        logger.exception("Ollama completion failed")
        return jsonify({"error": str(exc)}), 500

    audio_url = None
    if wants_audio and tts_service:
        try:
            audio_path = tts_service.synthesize(reply)
            audio_url = f"/static/audio/{audio_path.name}"
        except Exception as exc:
            logger.exception("TTS synthesis failed")
            audio_url = None

    return jsonify({"reply": reply, "audio_url": audio_url, "history": conversation_history[-(CONVERSATION_WINDOW * 2):]})


@app.route("/api/speech-to-text", methods=["POST"])
@limiter.limit("30 per minute")
def speech_to_text_route():
    if not stt_service:
        return jsonify({"error": "Whisper not configured"}), 503

    file = request.files.get("file")
    if not file or file.filename == "":
        return jsonify({"error": "No audio file provided"}), 400

    if not allowed_audio(file.mimetype):
        return jsonify({"error": "Unsupported audio type"}), 400

    language = request.form.get("language") or None

    try:
        audio_path = save_audio_file(file)
        result = stt_service.transcribe(audio_path, language=language)
        prune_audio()
    except Exception as exc:
        logger.exception("Whisper transcription failed")
        return jsonify({"error": str(exc)}), 500

    return jsonify({"transcript": result.get("text", ""), "segments": result.get("segments", []), "language": result.get("language"), "audio_url": f"/static/audio/{audio_path.name}"})


@app.route("/api/text-to-speech", methods=["POST"])
@limiter.limit("30 per minute")
def text_to_speech_route():
    if not tts_service:
        return jsonify({"error": "TTS not configured"}), 503

    payload = request.get_json(silent=True) or {}
    text = (payload.get("text") or "").strip()
    voice = (payload.get("voice") or "").strip() or None
    if not text:
        return jsonify({"error": "Text is required"}), 400

    try:
        audio_path = tts_service.synthesize(text, voice=voice)
        prune_audio()
    except Exception as exc:
        logger.exception("TTS synthesis failed")
        return jsonify({"error": str(exc)}), 500

    return jsonify({"audio_url": f"/static/audio/{audio_path.name}"})


@app.errorhandler(429)
def handle_rate_limit(e):
    return jsonify({"error": "Rate limit exceeded"}), 429


@app.errorhandler(Exception)
def handle_exception(e):
    logger.exception("Unhandled exception")
    return jsonify({"error": "Internal server error"}), 500


# Initialize services at import time
ollama_model = configure_ollama()
try:
    stt_service = STTService(WHISPER_MODEL)
except Exception as exc:
    logger.error("Failed to load speech recognition: %s", exc)
    stt_service = None

try:
    tts_service = TTSService(TTS_MODEL, TTS_VOICE, AUDIO_FORMAT)
except Exception as exc:
    logger.error("Failed to load text-to-speech: %s", exc)
    tts_service = None


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=os.getenv("FLASK_DEBUG", "false").lower() == "true")
