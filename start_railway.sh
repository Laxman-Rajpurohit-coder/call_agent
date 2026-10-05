#!/bin/bash
set -e

echo "=========================================================="
echo "  SUPERFONE AI VOICE PLATFORM — RAILWAY PRODUCTION LAUNCHER"
echo "=========================================================="

export PORT="${PORT:-8080}"
export PYTHONUNBUFFERED=1
export PYTHONPATH="/app:${PYTHONPATH}"

# Ensure data and recording directories exist
mkdir -p /app/recordings /app/data

# 1. Initialize Prisma client if schema exists
if [ -f "/app/prisma/schema.prisma" ]; then
    echo "Syncing Prisma client..."
    npx prisma generate || true
fi

# 2. Start FastAPI Platform on internal port 9090
echo "🚀 Starting FastAPI Platform on port 9090..."
python3 -m uvicorn services.dashboard.app.main:app --host 0.0.0.0 --port 9090 &

# 3. Start LLM Server on internal port 9093
echo "🚀 Starting LLM Server on port 9093..."
python3 -m services.llm.server &

# 4. Start TTS Worker on internal port 9095
echo "🚀 Starting TTS Worker on port 9095..."
python3 -m services.tts.worker &

# 5. Start STT Worker on internal port 9094
echo "🚀 Starting STT Worker on port 9094..."
python3 -m services.stt.worker &

# 6. Start Call Gateway on internal port 9092
echo "🚀 Starting Call Gateway on port 9092..."
python3 -m services.call_gateway.server &

# Wait for background services to bind
sleep 3

# 7. Start Node.js Express Gateway (foreground process listening on $PORT)
echo "🚀 Starting Node Gateway & React Dashboard on port ${PORT}..."
exec node server.js
