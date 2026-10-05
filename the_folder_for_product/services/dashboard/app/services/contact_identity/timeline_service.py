from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from services.dashboard.app.models.crm import (
    Contact, ContactPhone, ContactNote, CallSession, LeadReminder, WhatsAppMessage
)

def get_contact_timeline(db: Session, contact_id: str) -> Dict[str, Any]:
    """
    Unified Event Projection: Projects calls, recordings, transcripts, notes,
    reminders, and messaging into a single chronological timeline for Contact 360.
    """
    contact = db.query(Contact).filter(Contact.id == contact_id).first()
    if not contact:
        return {"error": "Contact not found", "timeline": []}

    # Collect phone numbers for call matching
    phone_numbers = {contact.phone_number}
    for p in contact.phones:
        phone_numbers.add(p.phone_e164)

    # 1. Fetch Calls
    calls = db.query(CallSession).filter(
        (CallSession.contact_id == contact.id) |
        (CallSession.from_number.in_(phone_numbers)) |
        (CallSession.to_number.in_(phone_numbers))
    ).order_by(CallSession.created_at.desc()).all()

    # 2. Fetch Notes
    notes = db.query(ContactNote).filter(
        ContactNote.contact_id == contact.id
    ).order_by(ContactNote.created_at.desc()).all()

    # 3. Fetch Reminders
    reminders = db.query(LeadReminder).filter(
        LeadReminder.contact_id == contact.id
    ).order_by(LeadReminder.created_at.desc()).all()

    events: List[Dict[str, Any]] = []

    # Project Calls into Timeline
    for c in calls:
        interaction = c.interactions[0] if (c.interactions and len(c.interactions) > 0) else None
        
        # Determine direction
        direction = "inbound"
        if c.from_number == contact.phone_number or any(c.from_number == p for p in phone_numbers):
            direction = "inbound"
        else:
            direction = "outbound"

        # Determine handler history
        handler_info = {
            "type": "ai",
            "name": "Riya AI",
            "transferred": False
        }
        if c.handled_by_user_id or (interaction and interaction.human_handoff_requested) or (c.handoff_status in ["HUMAN_CONNECTED", "AGENT_ACCEPTED"]):
            handler_info = {
                "type": "human_transfer",
                "name": "Transferred to Agent",
                "agent_id": c.handled_by_user_id,
                "reason": c.handoff_reason or "Customer requested human agent",
                "transferred": True
            }

        events.append({
            "id": f"call_{c.id}",
            "type": "call",
            "timestamp": c.created_at.isoformat() if c.created_at else None,
            "title": f"{'📞 Incoming Call' if direction == 'inbound' else '📱 Outbound Call'}",
            "direction": direction,
            "status": c.status or "completed",
            "duration_s": c.duration_s or 0,
            "recording_url": c.recording_url or f"/recordings/{c.id}.wav",
            "transcript": c.transcript or [],
            "ai_summary": interaction.ai_summary if interaction else None,
            "intent_detected": interaction.intent_detected if interaction else None,
            "sentiment": interaction.sentiment if interaction else "neutral",
            "handler": handler_info,
            "caller_number": c.from_number,
            "callee_number": c.to_number
        })

    # Project Notes into Timeline
    for n in notes:
        events.append({
            "id": f"note_{n.id}",
            "type": "note",
            "timestamp": n.created_at.isoformat() if n.created_at else None,
            "title": "📝 Agent Note",
            "content": n.note,
            "disposition": n.disposition,
            "sentiment": n.sentiment,
            "author": n.agent_name or "Agent",
            "agent_id": n.agent_id
        })

    # Project Reminders into Timeline
    for r in reminders:
        events.append({
            "id": f"reminder_{r.id}",
            "type": "reminder",
            "timestamp": r.created_at.isoformat() if r.created_at else None,
            "title": "⏰ Follow-up Reminder",
            "content": r.note,
            "remind_at": r.remind_at.isoformat() if r.remind_at else None,
            "is_triggered": r.is_triggered
        })

    # Sort all events chronologically descending (newest first)
    events.sort(key=lambda x: x["timestamp"] or "", reverse=True)

    # Derive AI Profile Summary from last call if not explicitly set
    ai_profile = contact.ai_profile or {}
    if not ai_profile.get("summary") and calls:
        for c in calls:
            if c.interactions and c.interactions[0].ai_summary:
                ai_profile = {
                    "summary": c.interactions[0].ai_summary,
                    "sentiment": c.interactions[0].sentiment or "neutral",
                    "intent_score": c.custom_fields.get("intent_score", 0.75) if contact.custom_fields else 0.75,
                    "open_issue": "General Inquiry",
                    "next_action": "Follow-up Call",
                    "generated_at": c.created_at.isoformat() if c.created_at else None,
                    "model": "qwen3.8-27b"
                }
                break

    return {
        "contact_id": contact.id,
        "name": contact.name or "Unnamed Lead",
        "phone_number": contact.phone_number,
        "company": contact.company,
        "status": contact.status,
        "tags": contact.tags or [],
        "ai_profile": ai_profile,
        "stats": {
            "total_calls": len(calls),
            "total_duration_s": sum(c.duration_s or 0 for c in calls),
            "total_notes": len(notes),
            "last_contacted_at": contact.last_called_at.isoformat() if contact.last_called_at else (calls[0].created_at.isoformat() if calls else None)
        },
        "timeline": events
    }
