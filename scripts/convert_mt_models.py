"""Builds the offline models the app downloads on first use.

Converts Helsinki-NLP's OPUS-MT es-en and en-es translation models and the
grammar model to CTranslate2 int8, zips each one with its SentencePiece
tokeniser(s), and prints the SHA-256 that belongs in ``src/local_mt.py`` or
``src/grammar.py``. Run it when a model is updated, then upload the zips to
the GitHub release tagged ``models`` and paste the new hashes:

    python -m venv convenv --system-site-packages && convenv\\Scripts\\activate
    pip install ctranslate2 "transformers<5" torch sentencepiece
    python scripts/convert_mt_models.py [output_dir] [name ...]

With no names every model is built; otherwise only the ones given, e.g.
``grammar-synthesis-small``.

Needs transformers and torch, which the app itself never ships: the whole
point of converting once is that users get a 68 MB zip per direction instead
of a 300 MB PyTorch checkpoint and the libraries to read it.
"""

import hashlib
import subprocess
import sys
import zipfile
from pathlib import Path

#: Folder name -> (Hugging Face repository, tokeniser files to copy).
MODELS = {
    "opus-mt-es-en": ("Helsinki-NLP/opus-mt-es-en", ("source.spm", "target.spm")),
    "opus-mt-en-es": ("Helsinki-NLP/opus-mt-en-es", ("source.spm", "target.spm")),
    # CoEdIT was chosen over pszemraj's grammar-synthesis family after a
    # side-by-side on dictated sentences: the T5-small, T5-base and
    # flan-T5-large variants all invented names ("Jose Mondragon" became
    # "Marco Polo" and "Jose Mondrian") and swapped nouns ("gizmo" became
    # "wifi", "button" became "menu"); CoEdIT-large changed nothing it was
    # not asked to. Its licence is CC-BY-NC-4.0: non-commercial use only.
    "coedit-large": ("grammarly/coedit-large", ("spiece.model",)),
}


def convert(name, out_dir):
    repo, tokenisers = MODELS[name]
    folder = out_dir / name
    subprocess.run(
        [sys.executable, "-m", "ctranslate2.converters.transformers",
         "--model", repo,
         "--output_dir", str(folder),
         "--quantization", "int8",
         "--copy_files", *tokenisers,
         "--force"],
        check=True)
    zip_path = out_dir / f"{name}-ct2-int8.zip"
    # Files sit at the root of the archive: the app unpacks it straight into
    # the model's folder and looks for model.bin there.
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for path in sorted(folder.iterdir()):
            z.write(path, path.name)
    digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    size_mb = round(zip_path.stat().st_size / 1e6)
    print(f"{zip_path.name}  {size_mb} MB  sha256={digest}")


def main():
    out_dir = Path(sys.argv[1] if len(sys.argv) > 1 else "build/mt-models")
    out_dir.mkdir(parents=True, exist_ok=True)
    for name in sys.argv[2:] or MODELS:
        convert(name, out_dir)


if __name__ == "__main__":
    main()
