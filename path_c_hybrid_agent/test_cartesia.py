import sys
import os
import asyncio
import httpx

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from path_c_hybrid_agent.config import CARTESIA_API_KEY

async def test_cartesia():
    print("Testing Cartesia Sonic Hindi API...")
    url = "https://api.cartesia.ai/tts/bytes"
    headers = {
        "X-API-Key": CARTESIA_API_KEY,
        "Cartesia-Version": "2024-06-10",
        "Content-Type": "application/json"
    }
    payload = {
        "model_id": "sonic-3",
        "transcript": "राम राम सा! माली सैनी समाज सेवा फाउंडेशन में आपरो स्वागत है।",
        "voice": {"mode": "id", "id": "56e35e2d-6eb6-4226-ab8b-9776515a7094"},
        "output_format": {
            "container": "wav",
            "encoding": "pcm_s16le",
            "sample_rate": 24000
        }
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.post(url, headers=headers, json=payload)
            print(f"Status: {res.status_code}, Bytes: {len(res.content)}")
            if res.status_code != 200:
                print("Error body:", res.text)
            else:
                with open("cartesia_hindi_test.wav", "wb") as f:
                    f.write(res.content)
                print("Saved cartesia_hindi_test.wav successfully!")
    except Exception as e:
        print(f"Exception: {e}")

if __name__ == "__main__":
    asyncio.run(test_cartesia())
