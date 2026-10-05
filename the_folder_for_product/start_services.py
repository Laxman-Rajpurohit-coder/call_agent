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

candidate_pythons = [
    os.path.join(ROOT_DIR, "venv", "Scripts", "python.exe"),
    os.path.join(ROOT_DIR, "..", "venv", "Scripts", "python.exe"),
    sys.executable
]
python_bin = sys.executable
for cp in candidate_pythons:
    if os.path.exists(cp) and check_has_deps(cp):
        python_bin = cp
        break

def is_port_in_use(port: int) -> bool:
    import socket
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            return s.connect_ex(('127.0.0.1', port)) == 0
    except Exception:
        return False

npm_bin = "npm.cmd" if sys.platform == "win32" else "npm"

SERVICES = [
    {"name": "Dashboard Platform", "port": 9090, "cmd": [python_bin, "-m", "uvicorn", "services.dashboard.app.main:app", "--port", "9090", "--host", "0.0.0.0"], "env": {}, "cwd": ROOT_DIR},
    {"name": "Voice Agent & CRM Server", "port": 8080, "cmd": ["node", "server.js"], "env": {}, "cwd": ROOT_DIR},
    {"name": "Frontend Dashboard UI", "port": 3000, "cmd": [npm_bin, "run", "dev"], "env": {}, "cwd": os.path.join(ROOT_DIR, "frontend")},
    {"name": "Telephony AI Gateway", "port": 9096, "cmd": [python_bin, "path_c_hybrid_agent/twilio_gateway.py"], "env": {}, "cwd": ROOT_DIR},
    {"name": "TTS Worker", "port": 9095, "cmd": [python_bin, "-m", "services.tts.worker"], "env": {}, "cwd": ROOT_DIR},
    {"name": "STT Worker", "port": 9094, "cmd": [python_bin, "-m", "services.stt.worker"], "env": {"WHISPER_MODEL": "base"}, "cwd": ROOT_DIR},
    {"name": "LLM Server", "port": 9093, "cmd": [python_bin, "-m", "services.llm.server"], "env": {}, "cwd": ROOT_DIR},
    {"name": "Call Gateway", "port": 9092, "cmd": [python_bin, "-m", "services.call_gateway.server"], "env": {"ASTERISK_AMI_SECRET": "F-yfV4qLZt7-fnA5qzlq0_z6lH9HBUlc"}, "cwd": ROOT_DIR},
    {"name": "Vobiz WS Bridge", "port": 9098, "cmd": [python_bin, "-m", "services.vobiz_bridge.server"], "env": {}, "cwd": ROOT_DIR},
    {"name": "Ngrok Tunnel", "port": 4040, "cmd": ["ngrok", "http", "9098", "--url", "drool-envoy-sandy.ngrok-free.dev"], "env": {}, "cwd": ROOT_DIR},
]

def main():
    print("=" * 70)
    print("  SUPERFONE AI VOICE BOT & CAMPAIGN PLATFORM — SERVICES LAUNCHER")
    print("=" * 70)

    logs_dir = os.path.join(ROOT_DIR, "logs")
    os.makedirs(logs_dir, exist_ok=True)

    processes = []
    for svc in SERVICES:
        port = svc["port"]
        if is_port_in_use(port):
            print(f"ℹ️  {svc['name']} already active on Port {port} (reusing existing instance).")
            continue

        env = os.environ.copy()
        env.update(svc.get("env", {}))
        env["PYTHONPATH"] = ROOT_DIR + os.pathsep + env.get("PYTHONPATH", "")
        cwd = svc.get("cwd", ROOT_DIR)
        
        slug = svc["name"].lower().replace(" ", "_").replace("&", "").replace("__", "_")
        log_path = os.path.join(logs_dir, f"{slug}.log")
        log_f = open(log_path, "a", encoding="utf-8")
        
        print(f"🚀 Starting {svc['name']} (Port {port})... -> {os.path.basename(log_path)}")
        p = subprocess.Popen(svc["cmd"], env=env, cwd=cwd, stdout=log_f, stderr=subprocess.STDOUT)
        processes.append((svc, p, log_f))
        time.sleep(1.2)

    print("=" * 70)
    print("✅ All services initialized successfully!")
    print("   React Dashboard Web UI  : http://localhost:3000")
    print("   AI Voice Ops Platform UI: http://localhost:9090")
    print("   Voice Agent & CRM Server: http://localhost:8080")
    print("   AudioSocket Gateway     : 127.0.0.1:9092")
    print("   Telephony AI Gateway    : http://localhost:9096")
    print("   LLM Server              : http://localhost:9093")
    print("   STT Worker              : http://localhost:9094")
    print("   TTS Worker              : http://localhost:9095")
    print("   Vobiz WS Bridge         : 127.0.0.1:9098")
    print("   Ngrok Public Tunnel     : https://drool-envoy-sandy.ngrok-free.dev")
    print("=" * 70)

    try:
        while True:
            time.sleep(3)
            for idx, (svc, p, log_f) in enumerate(processes):
                ret = p.poll()
                if ret is not None:
                    port = svc["port"]
                    if not is_port_in_use(port):
                        print(f"⚠️ [{time.strftime('%H:%M:%S')}] {svc['name']} stopped (code {ret}). Auto-restarting...")
                        env = os.environ.copy()
                        env.update(svc.get("env", {}))
                        env["PYTHONPATH"] = ROOT_DIR + os.pathsep + env.get("PYTHONPATH", "")
                        cwd = svc.get("cwd", ROOT_DIR)
                        new_p = subprocess.Popen(svc["cmd"], env=env, cwd=cwd, stdout=log_f, stderr=subprocess.STDOUT)
                        processes[idx] = (svc, new_p, log_f)
    except KeyboardInterrupt:
        print("\nStopping all supervised services...")
        for svc, p, log_f in processes:
            try:
                p.terminate()
            except Exception:
                pass
            try:
                log_f.close()
            except Exception:
                pass

if __name__ == "__main__":
    main()

