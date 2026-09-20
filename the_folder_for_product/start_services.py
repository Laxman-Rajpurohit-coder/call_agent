import os
import sys
import time
import subprocess

try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

from pathlib import Path

# Multi-Path .env resolution per Rule 4
possible_envs = [
    Path(__file__).parent / ".env",
    Path(__file__).parent.parent / ".env",
    Path(r"c:\daily_works\superfone_call\.env")
]

for env_path in possible_envs:
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    os.environ[k.strip()] = v.strip().strip('"').strip("'")
        print(f"[Launcher] Loaded .env configuration from {env_path}")
        break

ROOT_DIR = str(Path(__file__).parent.resolve())

def check_has_deps(py_path):
    try:
        res = subprocess.run([py_path, "-c", "import aiohttp, scipy, jwt"], capture_output=True, timeout=3)
        return res.returncode == 0
    except Exception:
        return False

venv_python = os.path.join(ROOT_DIR, "venv", "Scripts", "python.exe")
if os.path.exists(venv_python) and check_has_deps(venv_python):
    python_bin = venv_python
else:
    python_bin = sys.executable

SERVICES = [
    {"name": "Dashboard Platform", "port": 9090, "cmd": [python_bin, "-m", "uvicorn", "services.dashboard.app.main:app", "--port", "9090", "--host", "0.0.0.0"], "env": {}},
    {"name": "Telephony AI Gateway", "port": 9096, "cmd": [python_bin, "path_c_hybrid_agent/twilio_gateway.py"], "env": {}},
    {"name": "TTS Worker", "port": 9095, "cmd": [python_bin, "-m", "services.tts.worker"], "env": {}},
    {"name": "STT Worker", "port": 9094, "cmd": [python_bin, "-m", "services.stt.worker"], "env": {"WHISPER_MODEL": "base"}},
    {"name": "LLM Server", "port": 9093, "cmd": [python_bin, "-m", "services.llm.server"], "env": {}},
    {"name": "Call Gateway", "port": 9092, "cmd": [python_bin, "-m", "services.call_gateway.server"], "env": {"ASTERISK_AMI_SECRET": "F-yfV4qLZt7-fnA5qzlq0_z6lH9HBUlc"}},
]

def main():
    print("=" * 70)
    print("  SUPERFONE AI VOICE BOT & CAMPAIGN PLATFORM — SERVICES LAUNCHER")
    print("=" * 70)

    processes = []
    for svc in SERVICES:
        env = os.environ.copy()
        env.update(svc["env"])
        env["PYTHONPATH"] = ROOT_DIR + os.pathsep + env.get("PYTHONPATH", "")
        print(f"🚀 Starting {svc['name']} (Port {svc['port']})...")
        p = subprocess.Popen(svc["cmd"], env=env, cwd=ROOT_DIR)
        processes.append((svc["name"], p))
        time.sleep(1.5)

    print("=" * 70)
    print("✅ All 6 microservices initialized successfully!")
    print("   AI Voice Ops Platform UI: http://localhost:9090")
    print("   AudioSocket Gateway     : 127.0.0.1:9092")
    print("   Audio Studio Console UI : http://localhost:9096")
    print("=" * 70)

    try:
        for name, p in processes:
            p.wait()
    except KeyboardInterrupt:
        print("\nStopping services...")
        for name, p in processes:
            p.terminate()

if __name__ == "__main__":
    main()
