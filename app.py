import logging
import os
import subprocess
import uuid
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import wave

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request
from werkzeug.exceptions import HTTPException
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import requests
import speech_recognition as sr
import pyttsx3
from dashscope import Generation
from openai import OpenAI

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
FFMPEG_PATH = os.getenv("FFMPEG_PATH")
QWEN_API_KEY = os.getenv("QWEN_API_KEY")
QWEN_MODEL = os.getenv("QWEN_MODEL", "qwen-turbo")
QWEN_TEMPERATURE = float(os.getenv("QWEN_TEMPERATURE", "0.7"))

# Provider selection (qwen | openrouter)
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "qwen").lower()
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "qwen2.5:7b-instruct")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
OPENROUTER_TEMPERATURE = float(os.getenv("OPENROUTER_TEMPERATURE", "0.7"))

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY", "change-me")
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024
# Disable static caching in dev to avoid stale JS
if os.getenv("FLASK_DEBUG", "false").lower() == "true":
    app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0

# Security: basic rate limiting per client IP.
limiter = Limiter(get_remote_address, app=app, default_limits=[f"{REQUESTS_PER_MINUTE} per minute"])
CORS(app, resources={r"/api/*": {"origins": "*"}})

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("voice-assistant")

conversation_history: List[Dict[str, str]] = []
provider_configured = False
openrouter_client: Optional[OpenAI] = None
stt_service = None
tts_service = None
ASSET_VERSION = os.getenv("ASSET_VERSION", str(int(datetime.utcnow().timestamp())))


def resolve_ffmpeg_path() -> Optional[str]:
    """Locate ffmpeg binary via env, PATH, or common install paths."""
    candidates: List[Optional[str]] = []
    if FFMPEG_PATH:
        candidates.append(FFMPEG_PATH)
    candidates.append(shutil.which("ffmpeg"))
    candidates.extend(
        [
            r"C:\\Program Files\\ffmpeg\\bin\\ffmpeg.exe",
            r"C:\\Program Files (x86)\\ffmpeg\\bin\\ffmpeg.exe",
        ]
    )

    for cand in candidates:
        if not cand:
            continue
        path = Path(cand)
        if path.is_file():
            return str(path)
    return None


def configure_qwen():
    """Initialize Qwen API configuration."""
    if not QWEN_API_KEY:
        logger.warning("QWEN_API_KEY is not set; chat routes will be disabled.")
        return False
    Generation.api_key = QWEN_API_KEY
    logger.info("Qwen API configured successfully")
    return True

def configure_openrouter():
    """Initialize OpenRouter (OpenAI-compatible) client."""
    global openrouter_client
    if not OPENROUTER_API_KEY:
        logger.warning("OPENROUTER_API_KEY is not set; chat routes will be disabled.")
        return False
    try:
        openrouter_client = OpenAI(base_url=OPENROUTER_BASE_URL, api_key=OPENROUTER_API_KEY)
        logger.info("OpenRouter client configured: %s", OPENROUTER_BASE_URL)
        return True
    except Exception as exc:
        logger.error("Failed to configure OpenRouter: %s", exc)
        return False


class STTService:
    def __init__(self, model_size: str = "default"):
        self.recognizer = sr.Recognizer()
        self.model_size = model_size
        self.ffmpeg_bin = resolve_ffmpeg_path()

    def _convert_to_wav(self, path: Path) -> Path:
        """Ensure audio is 16k mono wav for SpeechRecognition."""
        # If it's already WAV, no conversion needed
        if path.suffix.lower() == ".wav":
            return path
        # Conversion required for non-WAV inputs; ensure ffmpeg is available
        if not self.ffmpeg_bin:
            raise RuntimeError(
                "ffmpeg is required for audio conversion but could not be found. "
                "Set FFMPEG_PATH to the ffmpeg.exe location or add it to PATH."
            )
        wav_path = path.with_suffix(".wav")
        cmd = [
            self.ffmpeg_bin,
            "-y",
            "-i",
            str(path),
            "-ar",
            "16000",
            "-ac",
            "1",
            str(wav_path),
        ]
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except FileNotFoundError:
            raise RuntimeError("ffmpeg is required for audio conversion but is not installed")
        except subprocess.CalledProcessError:
            raise RuntimeError("Failed to convert audio; file may be corrupted or unsupported")
        return wav_path

    def transcribe(self, path: Path, language: Optional[str] = None) -> Dict:
        try:
            wav_path = self._convert_to_wav(path)
            with sr.AudioFile(str(wav_path)) as source:
                audio = self.recognizer.record(source)
            
            language_code = language if language else "en-US"
            result = self.recognizer.recognize_google(audio, language=language_code, show_all=True)
            if isinstance(result, dict) and result.get("alternative"):
                best = result["alternative"][0]
                text = (best.get("transcript") or "").strip()
                return {
                    "text": text,
                    "segments": [{"text": text, "start": 0.0, "end": 0.0}],
                    "language": language_code,
                }
            else:
                raise sr.UnknownValueError()
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
    try:
        logger.info("Uploaded audio saved: name=%s mime=%s size=%s bytes", file_storage.filename, file_storage.mimetype, path.stat().st_size)
    except Exception:
        pass
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
    history = conversation_history[-(CONVERSATION_WINDOW * 2):]
    messages = [
        {"role": "system", "content": "You are a concise, helpful voice assistant."},
        *history,
        {"role": "user", "content": message},
    ]

    if LLM_PROVIDER == "openrouter":
        if not openrouter_client:
            raise RuntimeError("OpenRouter not configured. Set OPENROUTER_API_KEY in .env")
        try:
            resp = openrouter_client.chat.completions.create(
                model=OPENROUTER_MODEL,
                messages=messages,
                temperature=OPENROUTER_TEMPERATURE,
            )
            return (resp.choices[0].message.content or "").strip()
        except Exception as exc:
            raise RuntimeError(f"OpenRouter request failed: {exc}")
    else:  # default to Qwen (DashScope)
        if not provider_configured:
            raise RuntimeError("Qwen API not configured. Set QWEN_API_KEY in .env")
        try:
            # Collapse messages to a single prompt for DashScope simple Generation
            history_context = "\n".join([f"{m['role']}: {m['content']}" for m in history])
            prompt = f"You are a concise, helpful voice assistant.\n\nConversation history:\n{history_context}\n\nuser: {message}\nassistant:"
            response = Generation.call(
                model=QWEN_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=QWEN_TEMPERATURE,
                top_p=0.8,
            )
            if response.status_code == 200:
                return response.output.text.strip()
            else:
                raise RuntimeError(f"Qwen API error: {response.message}")
        except Exception as exc:
            raise RuntimeError(f"Qwen API request failed: {exc}")


@app.route("/")
@limiter.exempt
def index():
    return render_template("index.html", asset_version=ASSET_VERSION)


@app.route("/health")
@limiter.exempt
def health():
    return jsonify({
        "status": "ok",
        # LLM info
        "provider": LLM_PROVIDER,
        "configured": provider_configured,
        "model": QWEN_MODEL if LLM_PROVIDER != "openrouter" else OPENROUTER_MODEL,
        # Legacy frontend fields for display
        "gemini": False,
        "gemini_model": GEMINI_MODEL,
        # STT/TTS info expected by UI
        "stt": bool(stt_service),
        "whisper_model": WHISPER_MODEL,
        "tts": bool(tts_service),
        "tts_model": TTS_MODEL,
        # Diagnostics
        "ffmpeg": bool(getattr(stt_service, "ffmpeg_bin", None)),
    })


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
    if not provider_configured:
        return jsonify({"error": f"{LLM_PROVIDER} provider not configured"}), 503

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
        logger.exception("LLM completion failed")
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
        logger.info("STT requested with language: %s", language or "(default)")
        if audio_path.suffix.lower() == ".wav":
            try:
                with wave.open(str(audio_path), "rb") as wf:
                    params = {
                        "channels": wf.getnchannels(),
                        "width": wf.getsampwidth(),
                        "rate": wf.getframerate(),
                        "frames": wf.getnframes(),
                        "duration_sec": round(wf.getnframes() / float(wf.getframerate() or 1), 3),
                    }
                    logger.info("WAV meta: %s", params)
            except Exception as _exc:
                logger.warning("Failed to inspect WAV: %s", _exc)
        result = stt_service.transcribe(audio_path, language=language)
        prune_audio()
    except Exception as exc:
        logger.exception("Whisper transcription failed")
        msg = str(exc)
        try:
            apath = f"/static/audio/{audio_path.name}"
        except Exception:
            apath = None
        if "Could not understand audio" in msg:
            return jsonify({
                "transcript": "",
                "segments": [],
                "language": language or None,
                "audio_url": apath,
                "status": "no_speech"
            }), 200
        return jsonify({"error": msg}), 500

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


@app.errorhandler(HTTPException)
def handle_http_exception(e: HTTPException):
    # Preserve proper HTTP codes like 404 for missing favicon
    return jsonify({"error": e.description}), e.code


@app.errorhandler(Exception)
def handle_uncaught_exception(e):
    logger.exception("Unhandled exception")
    return jsonify({"error": "Internal server error"}), 500


@app.route("/favicon.ico")
@limiter.exempt
def favicon():
    # Avoid noisy errors if no favicon is provided
    return ("", 204)


# Initialize services at import time
if LLM_PROVIDER == "openrouter":
    provider_configured = configure_openrouter()
else:
    provider_configured = configure_qwen()
try:
    stt_service = STTService(WHISPER_MODEL)
    if not stt_service.ffmpeg_bin:
        logger.warning("ffmpeg not found; set FFMPEG_PATH or add ffmpeg to PATH for STT")
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
