"""
Multilingual Live Speaker Call Showcase
Uses User-Selected Voice Profiles:
  - Hindi   : H1 (Kavita - Female) & H4 (Ayush - Male)
  - English : E1 (Arushi - Female) & E4 (Kabir - Male)
  - Marwadi : M1 (Kavita - Female) & M3 (Shreeraj - Male)
"""

import os
import sys
import time
import wave
import asyncio
import winsound
import tempfile

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from path_c_hybrid_agent.tts_cartesia import synthesize_speech_hd

MULTILINGUAL_SHOWCASE = [
    # ── 1. HINDI SCENARIO ───────────────────────────────────────────────────────
    {
        "lang_title": "🇮🇳 HINDI TELEPHONY CALL (H4 Ayush vs H1 Kavita)",
        "caller_name": "Rajesh (Caller - H4 Ayush Male)",
        "caller_uuid": "791d5162-d5eb-40f0-8189-f19db44611d8",
        "caller_text": "नमस्ते! मैं माली सैनी समाज सेवा फाउंडेशन के बारे में जानना चाहता हूँ।",
        "bot_name": "Pratham AI (Coordinator - H1 Kavita Female)",
        "bot_uuid": "56e35e2d-6eb6-4226-ab8b-9776515a7094",
        "bot_text": "नमस्ते! माली सैनी समाज सेवा फाउंडेशन में आपका स्वागत है। मैं आपकी क्या सहायता कर सकती हूँ?"
    },

    # ── 2. ENGLISH / HINGLISH SCENARIO ─────────────────────────────────────────
    {
        "lang_title": "🇬🇧 ENGLISH / HINGLISH CALL (E4 Kabir vs E1 Arushi)",
        "caller_name": "Vikram (Caller - E4 Kabir Male)",
        "caller_uuid": "cb9c954d-bcaa-43ed-82bf-aeb5e88a3cb5",
        "caller_text": "Hello! I would like to make a 1000 rupees donation and get an 80G tax receipt.",
        "bot_name": "Pratham AI (Coordinator - E1 Arushi Female)",
        "bot_uuid": "95d51f79-c397-46f9-b49a-23763d3eaa2d",
        "bot_text": "Hello! Yes absolutely, you can complete your donation via UPI or Netbanking and we will issue your 80G tax receipt immediately."
    },

    # ── 3. MARWADI SCENARIO ─────────────────────────────────────────────────────
    {
        "lang_title": "🚩 MARWADI RAJASTHANI CALL (M3 Shreeraj vs M1 Kavita)",
        "caller_name": "Rathore Ji (Caller - M3 Shreeraj Male)",
        "caller_uuid": "c7be5dde-c1e6-4ebe-9096-ddc4b4edb1cc",
        "caller_text": "राम-राम सा, हुकम! माली सैनी समाज सेवा फाउंडेशन में आपरो घणो-घणो आभार।",
        "bot_name": "Pratham AI (Coordinator - M1 Kavita Female)",
        "bot_uuid": "56e35e2d-6eb6-4226-ab8b-9776515a7094",
        "bot_text": "राम-राम सा! आपरो यह योगदान हमारे समाज सेवा कार्यों में घणो काम आवेगा। बहुत-बहुत धन्यवाद सा!"
    }
]


def play_audio_out_loud(pcm_bytes: bytes, sample_rate: int = 24000):
    if not pcm_bytes:
        return
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = tmp.name

        with wave.open(tmp_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(pcm_bytes)

        winsound.PlaySound(tmp_path, winsound.SND_FILENAME)
        try:
            os.remove(tmp_path)
        except Exception:
            pass
    except Exception as e:
        print(f"[Playback Note] {e}")


async def main():
    print("=" * 80)
    print("  🎙️ USER-SELECTED MULTILINGUAL VOICE SHOWCASE")
    print("  Selected Voice Models: H1, H4, E1, E4, M1, M3")
    print("================================================================================\n")

    for item in MULTILINGUAL_SHOWCASE:
        print(f"\n{item['lang_title']}")
        print("-" * 75)

        # 1. Caller Speaks Out Loud
        print(f"🗣️ {item['caller_name']}:")
        print(f"   \"{item['caller_text']}\"")
        c_pcm = await synthesize_speech_hd(item['caller_text'], voice_id=item['caller_uuid'], sample_rate=24000)
        if c_pcm:
            play_audio_out_loud(c_pcm, sample_rate=24000)
        time.sleep(0.4)

        # 2. Agent Responds Out Loud
        print(f"🤖 {item['bot_name']}:")
        print(f"   \"{item['bot_text']}\"")
        b_pcm = await synthesize_speech_hd(item['bot_text'], voice_id=item['bot_uuid'], sample_rate=24000)
        if b_pcm:
            play_audio_out_loud(b_pcm, sample_rate=24000)
        time.sleep(0.8)

    print("\n" + "=" * 80)
    print("  ✅ MULTILINGUAL SHOWCASE WITH SELECTED ACCENTS COMPLETED SUCCESSFULLY!")
    print("================================================================================")

if __name__ == "__main__":
    asyncio.run(main())
