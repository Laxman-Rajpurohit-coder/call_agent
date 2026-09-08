import os
import urllib.request
import sys

MODELS_DIR = r"c:\daily_works\superfone_call\models"
os.makedirs(MODELS_DIR, exist_ok=True)

MODEL_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files/kokoro-v0_19.onnx"
VOICES_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files/voices.json"

model_path = os.path.join(MODELS_DIR, "kokoro-v0_19.onnx")
voices_path = os.path.join(MODELS_DIR, "voices.json")

def download_file(url, target_path, label):
    if os.path.exists(target_path) and os.path.getsize(target_path) > 1000:
        print(f"[OK] {label} already exists: {target_path} ({os.path.getsize(target_path)} bytes)")
        return
    print(f"Downloading {label} from {url}...")
    def reporthook(count, block_size, total_size):
        if total_size > 0:
            percent = int(count * block_size * 100 / total_size)
            sys.stdout.write(f"\rDownloading {label}: {percent}% ({count * block_size / 1024 / 1024:.1f} MB / {total_size / 1024 / 1024:.1f} MB)")
            sys.stdout.flush()
    urllib.request.urlretrieve(url, target_path, reporthook)
    print(f"\n[DONE] Saved {label} -> {target_path} ({os.path.getsize(target_path)} bytes)")

if __name__ == "__main__":
    download_file(MODEL_URL, model_path, "Kokoro v0.19 ONNX Model")
    download_file(VOICES_URL, voices_path, "Kokoro Voices Definition")
