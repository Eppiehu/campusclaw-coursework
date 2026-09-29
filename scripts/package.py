"""Create a submission zip without secrets, runtime data, or installed packages."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT.parent / "campusclaw-submission.zip"
EXCLUDED_PARTS = {"_vendor", "_tools", ".git", "data", "uploads", "__pycache__", ".pytest_cache"}
EXCLUDED_FILES = {".env", ".verify-cookie"}

with ZipFile(OUTPUT, "w", ZIP_DEFLATED) as archive:
    for file in ROOT.rglob("*"):
        if not file.is_file() or any(part in EXCLUDED_PARTS for part in file.relative_to(ROOT).parts):
            continue
        if file.name in EXCLUDED_FILES or file.suffix == ".pyc":
            continue
        archive.write(file, Path("campusclaw") / file.relative_to(ROOT))

print(OUTPUT)
