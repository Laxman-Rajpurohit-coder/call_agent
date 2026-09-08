import os
import sys
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).parent
MODELS_DIRS = [
    BASE_DIR / "models",
    Path(r"c:\daily_works\superfone_call\models")
]

for d in MODELS_DIRS:
    d.mkdir(parents=True, exist_ok=True)

MODEL_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files/kokoro-v0_19.onnx"
VOICES_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files/voices.bin"

def download_file(url, label, target_filename):
    for models_dir in MODELS_DIRS:
        target_path = models_dir / target_filename
        if target_path.exists() and target_path.stat().st_size > 1000000:
            print(f"[OK] {label} already exists: {target_path} ({target_path.stat().st_size} bytes)")
            continue

        print(f"Downloading {label} from {url} to {target_path}...")
        def reporthook(count, block_size, total_size):
            if total_size > 0:
                percent = int(count * block_size * 100 / total_size)
                mb_downloaded = (count * block_size) / (1024 * 1024)
                mb_total = total_size / (1024 * 1024)
                sys.stdout.write(f"\rDownloading {label}: {percent}% ({mb_downloaded:.1f} MB / {mb_total:.1f} MB)")
                sys.stdout.flush()

        try:
            opener = urllib.request.build_opener()
            opener.addheaders = [('User-Agent', 'Mozilla/5.0')]
            urllib.request.install_opener(opener)
            urllib.request.urlretrieve(url, target_path, reporthook)
            print(f"\n[DONE] Saved {label} -> {target_path} ({target_path.stat().st_size} bytes)")
        except Exception as e:
            print(f"\n[ERROR] Failed to download {label} to {target_path}: {e}")

if __name__ == "__main__":
    download_file(MODEL_URL, "Kokoro v0.19 ONNX Model", "kokoro-v0_19.onnx")
    download_file(VOICES_URL, "Kokoro Voices Binary Archive", "voices.bin")
