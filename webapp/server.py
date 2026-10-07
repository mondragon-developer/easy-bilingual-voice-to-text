"""The HTTP side: one page, one status call, one dictation call.

``create_app`` builds the FastAPI application. The Whisper model loads on a
background thread the moment the app starts, exactly as the desktop window
does, so the page opens at once and says "loading" until the model is in.

The one piece of real work here is turning what a browser records into the
samples Whisper wants. Phones hand over webm/opus (Android, desktop Chrome)
or mp4/aac (iPhone). faster-whisper already decodes files through PyAV, so
the clip goes to it as is and comes back as 16 kHz float32, the same array
the desktop recorder produces.
"""

import io
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src import __version__
from src.languages import LANG_NAMES
from src.pipeline import Pipeline
from src.settings import CHOICES

from . import guard

STATIC = Path(__file__).parent / "static"

#: Clips longer than this are refused before decoding. The desktop app caps
#: a recording at 30 minutes; 64 MB of opus is well past that.
MAX_UPLOAD_BYTES = 64 * 1024 * 1024


def _decode(clip: bytes):
    from faster_whisper.audio import decode_audio
    return decode_audio(io.BytesIO(clip), sampling_rate=16000)


class _Models:
    """Loads the transcriber once, off the request thread."""

    def __init__(self, transcriber):
        self._transcriber = transcriber
        self.device = None
        self.error = None
        self.pipeline = None
        self._thread = None

    def start(self):
        self._thread = threading.Thread(target=self._load, daemon=True)
        self._thread.start()

    def _load(self):
        try:
            self.device = self._transcriber.load()
            self.pipeline = Pipeline(self._transcriber)
        except Exception as exc:  # noqa: BLE001 - shown on the status call
            self.error = f"{type(exc).__name__}: {exc}"

    @property
    def ready(self) -> bool:
        return self.pipeline is not None


def create_app(transcriber=None, remote_user="", remote_password="",
               remote_users="", decode=_decode) -> FastAPI:
    """Build the application.

    Args:
        transcriber: Object with the ``Transcriber`` interface; the real one
            when omitted. A test hands in a fake and no model loads.
        remote_user: User name a remote browser must present (HTTP Basic).
        remote_password: Its password.
        remote_users: More accounts, ``name:password`` pairs separated by
            commas. With no account at all, every remote request is
            refused; see ``guard``. Local use never signs in.
        decode: ``callable(bytes) -> numpy array`` turning an uploaded clip
            into 16 kHz samples; swapped out in tests.
    """
    if transcriber is None:
        from src.transcriber import Transcriber
        transcriber = Transcriber()
    models = _Models(transcriber)

    @asynccontextmanager
    async def _lifespan(_app):
        models.start()
        yield

    app = FastAPI(title="Speech to Text", version=__version__,
                  lifespan=_lifespan)
    app.state.remote_enabled = guard.install(app, remote_user, remote_password,
                                             remote_users)

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")

    @app.get("/api/status")
    def status():
        return {
            "version": __version__,
            "ready": models.ready,
            "device": models.device,
            "model": getattr(transcriber, "model_name", None),
            "error": models.error,
            "languages": LANG_NAMES,
            "translate_modes": CHOICES["translate_mode"],
            "tidy_modes": CHOICES["tidy_mode"],
        }

    @app.post("/api/dictate")
    async def dictate(clip: UploadFile = File(...),
                      translate_mode: str = Form("offline"),
                      tidy_mode: str = Form("basic")):
        if not models.ready:
            raise HTTPException(503, models.error or "model still loading")
        if translate_mode not in CHOICES["translate_mode"]:
            raise HTTPException(422, f"unknown translate_mode {translate_mode!r}")
        if tidy_mode not in CHOICES["tidy_mode"]:
            raise HTTPException(422, f"unknown tidy_mode {tidy_mode!r}")
        raw = await clip.read(MAX_UPLOAD_BYTES + 1)
        if len(raw) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, "recording too large")
        try:
            audio = decode(raw)
        except Exception as exc:  # noqa: BLE001 - the browser sent junk
            raise HTTPException(400, f"could not decode the recording: {exc}")
        if audio.size < 16000 * 0.3:
            return {"text": "", "note": "Recording was too short."}
        result = models.pipeline.run(audio, translate_mode=translate_mode,
                                     tidy_mode=tidy_mode)
        if not result.text:
            return {"text": "", "note": "No speech detected."}
        return {
            "text": result.text,
            "lang": result.lang,
            "lang_name": LANG_NAMES[result.lang],
            "probability": result.probability,
            "duration": result.duration,
            "translation": result.translation,
            "engine": result.engine,
            "notes": list(result.notes),
        }

    app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")
    return app
