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
import google.generativeai as genai
import whisper
from TTS.api import TTS

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

WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base")
TTS_MODEL = os.getenv("TTS_MODEL", "tts_models/en/ljspeech/tacotron2-DDC")
TTS_VOICE = os.getenv("TTS_VOICE", "en-US")
AUDIO_FORMAT = os.getenv("AUDIO_FORMAT", "wav")

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
gemini_model = None
stt_service = None
tts_service = None


def configure_gemini():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.warning("GEMINI_API_KEY is not set; chat routes will be disabled.")
        return None
    genai.configure(api_key=api_key)
    return genai.GenerativeModel(GEMINI_MODEL)


class STTService:
    def __init__(self, model_size: str):
        self.model_size = model_size
        self.model = whisper.load_model(model_size)

    def _convert_to_wav(self, path: Path) -> Path:
        if path.suffix.lower() == ".wav":
            return path
        wav_path = path.with_suffix(".wav")
        cmd = [
            "ffmpeg",
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
        wav_path = self._convert_to_wav(path)
        result = self.model.transcribe(str(wav_path), language=language, fp16=False)
        raw_segments = result.get("segments", [])
        segments = [
            {
                "text": seg.get("text", "").strip(),
                "start": float(seg.get("start", 0.0) or 0.0),
                "end": float(seg.get("end", 0.0) or 0.0),
            }
            for seg in raw_segments
        ]
        return {
            "text": result.get("text", "").strip(),
            "segments": segments,
            "language": result.get("language"),
        }


class TTSService:
    def __init__(self, model_name: str, default_voice: str, audio_format: str):
        self.model_name = model_name
        self.default_voice = default_voice
        self.audio_format = audio_format.lower()
        self.tts = TTS(model_name)
        self.cache: Dict[Tuple[str, str, str], Path] = {}
        self.cache_limit = 20

    def _convert_format(self, wav_path: Path) -> Path:
        if self.audio_format == "wav":
            return wav_path
        out_path = wav_path.with_suffix(f".{self.audio_format}")
        cmd = ["ffmpeg", "-y", "-i", str(wav_path), str(out_path)]
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except FileNotFoundError:
            raise RuntimeError("ffmpeg is required for audio conversion but is not installed")
        except subprocess.CalledProcessError:
            raise RuntimeError("Failed to convert synthesized audio")
        return out_path

    def _evict_cache(self):
        if len(self.cache) <= self.cache_limit:
            return
        oldest_key = next(iter(self.cache))
        try:
            self.cache[oldest_key].unlink(missing_ok=True)
        finally:
            self.cache.pop(oldest_key, None)

    def synthesize(self, text: str, voice: Optional[str] = None) -> Path:
        key = (text, voice or self.default_voice, self.audio_format)
        cached = self.cache.get(key)
        if cached and cached.exists():
            return cached

        wav_path = AUDIO_DIR / f"tts-{uuid.uuid4().hex}.wav"
        kwargs = {}
        if voice or self.default_voice:
            speaker = voice or self.default_voice
            if getattr(self.tts, "speakers", None):
                kwargs["speaker"] = speaker
        try:
            self.tts.tts_to_file(text=text, file_path=str(wav_path), **kwargs)
        except Exception as exc:
            raise RuntimeError(f"TTS synthesis failed: {exc}")

        final_path = self._convert_format(wav_path)
        self.cache[key] = final_path
        self._evict_cache()
        return final_path


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
    if not gemini_model:
        raise RuntimeError("Gemini not configured")
    history_context = "\n".join([f"{m['role']}: {m['content']}" for m in conversation_history[-(CONVERSATION_WINDOW * 2):]])
    prompt = f"You are a concise, helpful voice assistant.\n\nConversation history:\n{history_context}\n\nuser: {message}\nassistant:"
    response = gemini_model.generate_content(
        prompt,
        generation_config=genai.types.GenerationConfig(
            temperature=GEMINI_TEMPERATURE,
            max_output_tokens=GEMINI_MAX_TOKENS,
        ),
    )
    return response.text.strip()


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
            "gemini": bool(gemini_model),
            "stt": bool(stt_service),
            "tts": bool(tts_service),
            "whisper_model": WHISPER_MODEL,
            "tts_model": TTS_MODEL,
            "gemini_model": GEMINI_MODEL,
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
    if not gemini_model:
        return jsonify({"error": "Gemini not configured"}), 503

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
        logger.exception("Gemini completion failed")
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


# Initialize third-party clients at import time to fail fast on boot.
gemini_model = configure_gemini()
try:
    stt_service = STTService(WHISPER_MODEL)
except Exception as exc:
    logger.error("Failed to load Whisper model: %s", exc)
    stt_service = None

try:
    tts_service = TTSService(TTS_MODEL, TTS_VOICE, AUDIO_FORMAT)
except Exception as exc:
    logger.error("Failed to load TTS model: %s", exc)
    tts_service = None


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=os.getenv("FLASK_DEBUG", "false").lower() == "true")
