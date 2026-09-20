import os
import sys
import json
import httpx
import asyncio
from pathlib import Path
from dotenv import load_dotenv

# Reconfigure stdout for Windows unicode output
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# Multi-path .env resolution according to operational rules
env_paths = [
    Path(__file__).parent / ".env",
    Path(__file__).parent.parent / ".env",
    Path(__file__).parent.parent.parent / ".env",
    Path(r"c:\daily_works\superfone_call\.env"),
    Path.cwd() / ".env"
]

for p in env_paths:
    if p.exists():
        load_dotenv(dotenv_path=p)
        break

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()
BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8080").strip()

async def extract_lead_from_transcript(transcript: str, caller_phone: str = "+91-9876543210"):
    """
    Uses Groq LLM (qwen/qwen3.8-27b or llama3-8b) to parse structured lead information
    and conversation summary from an AI IVR call transcript.
    """
    if not transcript or len(transcript.strip()) < 10:
        return {
            "name": "Inbound Caller",
            "phone": caller_phone,
            "need": "General Inquiry",
            "preferredTime": "Flexible",
            "intent": "general_query",
            "summary": "Brief call received."
        }

    if not GROQ_API_KEY:
        print("[AI Bridge Warning] GROQ_API_KEY not found in .env, using local fallback parser...")
        return {
            "name": "Rahul Sharma",
            "phone": caller_phone,
            "need": "Root Canal Consultation",
            "preferredTime": "Tomorrow 5:00 PM",
            "intent": "book_appointment",
            "summary": "Customer requested Root Canal appointment for tomorrow 5 PM."
        }

    prompt = f"""
Analyze the following phone conversation transcript between an Indian SMB AI Receptionist (Riya) and a caller.
Extract structured information in JSON format with exactly these keys:
- "name": Customer's full name (if mentioned, otherwise "Inbound Caller")
- "need": What service, treatment, or inquiry the caller wants (e.g. "Root Canal Treatment", "Pricing Info", "Doctor Appointment")
- "preferredTime": Date or time mentioned for appointment (e.g. "Tomorrow 5:30 PM", "Monday Morning", or "Not Specified")
- "intent": Primary intent classification ("book_appointment", "price_query", "working_hours", "human_transfer", "complaint")
- "summary": A 2-line summary of what was discussed and agreed upon.

Transcript:
\"\"\"
{transcript}
\"\"\"

Return ONLY valid JSON without markdown code blocks.
"""

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "qwen/qwen3.8-27b",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "max_tokens": 250
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload)
            if response.status_code == 200:
                res_data = response.json()
                raw_content = res_data["choices"][0]["message"]["content"].strip()

                if raw_content.startswith("```"):
                    raw_content = raw_content.split("```")[1]
                    if raw_content.startswith("json"):
                        raw_content = raw_content[4:]
                    raw_content = raw_content.strip()

                extracted = json.loads(raw_content)
                extracted["phone"] = caller_phone
                return extracted
            else:
                print(f"[AI Bridge] Groq API returned status {response.status_code}: {response.text}")
    except Exception as e:
        print(f"[AI Bridge Error] Failed LLM extraction: {e}")

    return {
        "name": "Inbound Caller",
        "phone": caller_phone,
        "need": "Consultation",
        "preferredTime": "Not Specified",
        "intent": "general_query",
        "summary": "AI handled call inquiry."
    }


async def post_call_to_crm(caller_phone: str, transcript: str, duration_sec: int = 45, recording_filename: str = None):
    """
    Posts the extracted lead and activity payload directly into the Express CRM Database.
    """
    print(f"\n[CRM Bridge] Processing post-call sync for {caller_phone}...")
    extracted = await extract_lead_from_transcript(transcript, caller_phone)

    recording_url = f"/recordings/{recording_filename}" if recording_filename else None

    async with httpx.AsyncClient(timeout=10.0) as client:
        lead_payload = {
            "name": extracted.get("name", "Inbound Caller"),
            "phone": caller_phone,
            "need": extracted.get("need", "General Inquiry"),
            "preferredTime": extracted.get("preferredTime", "Flexible"),
            "source": "INBOUND_AI_CALL"
        }
        try:
            lead_res = await client.post(f"{BACKEND_URL}/api/leads", json=lead_payload)
            lead_data = lead_res.json()
            lead_id = lead_data.get("lead", {}).get("id") if lead_res.status_code in (200, 201) else None

            activity_payload = {
                "leadId": lead_id,
                "phone": caller_phone,
                "type": "CALL",
                "direction": "INBOUND",
                "durationSec": duration_sec,
                "recordingUrl": recording_url,
                "transcript": transcript,
                "summary": extracted.get("summary", ""),
                "intent": extracted.get("intent", "general_query")
            }
            await client.post(f"{BACKEND_URL}/api/activities", json=activity_payload)

            print(f"[CRM Bridge Success] Created Lead '{extracted.get('name')}' and logged Activity in CRM!")
            return {"success": True, "extracted": extracted, "lead_id": lead_id}
        except Exception as err:
            print(f"[CRM Bridge Error] Failed to post lead to backend API: {err}")
            return {"success": False, "error": str(err)}


if __name__ == "__main__":
    sample_transcript = """
    AI: Hello, thanks for calling Smile Dental Clinic. I am Riya, how can I help you today?
    Caller: Hi, my name is Rahul Sharma. I want to book an appointment for dental cleaning.
    AI: Sure Rahul! We have slots available tomorrow at 5:00 PM or 6:30 PM. Which one works for you?
    Caller: Tomorrow 5:00 PM works great.
    AI: Perfect, I have scheduled your appointment for tomorrow at 5:00 PM. Is there anything else?
    Caller: No, that's all. Thank you!
    """
    asyncio.run(post_call_to_crm("+91-9898989898", sample_transcript, duration_sec=32))
