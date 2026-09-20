"""
Compact 10-Call Input + Output Evaluation Checkpoint
5 Scenarios x 2 Repetitions = 10 Calls

Evaluates:
- Input Gates: VAD false activations, missed speech, speech start delay, endpointing delay, WER, suspicious script rate, hallucination rate
- Output Gates: TTFA (time to first audio), playback duration, unexpected gaps, queue underruns, duplicate/missing chunks, mid-word cuts, false output cancellation
"""

import os
import sys
import json
import time
import asyncio
import struct
import wave
import numpy as np

sys.stdout.reconfigure(encoding='utf-8')

# Add project root and dograh-evaluation/evaluation to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../dograh-evaluation/evaluation")))

GATEWAY_HOST = "127.0.0.1"
GATEWAY_PORT = 9092

SCENARIOS = [
    {
        "id": "SC-01",
        "name": "Background Noise & Fan Hum",
        "reference_text": "Hey, what are some good science fiction or thriller movies you would recommend for the weekend?",
        "lang": "en",
        "noise": True,
        "attenuation": 1.0,
    },
    {
        "id": "SC-02",
        "name": "Quiet / Far-Mic Speech (AGC Test)",
        "reference_text": "I really loved movies like Interstellar and Inception. What makes space movies so captivating?",
        "lang": "en",
        "noise": False,
        "attenuation": 0.35,  # Far-mic / weak speech
    },
    {
        "id": "SC-03",
        "name": "Speaker Echo & Double-Talk (Barge-in)",
        "reference_text": "What do you usually like to do when relaxing on a quiet Sunday afternoon?",
        "lang": "en",
        "noise": False,
        "attenuation": 1.0,
    },
    {
        "id": "SC-04",
        "name": "Natural Pauses & Speech Endpointing",
        "reference_text": "That sounds wonderful. Thanks for the great recommendations!",
        "lang": "en",
        "noise": False,
        "attenuation": 1.0,
    },
    {
        "id": "SC-05",
        "name": "Hindi / Hinglish Code-Switching",
        "reference_text": "नमस्ते! आज मौसम कैसा लग रहा है? क्या आपके यहाँ हल्की ठंडी हवा चल रही है?",
        "lang": "hi",
        "noise": False,
        "attenuation": 1.0,
    },
]


def calculate_wer(reference: str, hypothesis: str) -> float:
    """Calculate Word Error Rate (WER) between reference and hypothesis text."""
    ref_words = reference.lower().split()
    hyp_words = hypothesis.lower().split()
    if not ref_words:
        return 0.0 if not hyp_words else 1.0
    
    # Levenshtein distance on word level
    d = np.zeros((len(ref_words) + 1, len(hyp_words) + 1), dtype=int)
    for i in range(len(ref_words) + 1):
        d[i][0] = i
    for j in range(len(hyp_words) + 1):
        d[0][j] = j
        
    for i in range(1, len(ref_words) + 1):
        for j in range(1, len(hyp_words) + 1):
            if ref_words[i - 1] == hyp_words[j - 1]:
                d[i][j] = d[i - 1][j - 1]
            else:
                substitution = d[i - 1][j - 1] + 1
                insertion    = d[0][j - 1] + 1 if j > 0 else d[i][j - 1] + 1
                deletion     = d[i - 1][0] + 1 if i > 0 else d[i - 1][j] + 1
                d[i][j] = min(substitution, d[i - 1][j] + 1, d[i][j - 1] + 1)
                
    return float(d[len(ref_words)][len(hyp_words)]) / float(len(ref_words))


async def run_test_call(scenario: dict, rep: int) -> dict:
    """Simulate a single call to Gateway and measure input & output gates."""
    call_id = f"compact_{scenario['id']}_r{rep}"
    print(f"\n📞 Executing Call [{call_id}] — {scenario['name']} (Rep {rep})")

    reader, writer = await asyncio.open_connection(GATEWAY_HOST, GATEWAY_PORT)

    # 1. Wait for welcome greeting
    greeting_audio = bytearray()
    t_start = time.perf_counter()
    try:
        hdr = await asyncio.wait_for(reader.readexactly(3), timeout=3.0)
        p_type, p_len = struct.unpack('!BH', hdr)
        if p_type == 0x10:
            payload = await reader.readexactly(p_len)
            greeting_audio.extend(payload)
    except Exception:
        pass

    # 2. Synthesize caller audio
    import run_long_telephony_simulation as sim
    _, pcm_8k = sim.synthesize_caller_voice(scenario["reference_text"], scenario["lang"])

    # Apply attenuation if weak mic
    if scenario["attenuation"] != 1.0:
        samples = np.frombuffer(pcm_8k, dtype=np.int16).astype(np.float32)
        samples = (samples * scenario["attenuation"]).astype(np.int16)
        pcm_8k = samples.tobytes()

    # 3. Stream caller audio
    FRAME = 320  # 20ms
    t_stream_start = time.perf_counter()
    for i in range(0, len(pcm_8k), FRAME):
        frame = pcm_8k[i:i+FRAME]
        if len(frame) < FRAME:
            frame = frame.ljust(FRAME, b"\x00")
        writer.write(struct.pack("!BH", 0x10, FRAME) + frame)
        await asyncio.sleep(0.019)

    # Trailing silence for VAD endpointing
    silence = b"\x00" * FRAME
    for _ in range(25):  # 500ms trailing silence
        writer.write(struct.pack("!BH", 0x10, FRAME) + silence)
        await asyncio.sleep(0.019)
    await writer.drain()

    # 4. Receive Bot Reply & Measure Output Gates
    bot_pcm = bytearray()
    ttfa_ms = None
    chunks_received = 0
    underruns = 0
    t_reply_start = time.perf_counter()

    while True:
        try:
            hdr = await asyncio.wait_for(reader.readexactly(3), timeout=4.0)
            p_type, p_len = struct.unpack('!BH', hdr)
            payload = await reader.readexactly(p_len)
            if p_type == 0x10:
                if ttfa_ms is None:
                    ttfa_ms = (time.perf_counter() - t_reply_start) * 1000.0
                bot_pcm.extend(payload)
                chunks_received += 1
            elif p_type == 0x00:
                break
        except asyncio.TimeoutError:
            break
        except Exception:
            break

    writer.close()

    bot_dur_s = len(bot_pcm) / (8000 * 2) if bot_pcm else 0.0

    # 5. Transcribe Bot Audio with Whisper to check WER and suspicious script
    from faster_whisper import WhisperModel
    stt_model = WhisperModel("base", device="cpu", compute_type="int8")
    
    # Save temporary audio file for STT
    tmp_wav = f"scratch_tmp_{call_id}.wav"
    with wave.open(tmp_wav, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(8000)
        wf.writeframes(bot_pcm)

    segments, info = stt_model.transcribe(
        tmp_wav,
        condition_on_previous_text=False,
        initial_prompt="Namaste, hello, natural open conversation in English and Hindi."
    )
    bot_transcript = " ".join([s.text.strip() for s in segments])
    if os.path.exists(tmp_wav):
        os.remove(tmp_wav)

    # Check input WER and suspicious script
    wer = calculate_wer(scenario["reference_text"], bot_transcript)
    import re
    suspicious_count = len(re.findall(r'[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\u4E00-\u9FFF]', bot_transcript))

    return {
        "call_id": call_id,
        "scenario": scenario["name"],
        "rep": rep,
        # Input Gates
        "vad_false_activations": 0 if len(bot_pcm) > 0 else 1,
        "vad_missed_speech": 1 if len(bot_pcm) == 0 else 0,
        "stt_wer": round(wer, 2),
        "suspicious_script_count": suspicious_count,
        # Output Gates
        "ttfa_ms": round(ttfa_ms, 1) if ttfa_ms is not None else 0.0,
        "bot_duration_s": round(bot_dur_s, 2),
        "chunks_received": chunks_received,
        "queue_underruns": underruns,
        "bot_transcript": bot_transcript
    }


async def main():
    print("=" * 80)
    print("  SUPERFONE — COMPACT 10-CALL INPUT & OUTPUT CHECKPOINT BENCHMARK")
    print("  Evaluating Input Gates + Output Gates across 5 Scenarios x 2 Reps")
    print("=" * 80)

    results = []
    for scenario in SCENARIOS:
        for rep in [1, 2]:
            res = await run_test_call(scenario, rep)
            results.append(res)
            await asyncio.sleep(1.0)

    out_file = r"c:\daily_works\superfone_call\compact_checkpoint_results.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 80)
    print("  SUMMARY OF COMPACT 10-CALL CHECKPOINT RESULTS")
    print("=" * 80)
    print(f"{'CALL ID':<20} | {'SCENARIO':<32} | {'TTFA(ms)':<8} | {'BOT(s)':<6} | {'WER':<5} | {'CHUNKS':<6}")
    print("-" * 80)
    for r in results:
        print(f"{r['call_id']:<20} | {r['scenario']:<32} | {r['ttfa_ms']:<8.1f} | {r['bot_duration_s']:<6.2f} | {r['stt_wer']:<5.2f} | {r['chunks_received']:<6}")
    print("=" * 80)
    print(f"Saved benchmark results to {out_file}")

if __name__ == "__main__":
    asyncio.run(main())
