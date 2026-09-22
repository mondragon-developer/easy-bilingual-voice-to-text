"""Builds the offline translation models the app downloads on first use.

Converts Helsinki-NLP's OPUS-MT es-en and en-es models to CTranslate2 int8,
zips each one with its SentencePiece tokenisers, and prints the SHA-256 that
belongs in ``src/local_mt.py``. Run it when a model is updated, then upload
the zips to the GitHub release tagged ``models`` and paste the new hashes:

    python -m venv convenv && convenv\\Scripts\\activate
    pip install ctranslate2 "transformers<5" torch sentencepiece
    python scripts/convert_mt_models.py [output_dir]

Needs transformers and torch, which the app itself never ships: the whole
point of converting once is that users get a 68 MB zip per direction instead
of a 300 MB PyTorch checkpoint and the libraries to read it.
"""

import hashlib
import subprocess
import sys
import zipfile
from pathlib import Path

PAIRS = (("es", "en"), ("en", "es"))


def convert(source, target, out_dir):
    name = f"opus-mt-{source}-{target}"
    folder = out_dir / name
    subprocess.run(
        [sys.executable, "-m", "ctranslate2.converters.transformers",
         "--model", f"Helsinki-NLP/{name}",
         "--output_dir", str(folder),
         "--quantization", "int8",
         "--copy_files", "source.spm", "target.spm",
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
    for source, target in PAIRS:
        convert(source, target, out_dir)


if __name__ == "__main__":
    main()
