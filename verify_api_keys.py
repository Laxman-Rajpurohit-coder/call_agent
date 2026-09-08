import os
import asyncio
import httpx

def load_env():
    env_vars = {}
    env_path = '.env'
    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and '=' in line and not line.startswith('#'):
                    k, v = line.split('=', 1)
                    env_vars[k.strip()] = v.strip().strip('"').strip("'")
    return env_vars

env = load_env()
groq_key = env.get('GROQ_API_KEY', os.environ.get('GROQ_API_KEY', ''))
deepgram_key = env.get('DEEPGRAM_API_KEY', os.environ.get('DEEPGRAM_API_KEY', ''))
cartesia_key = env.get('CARTESIA_API_KEY', os.environ.get('CARTESIA_API_KEY', ''))

async def test_groq():
    if not groq_key:
        print("[GROQ API]     MISSING KEY")
        return False
    async with httpx.AsyncClient() as client:
        try:
            r = await client.get('https://api.groq.com/openai/v1/models', headers={'Authorization': f'Bearer {groq_key}'}, timeout=10.0)
            if r.status_code == 200:
                print("[GROQ API]     CONNECTED (HTTP 200 OK)")
                return True
            else:
                print(f"[GROQ API]     FAILED (HTTP {r.status_code}): {r.text[:100]}")
                return False
        except Exception as e:
            print(f"[GROQ API]     ERROR: {e}")
            return False

async def test_deepgram():
    if not deepgram_key:
        print("[DEEPGRAM API] MISSING KEY")
        return False
    async with httpx.AsyncClient() as client:
        try:
            r = await client.get('https://api.deepgram.com/v1/projects', headers={'Authorization': f'Token {deepgram_key}'}, timeout=10.0)
            if r.status_code in [200, 201]:
                print("[DEEPGRAM API] CONNECTED (HTTP 200 OK)")
                return True
            else:
                print(f"[DEEPGRAM API] FAILED (HTTP {r.status_code}): {r.text[:100]}")
                return False
        except Exception as e:
            print(f"[DEEPGRAM API] ERROR: {e}")
            return False

async def test_cartesia():
    if not cartesia_key:
        print("[CARTESIA API] MISSING KEY")
        return False
    async with httpx.AsyncClient() as client:
        try:
            r = await client.get('https://api.cartesia.ai/voices', headers={'X-API-Key': cartesia_key, 'Cartesia-Version': '2024-06-10'}, timeout=10.0)
            if r.status_code == 200:
                print("[CARTESIA API] CONNECTED (HTTP 200 OK)")
                return True
            else:
                print(f"[CARTESIA API] FAILED (HTTP {r.status_code}): {r.text[:100]}")
                return False
        except Exception as e:
            print(f"[CARTESIA API] ERROR: {e}")
            return False

async def main():
    print("=" * 60)
    print("  VERIFYING ENTERPRISE VOICE AGENT API CONNECTIONS")
    print("=" * 60)
    await test_groq()
    await test_deepgram()
    await test_cartesia()
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
