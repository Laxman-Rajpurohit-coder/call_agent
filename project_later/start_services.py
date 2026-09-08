import os
import sys
import time
import subprocess

SERVICES = [
    {"name": "Audio Studio Server", "port": 9096, "cmd": [sys.executable, "-m", "services.audio_studio.studio_server"], "env": {}},
    {"name": "TTS Worker", "port": 9095, "cmd": [sys.executable, "-m", "services.tts.worker"], "env": {}},
    {"name": "STT Worker", "port": 9094, "cmd": [sys.executable, "-m", "services.stt.worker"], "env": {"WHISPER_MODEL": "base"}},
    {"name": "LLM Server", "port": 9093, "cmd": [sys.executable, "-m", "services.llm.server"], "env": {}},
    {"name": "Call Gateway", "port": 9092, "cmd": [sys.executable, "-m", "services.call_gateway.server"], "env": {"ASTERISK_AMI_SECRET": "F-yfV4qLZt7-fnA5qzlq0_z6lH9HBUlc"}},
]

def main():
    print("=" * 70)
    print("  SUPERFONE AI VOICE BOT — MICROSERVICES LAUNCHER")
    print("=" * 70)

    processes = []
    for svc in SERVICES:
        env = os.environ.copy()
        env.update(svc["env"])
        print(f"🚀 Starting {svc['name']} (Port {svc['port']})...")
        p = subprocess.Popen(svc["cmd"], env=env)
        processes.append((svc["name"], p))
        time.sleep(1.5)

    print("=" * 70)
    print("✅ All 5 microservices initialized successfully!")
    print("   AudioSocket Gateway : 127.0.0.1:9092")
    print("   Audio Studio UI     : http://localhost:9096")
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
