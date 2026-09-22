"""EN <-> ES translation on this machine, with no network after the first run.

The models are OPUS-MT (Helsinki-NLP), converted once to CTranslate2 int8 and
published as release assets of this repository. CTranslate2 is already in the
build for Whisper, so the only thing this adds to the download is
``sentencepiece`` for the tokeniser and, on first use, the two models
themselves: about 75 MB per direction, kept next to the settings file.

Why a fixed URL and a pinned SHA-256 rather than the Hugging Face hub: the hub
is what rate limits and captive portals already break for Whisper, and a hash
in the code means a swapped file on the server cannot reach the app. The
download is verified before a single byte of it is unpacked.
"""

import hashlib
import os
import re
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

from .settings import default_path

_RELEASE = ("https://github.com/mondragon-developer/easy-bilingual-voice-to-text"
            "/releases/download/models")

#: Seconds to wait on the download before giving up on a byte.
DOWNLOAD_TIMEOUT = 30.0

#: Sentences longer than this many tokens are cut so the model never sees a
#: sequence it was not trained for; Marian models degrade badly past 512.
_MAX_TOKENS = 400


@dataclass(frozen=True)
class ModelSpec:
    """One translation direction: where its files come from and how big."""

    source: str
    target: str
    sha256: str
    size_mb: int

    @property
    def name(self) -> str:
        return f"opus-mt-{self.source}-{self.target}"

    @property
    def url(self) -> str:
        return f"{_RELEASE}/{self.name}-ct2-int8.zip"


#: Both directions the two panes can need. The hashes are of the zip files
#: as published; ``scripts/convert_mt_models.py`` prints them.
MODELS = {
    ("es", "en"): ModelSpec(
        "es", "en",
        "75b9a5f77dfcd9b7da5cb8a2a1508fecbc4014cbaf2060c9d6a0e3ec6c474ef0", 68),
    ("en", "es"): ModelSpec(
        "en", "es",
        "1eeba0c16f516180a35fa0ee16f5f6581f402c9980db876ddac56fb243a662ae", 69),
}


def models_dir() -> Path:
    """Where the unpacked models live: ``<settings folder>/models``."""
    return default_path().parent / "models"


#: What ``_Engine`` opens. A folder missing any of these is not a model.
_REQUIRED_FILES = ("model.bin", "source.spm", "target.spm")


def _is_complete(folder) -> bool:
    return all((Path(folder) / name).is_file() for name in _REQUIRED_FILES)


def is_installed(spec: ModelSpec, root=None) -> bool:
    """True when every file the engine needs is present for ``spec``."""
    return _is_complete(Path(root or models_dir()) / spec.name)


def _safe_members(archive: zipfile.ZipFile, dest: Path):
    """Yield archive members that unpack strictly inside ``dest``.

    A zip can name a member ``../../something``; extracting it blindly would
    write outside the models folder. Anything that resolves elsewhere, and
    any directory entry, is skipped.
    """
    dest = dest.resolve()
    for member in archive.infolist():
        if member.is_dir():
            continue
        target = (dest / member.filename).resolve()
        if dest not in target.parents:
            continue
        yield member, target


def _download(url: str, into, progress=None, session=None):
    """Stream ``url`` into the open file ``into``, reporting progress.

    Args:
        url: What to fetch.
        into: A writable binary file object.
        progress: Optional ``callable(done_bytes, total_bytes)``; ``total`` is
            0 when the server did not say.
        session: Something with ``requests.get``'s interface, for tests.
    """
    if session is None:
        import requests
        session = requests
    with session.get(url, stream=True, timeout=DOWNLOAD_TIMEOUT) as resp:
        resp.raise_for_status()
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        for chunk in resp.iter_content(chunk_size=1 << 16):
            if not chunk:
                continue
            into.write(chunk)
            done += len(chunk)
            if progress is not None:
                progress(done, total)


def install(spec: ModelSpec, root=None, progress=None, session=None) -> Path:
    """Download, verify and unpack one model. Returns its folder.

    The zip is written to a temporary file in the models folder, hashed, and
    only then unpacked into a scratch directory that is renamed into place at
    the end, so a crash or a bad download can never leave a half-installed
    model that ``is_installed`` would then trust.

    Raises:
        ValueError: The download's SHA-256 does not match ``spec.sha256``.
        Exception: Whatever the HTTP layer raises when offline.
    """
    root = Path(root or models_dir())
    root.mkdir(parents=True, exist_ok=True)
    final = root / spec.name
    if is_installed(spec, root):
        return final

    handle, temp_zip = tempfile.mkstemp(dir=str(root), prefix=".download-",
                                        suffix=".zip")
    scratch = None
    try:
        with os.fdopen(handle, "wb") as fh:
            _download(spec.url, fh, progress=progress, session=session)
        digest = hashlib.sha256()
        with open(temp_zip, "rb") as fh:
            for block in iter(lambda: fh.read(1 << 20), b""):
                digest.update(block)
        if digest.hexdigest() != spec.sha256:
            raise ValueError(f"{spec.name}: downloaded file failed verification")

        scratch = Path(tempfile.mkdtemp(dir=str(root), prefix=".unpack-"))
        with zipfile.ZipFile(temp_zip) as archive:
            for member, target in _safe_members(archive, scratch):
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as src, open(target, "wb") as dst:
                    shutil.copyfileobj(src, dst)
        # The zip holds the files at its root; tolerate one wrapping folder.
        # Every file the engine opens must be there, not just the weights:
        # a model without its tokenisers would install and then fail on
        # every translation.
        inner = scratch
        if not _is_complete(inner):
            subdirs = [p for p in scratch.iterdir() if p.is_dir()]
            if len(subdirs) == 1 and _is_complete(subdirs[0]):
                inner = subdirs[0]
        if not _is_complete(inner):
            raise ValueError(
                f"{spec.name}: archive does not contain a complete model")
        if final.exists():
            shutil.rmtree(final)
        os.replace(inner, final)
        return final
    finally:
        for leftover in (temp_zip, scratch):
            if leftover is None:
                continue
            try:
                if os.path.isdir(leftover):
                    shutil.rmtree(leftover)
                else:
                    os.unlink(leftover)
            except OSError:
                pass


def _split_sentences(text: str):
    """Sentence-ish pieces so each one is translated as a unit."""
    parts = re.split(r"(?<=[.!?…])\s+", text.strip())
    return [part for part in parts if part]


class LocalTranslator:
    """Lazily loads one CTranslate2 model per direction and translates.

    Loading is deferred until the first translation in that direction, so
    the app's start-up never pays for a model it may not use, and the model
    is fetched on demand rather than at install time.
    """

    def __init__(self, root=None, ensure=install):
        """
        Args:
            root: Models folder. Defaults to ``models_dir()``.
            ensure: ``callable(spec, root, progress) -> Path`` that makes the
                model available; ``install`` by default, a stub in tests.
        """
        self._root = root
        self._ensure = ensure
        self._engines = {}

    @property
    def root(self) -> Path:
        return Path(self._root or models_dir())

    def is_ready(self, source: str, target: str) -> bool:
        """True when no download is needed for this direction."""
        return is_installed(MODELS[(source, target)], self.root)

    def _engine(self, source, target, progress=None):
        key = (source, target)
        if key not in self._engines:
            spec = MODELS[key]
            folder = self._ensure(spec, self.root, progress)
            self._engines[key] = _Engine(folder)
        return self._engines[key]

    def translate(self, text: str, source: str, target: str,
                  progress=None) -> str:
        """Translate ``text`` from ``source`` to ``target`` on this machine.

        Args:
            text: Text in ``source``.
            source: ``"en"`` or ``"es"``.
            target: The other one.
            progress: Passed to the model download when one is needed;
                ``callable(done_bytes, total_bytes)``.

        Returns:
            str: The translation ("" for empty input).

        Raises:
            KeyError: An unsupported direction.
            Exception: A download that failed (offline, or verification).
        """
        text = text.strip()
        if not text:
            return ""
        engine = self._engine(source, target, progress)
        sentences = _split_sentences(text)
        return " ".join(engine.translate(sentences)).strip()


class _Engine:
    """The CTranslate2 model plus its two SentencePiece tokenisers."""

    def __init__(self, folder):
        import ctranslate2
        import sentencepiece as spm

        folder = Path(folder)
        self._translator = ctranslate2.Translator(str(folder), device="cpu",
                                                  compute_type="int8")
        self._source = spm.SentencePieceProcessor(
            model_file=str(folder / "source.spm"))
        self._target = spm.SentencePieceProcessor(
            model_file=str(folder / "target.spm"))

    def translate(self, sentences):
        """Translate a list of sentences, one result per sentence."""
        # Marian models were trained with an end-of-sentence marker after
        # every source; without it the decoder never sees a reason to stop
        # and loops the same phrase until the length limit.
        batch = [self._source.encode(s, out_type=str)[:_MAX_TOKENS] + ["</s>"]
                 for s in sentences]
        results = self._translator.translate_batch(
            batch, beam_size=4, max_decoding_length=_MAX_TOKENS + 50)
        out = []
        for result in results:
            tokens = result.hypotheses[0]
            out.append(self._target.decode(tokens).strip())
        return out
