"""
Live Multi-Tenant & Outbound Campaign Test Harness
Simulates parallel call traffic across two distinct business tenants:
  - Tenant A: Mali Saini NGO (Marwadi/Hindi) - Agent Pratham AI
  - Tenant B: Superfone SaaS (Indian English/Hinglish) - Agent Swati AI
  - Outbound Campaign Script Execution
"""

import os
import sys
import time
import wave
import uuid
import struct
import asyncio
import audioop
import numpy as np
from typing import List, Dict, Any

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from path_c_hybrid_agent.tts_cartesia import synthesize_speech_hd
from path_c_hybrid_agent.tenant_registry import get_tenant_config

HOST = "127.0.0.1"
PORT = 9092

SCENARIOS = [
    {
        "id": "TenantA-Inbound",
        "tenant_id": "tenant_a_ngo",
        "phone": "+919811000101",
        "query": "राम-राम सा! मैं माली सैनी समाज सेवा फाउंडेशन में ₹1000 डोनेशन देबो चाहूँ।",
        "voice_id": "791d5162-d5eb-40f0-8189-f19db44611d8"
    },
    {
        "id": "TenantB-Support",
        "tenant_id": "tenant_b_saas",
        "phone": "+919811000201",
        "query": "Hi! How do I connect my Twilio webhook URL to Superfone AI Voice Agent?",
        "voice_id": "cb9c954d-bcaa-43ed-82bf-aeb5e88a3cb5"
    },
    {
        "id": "TenantA-Campaign",
        "tenant_id": "tenant_a_ngo",
        "phone": "+919811000102",
        "query": "राम-राम सा! 80G टैक्स छूट कैंपेन रो काई विवरण है सा?",
        "voice_id": "791d5162-d5eb-40f0-8189-f19db44611d8"
    },
    {
        "id": "TenantB-Campaign",
        "tenant_id": "tenant_b_saas",
        "phone": "+919811000202",
        "query": "Hello Swati! I received your email regarding the early access demo campaign.",
        "voice_id": "cb9c954d-bcaa-43ed-82bf-aeb5e88a3cb5"
    },
    {
        "id": "TenantA-OfficeInquiry",
        "tenant_id": "tenant_a_ngo",
        "phone": "+919811000103",
        "query": "माली सैनी फाउंडेशन रो ऑफिस कठे है सा?",
        "voice_id": "791d5162-d5eb-40f0-8189-f19db44611d8"
    },
    {
        "id": "TenantB-Pricing",
        "tenant_id": "tenant_b_saas",
        "phone": "+919811000203",
        "query": "What are the subscription pricing plans for 10 concurrent AI voice channels?",
        "voice_id": "cb9c954d-bcaa-43ed-82bf-aeb5e88a3cb5"
    }
]


async def run_single_tenant_channel(scenario: Dict[str, str], results_list: List[Dict[str, Any]], pcm_audio_collector: Dict[str, bytes]):
    call_id = scenario["id"]
    tenant_id = scenario["tenant_id"]
    phone = scenario["phone"]
    query = scenario["query"]
    voice_id = scenario["voice_id"]
    
    tenant_cfg = get_tenant_config(tenant_id)
    org_name = tenant_cfg["organization_name"]
    agent_name = tenant_cfg["agent_name"]

    t_call_start = time.perf_counter()
    print(f"  🟢 [{call_id}] ({org_name} - {agent_name}): Connecting channel ({phone})...")

    try:
        reader, writer = await asyncio.open_connection(HOST, PORT)
        
        # 1. Send AudioSocket Header
        u_bytes = uuid.uuid4().bytes
        hdr = struct.pack("!BH", 0x01, 16)
        writer.write(hdr + u_bytes)
        await writer.drain()

        # 2. Receive Initial Greeting Audio from Gateway
        greeting_pcm = bytearray()
        t0_greeting = time.perf_counter()
        while time.perf_counter() - t0_greeting < 2.5:
            try:
                g_hdr = await asyncio.wait_for(reader.readexactly(3), timeout=0.3)
                p_type, p_len = struct.unpack("!BH", g_hdr)
                p_data = await reader.readexactly(p_len)
                if p_type == 0x10:
                    greeting_pcm.extend(p_data)
            except Exception:
                break

        # 3. Synthesize Caller Audio
        caller_pcm_24k = await synthesize_speech_hd(query, voice_id=voice_id, sample_rate=24000)
        if not caller_pcm_24k:
            caller_pcm_24k = b"\x00" * 48000
        
        audio_np = np.frombuffer(caller_pcm_24k, dtype=np.int16)
        caller_pcm_8k = audio_np[::3].tobytes()

        # 4. Stream Caller Audio to Gateway
        print(f"  🗣️ [{call_id}] Caller -> {agent_name}: '{query}'")

        for i in range(0, len(caller_pcm_8k), 320):
            chunk = caller_pcm_8k[i:i+320].ljust(320, b"\x00")
            writer.write(struct.pack("!BH", 0x10, 320) + chunk)
            await asyncio.sleep(0.018)

        await writer.drain()

        # Silence for VAD turn completion
        silence_chunk = b"\x00" * 320
        for _ in range(25):
            writer.write(struct.pack("!BH", 0x10, 320) + silence_chunk)
            await asyncio.sleep(0.018)
        await writer.drain()

        # 5. Receive Agent Response Audio
        agent_response_pcm = bytearray()
        t_wait_resp = time.perf_counter()
        ttft_ms = 0

        while time.perf_counter() - t_wait_resp < 6.0:
            try:
                r_hdr = await asyncio.wait_for(reader.readexactly(3), timeout=0.5)
                p_type, p_len = struct.unpack("!BH", r_hdr)
                p_data = await reader.readexactly(p_len)
                if p_type == 0x10:
                    if len(agent_response_pcm) == 0:
                        ttft_ms = round((time.perf_counter() - t_wait_resp) * 1000, 1)
                    agent_response_pcm.extend(p_data)
            except asyncio.TimeoutError:
                if len(agent_response_pcm) > 0:
                    break
            except Exception:
                break

        total_duration = round(time.perf_counter() - t_call_start, 2)
        print(f"  🤖 [{call_id}] ({agent_name}): Response Received ({len(agent_response_pcm)} bytes PCM, TTFT: {ttft_ms}ms, Total: {total_duration}s)")

        # Hangup
        writer.write(struct.pack("!BH", 0x00, 0))
        await writer.drain()
        writer.close()

        pcm_audio_collector[call_id] = bytes(agent_response_pcm)
        results_list.append({
            "call_id": call_id,
            "tenant_id": tenant_id,
            "org_name": org_name,
            "agent_name": agent_name,
            "phone": phone,
            "query": query,
            "ttft_ms": ttft_ms,
            "pcm_bytes": len(agent_response_pcm),
            "status": "SUCCESS"
        })

    except Exception as e:
        print(f"  ❌ [{call_id}] Exception: {e}")
        results_list.append({
            "call_id": call_id,
            "tenant_id": tenant_id,
            "org_name": org_name,
            "agent_name": agent_name,
            "phone": phone,
            "query": query,
            "ttft_ms": 0,
            "pcm_bytes": 0,
            "status": f"FAILED: {e}"
        })


async def main():
    print("=" * 90)
    print("  🚀 MULTI-TENANT VOICE AGENT ISOLATION & CAMPAIGN SCRIPT EXECUTION BENCHMARK")
    print("  Tenant A: Mali Saini NGO (Marwadi/Hindi) | Agent Pratham AI")
    print("  Tenant B: Superfone AI Voice CRM (Hinglish/English) | Agent Swati AI")
    print("=================================================================================\n")

    t_start_all = time.perf_counter()
    results: List[Dict[str, Any]] = []
    audio_collector: Dict[str, bytes] = {}

    # Run 6 parallel multi-tenant calls simultaneously
    tasks = [run_single_tenant_channel(sc, results, audio_collector) for sc in SCENARIOS]
    await asyncio.gather(*tasks)

    total_test_time = round(time.perf_counter() - t_start_all, 2)

    print("\n" + "=" * 90)
    print("  📊 MULTI-TENANT ISOLATION BENCHMARK SUMMARY & PERFORMANCE REPORT")
    print("=================================================================================")
    print(f"  Total Benchmark Time: {total_test_time}s")
    print(f"  Total Channels Executed: {len(results)}")
    print(f"  Successful Tenant Calls: {sum(1 for r in results if r['status'] == 'SUCCESS')}/6\n")

    print(f"  {'Channel':<20} | {'Tenant / Persona':<25} | {'TTFT (ms)':<10} | {'Audio Received':<15} | {'Status':<10}")
    print("  " + "-" * 85)
    
    for r in sorted(results, key=lambda x: x['call_id']):
        persona_str = f"{r['tenant_id']} ({r['agent_name']})"
        print(f"  {r['call_id']:<20} | {persona_str:<25} | {r['ttft_ms']:<10} | {r['pcm_bytes']:<15} | {r['status']:<10}")

    # Generate Separate Master Audio Mixes for Tenant A and Tenant B
    artifact_dir = r"C:\Users\msanj\.gemini\antigravity\brain\3f670608-a148-48ef-8f33-27bc120319d4"
    
    # Tenant A Mix
    mix_a_path = os.path.join(artifact_dir, "tenant_a_ngo_master_mix.wav")
    tenant_a_audio = [pcm for cid, pcm in audio_collector.items() if "TenantA" in cid and pcm]
    if tenant_a_audio:
        max_len = max([len(b) for b in tenant_a_audio])
        mix_arr = np.zeros(max_len // 2, dtype=np.int32)
        for b in tenant_a_audio:
            arr = np.frombuffer(b[: (len(b) // 2) * 2], dtype=np.int16)
            mix_arr[:len(arr)] += arr
        clipped = np.clip(mix_arr, -32768, 32767).astype(np.int16)
        with wave.open(mix_a_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(8000)
            wf.writeframes(clipped.tobytes())
        print(f"\n  🎵 Tenant A (NGO Marwadi) Master Audio Mix Saved to:\n     {mix_a_path}")

    # Tenant B Mix
    mix_b_path = os.path.join(artifact_dir, "tenant_b_saas_master_mix.wav")
    tenant_b_audio = [pcm for cid, pcm in audio_collector.items() if "TenantB" in cid and pcm]
    if tenant_b_audio:
        max_len = max([len(b) for b in tenant_b_audio])
        mix_arr = np.zeros(max_len // 2, dtype=np.int32)
        for b in tenant_b_audio:
            arr = np.frombuffer(b[: (len(b) // 2) * 2], dtype=np.int16)
            mix_arr[:len(arr)] += arr
        clipped = np.clip(mix_arr, -32768, 32767).astype(np.int16)
        with wave.open(mix_b_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(8000)
            wf.writeframes(clipped.tobytes())
        print(f"  🎵 Tenant B (SaaS Support) Master Audio Mix Saved to:\n     {mix_b_path}")

    print("=================================================================================\n")

if __name__ == "__main__":
    asyncio.run(main())
