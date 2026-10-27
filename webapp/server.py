"""The HTTP side: one page, one status call, one dictation call.

``create_app`` builds the FastAPI application. The Whisper model loads on a
background thread the moment the app starts, exactly as the desktop window
does, so the page opens at once and says "loading" until the model is in.
The desktop window's speech-model switch reaches this server too (see
``src.webpeer``), so a lighter model there means a lighter one here. The
page has the same switch; it changes this server's copy only.

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

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src import __version__
from src.languages import LANG_NAMES
from src.pipeline import Pipeline
from src.settings import CHOICES
from src.transcriber import ModelNotLoaded

from . import guard

STATIC = Path(__file__).parent / "static"

#: Clips longer than this are refused before decoding. The desktop app caps
#: a recording at 30 minutes; 64 MB of opus is well past that.
MAX_UPLOAD_BYTES = 64 * 1024 * 1024


def _decode(clip: bytes):
    from faster_whisper.audio import decode_audio
    return decode_audio(io.BytesIO(clip), sampling_rate=16000)


class _Models:
    """Loads the transcriber off the request thread, and reloads it on a
    speech-model switch.

    One worker does all the loading. A switch that arrives while it is busy
    only changes ``mode``; the worker sees the change when its current load
    ends and loads again, so two quick switches cannot finish in the wrong
    order and leave the older choice loaded.
    """

    def __init__(self, transcriber, mode):
        self._transcriber = transcriber
        self.mode = mode
        self.device = None
        self.error = None
        self.pipeline = None
        self._loaded = False
        self._lock = threading.Lock()
        self._thread = None

    def start(self):
        with self._lock:
            self._start_worker()

    def switch(self, mode):
        with self._lock:
            if mode == self.mode and (self._loaded or self._thread):
                return
            self.mode = mode
            self._loaded = False
            self.device = None
            self.error = None
            self._start_worker()

    def _start_worker(self):
        if self._thread is None:
            self._thread = threading.Thread(target=self._load, daemon=True)
            self._thread.start()

    def _load(self):
        while True:
            wanted = self.mode
            device, error = None, None
            try:
                device = self._transcriber.load(wanted)
            except Exception as exc:  # noqa: BLE001 - shown on the status call
                error = f"{type(exc).__name__}: {exc}"
            with self._lock:
                if self.mode != wanted:
                    continue
                self._thread = None
                if error is not None:
                    self.error = error
                    return
                # Built once: the pipeline holds the grammar model, which
                # has nothing to do with Whisper and should survive a swap.
                if self.pipeline is None:
                    self.pipeline = Pipeline(self._transcriber)
                self.device = device
                self._loaded = True
                return

    @property
    def ready(self) -> bool:
        return self._loaded


class _SpeechModel(BaseModel):
    mode: str


class _Clip(BaseModel):
    text: str


#: Far more than any dictation; a cap so the endpoint cannot be used to
#: push megabytes onto the clipboard.
MAX_CLIP_CHARS = 200_000


def create_app(transcriber=None, remote_user="", remote_password="",
               remote_users="", decode=_decode,
               speech_model="best", copy_to_clipboard=None) -> FastAPI:
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
        speech_model: The ``transcriber.MODES`` key to load at start.
        copy_to_clipboard: ``callable(str) -> bool`` setting this PC's
            clipboard; ``clipboard.copy`` when omitted, swapped out in
            tests so they leave the real clipboard alone.
    """
    if transcriber is None:
        from src.transcriber import Transcriber
        transcriber = Transcriber()
    if copy_to_clipboard is None:
        from .clipboard import copy as copy_to_clipboard
    if speech_model not in CHOICES["speech_model"]:
        speech_model = "best"
    models = _Models(transcriber, speech_model)

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

    # Only the main account may take the GPU back remotely; a guest can
    # dictate but not change what the PC runs. No main account, no remote
    # switching at all.
    owner = remote_user if remote_user and remote_password else None

    def is_local(request):
        host = request.client.host if request.client else None
        return not guard.is_remote(host, request.headers)

    def may_switch(request):
        if is_local(request):
            return True
        return owner is not None and request.state.remote_user == owner

    @app.get("/api/status")
    def status(request: Request):
        return {
            "version": __version__,
            "ready": models.ready,
            "device": models.device,
            "model": getattr(transcriber, "model_name", None),
            "speech_model": models.mode,
            "error": models.error,
            "languages": LANG_NAMES,
            "translate_modes": CHOICES["translate_mode"],
            "tidy_modes": CHOICES["tidy_mode"],
            "speech_models": CHOICES["speech_model"],
            "can_switch": may_switch(request),
            "pc_clipboard": is_local(request),
        }

    @app.post("/api/clipboard")
    def clipboard(clip: _Clip, request: Request):
        # A phone's copy belongs on the phone, so only a page on this PC
        # gets the PC's clipboard. The JSON body keeps other web pages from
        # writing it: cross-origin they would need a preflight this server
        # never answers.
        if not is_local(request):
            raise HTTPException(403, "the PC's clipboard is set from the PC only")
        if len(clip.text) > MAX_CLIP_CHARS:
            raise HTTPException(413, "text too long for the clipboard")
        if not copy_to_clipboard(clip.text):
            raise HTTPException(503, "could not reach the clipboard")
        return {"copied": True}

    @app.post("/api/speech-model", status_code=202)
    def speech_model_switch(choice: _SpeechModel, request: Request):
        # The JSON body is a CSRF guard: a web page cannot send one
        # cross-origin without a preflight this server never answers.
        if not may_switch(request):
            raise HTTPException(
                403, "only the owner's account can switch the speech model")
        if choice.mode not in CHOICES["speech_model"]:
            raise HTTPException(422, f"unknown speech model {choice.mode!r}")
        models.switch(choice.mode)
        return {"speech_model": models.mode, "ready": models.ready}

    @app.post("/api/dictate")
    async def dictate(clip: UploadFile = File(...),
                      translate_mode: str = Form("offline"),
                      tidy_mode: str = Form("basic")):
        if not models.ready:
            raise HTTPException(503, models.error or "model still loading")
        # The model can go between that check and the transcription when a
        # switch lands in the gap; the transcriber then refuses rather
        # than crash, and that is a 503 too.
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
        try:
            result = models.pipeline.run(audio, translate_mode=translate_mode,
                                         tidy_mode=tidy_mode)
        except ModelNotLoaded as exc:
            raise HTTPException(503, "the speech model is switching") from exc
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
