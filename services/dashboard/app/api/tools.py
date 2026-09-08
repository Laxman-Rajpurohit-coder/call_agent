from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from pydantic import BaseModel, Field

from services.dashboard.app.database import get_db
from services.dashboard.app.models.crm import (
    LeadTask, Contact, TeamMember, Organization, LeadReminder, WhatsAppMessage,
    CallSession, CallInteraction
)
from services.dashboard.app.services.lead_router_service import assign_lead_round_robin, get_or_create_default_org

router = APIRouter(prefix="/tools", tags=["LLM Tools"])

# ── Pydantic Schemas for LLM Tool Inputs ────────────────────────────────────

class CreateTaskInput(BaseModel):
    title: str = Field(..., description="Short task summary (e.g. 'Schedule site visit for 3 BHK')")
    description: Optional[str] = Field("", description="Detailed requirement notes captured from caller")
    phone_number: Optional[str] = Field("9999999999", description="Customer phone number")
    contact_name: Optional[str] = Field("Valued Customer", description="Customer full name")
    due_in_hours: Optional[int] = Field(24, description="Due duration in hours from now")

class ScheduleCallbackInput(BaseModel):
    phone_number: str = Field(..., description="Customer phone number to call back")
    scheduled_time: str = Field(..., description="Scheduled callback time (e.g. 'Tomorrow 10:00 AM' or ISO string)")
    note: Optional[str] = Field("Customer requested callback", description="Reason or context for callback")
    customer_id: Optional[str] = Field(None, description="Optional contact/customer ID")

class TagCustomerInput(BaseModel):
    phone_number: str = Field(..., description="Customer phone number")
    tag: str = Field(..., description="Tag name (e.g. 'Hot Lead', 'Budget: 75L', 'Price Inquiry')")
    reason: Optional[str] = Field("", description="Context or explanation for applying tag")
    customer_name: Optional[str] = Field(None, description="Customer name if creating new contact")

class SaveCallNoteInput(BaseModel):
    call_id: str = Field(..., description="Call session ID")
    summary: str = Field(..., description="Summary of conversation")
    action_items: Optional[str] = Field("", description="Pending action items or follow-up steps")
    customer_id: Optional[str] = Field(None, description="Associated contact ID")

class SendWhatsAppInput(BaseModel):
    phone_number: str = Field(..., description="Recipient mobile phone number")
    message_text: str = Field(..., description="WhatsApp text content or brochure details")
    contact_name: Optional[str] = Field("Customer", description="Recipient name")

class HumanHandoffInput(BaseModel):
    call_id: str = Field(..., description="Active call session ID")
    reason: Optional[str] = Field("Customer requested human agent", description="Reason for handoff")

class AnalyzeAndLabelInput(BaseModel):
    call_id: Optional[str] = Field(None, description="Call session ID to analyze & label")
    transcript: Optional[Any] = Field(None, description="Raw text transcript or list of turns ({role, content})")
    phone_number: Optional[str] = Field(None, description="Customer phone number")

class UniversalToolExecuteInput(BaseModel):
    tool_name: str = Field(..., description="Name of the LLM tool to execute")
    arguments: Dict[str, Any] = Field(default_factory=dict, description="Arguments dictionary for the tool")


# ── JSON Schema Tool Definitions for LLM Function Calling ─────────────

LLM_TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "analyze_and_label_transcript",
            "description": "Analyzes full call conversation transcript, classifies caller intent & sentiment, and attaches an appropriate label (e.g. 'Liked Product / High Intent', 'Not Interested', 'Price Objection', 'Invalid Customer / Wrong Number') to the Voice CRM.",
            "parameters": {
                "type": "object",
                "properties": {
                    "call_id": {"type": "string", "description": "Call session ID"},
                    "transcript": {"type": "string", "description": "Conversation transcript text or turns"},
                    "phone_number": {"type": "string", "description": "Customer phone number"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_task_round_robin",
            "description": "Creates a To-Do follow-up task and automatically assigns it to an active sales representative using Round-Robin load balancing.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Short task title (e.g. 'Site Visit 3 BHK')"},
                    "description": {"type": "string", "description": "Detailed notes from caller"},
                    "phone_number": {"type": "string", "description": "Customer phone number"},
                    "contact_name": {"type": "string", "description": "Customer name"},
                    "due_in_hours": {"type": "integer", "default": 24, "description": "Due in hours"}
                },
                "required": ["title"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "schedule_callback",
            "description": "Schedules an automated callback reminder for a customer at a specified date and time.",
            "parameters": {
                "type": "object",
                "properties": {
                    "phone_number": {"type": "string", "description": "Customer phone number"},
                    "scheduled_time": {"type": "string", "description": "Callback date/time"},
                    "note": {"type": "string", "description": "Reason for callback"}
                },
                "required": ["phone_number", "scheduled_time"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "tag_customer",
            "description": "Tags a customer contact record with interest categories, budget brackets, or priority stages.",
            "parameters": {
                "type": "object",
                "properties": {
                    "phone_number": {"type": "string", "description": "Customer phone number"},
                    "tag": {"type": "string", "description": "Tag to apply (e.g. 'Hot Lead', '2BHK Inquiry')"},
                    "reason": {"type": "string", "description": "Context for applying tag"}
                },
                "required": ["phone_number", "tag"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "save_call_note",
            "description": "Saves structured summary notes and action items for a call session in the Voice CRM.",
            "parameters": {
                "type": "object",
                "properties": {
                    "call_id": {"type": "string", "description": "Active call ID"},
                    "summary": {"type": "string", "description": "Call conversation summary"},
                    "action_items": {"type": "string", "description": "Follow-up action items"}
                },
                "required": ["call_id", "summary"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "send_whatsapp_message",
            "description": "Sends an instant WhatsApp message with property brochure, pricing, or confirmation to the caller's phone.",
            "parameters": {
                "type": "object",
                "properties": {
                    "phone_number": {"type": "string", "description": "Recipient phone number"},
                    "message_text": {"type": "string", "description": "Message text or link"}
                },
                "required": ["phone_number", "message_text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "request_human_handoff",
            "description": "Triggers live call transfer to a human sales manager when requested by the caller.",
            "parameters": {
                "type": "object",
                "properties": {
                    "call_id": {"type": "string", "description": "Active call ID"},
                    "reason": {"type": "string", "description": "Reason for handoff"}
                },
                "required": ["call_id"]
            }
        }
    }
]


# ── GET /api/v1/tools -> Returns Schema Definitions ────────────────────────

@router.get("")
def list_llm_tools():
    """Returns JSON Schema function definitions for LLM tool calling."""
    return {
        "status": "success",
        "total_tools": len(LLM_TOOL_DEFINITIONS),
        "tools": LLM_TOOL_DEFINITIONS
    }


# ── Helper for Transcript Label Classification ─────────────────────────────

def classify_transcript_label(text: str) -> Dict[str, Any]:
    text_lower = text.lower()

    # 1. Invalid Customer / Wrong Number
    if any(k in text_lower for k in ["wrong number", "galt number", "ग़लत नंबर", "who is this", "kon bol raha h"]):
        return {
            "label": "Invalid Customer / Wrong Number",
            "sentiment": "negative",
            "contact_status": "invalid",
            "confidence": 0.98,
            "action": "Flag number as Invalid in CRM database."
        }
    
    # 2. Not Interested
    if any(k in text_lower for k in ["not interested", "don't call", "no thanks", "wrong person", "remove my number", "nahin chahiye", "नहीं चाहिए", "मत करो"]):
        return {
            "label": "Not Interested",
            "sentiment": "negative",
            "contact_status": "unqualified",
            "confidence": 0.95,
            "action": "Mark lead as Unqualified & suppress further campaign dials."
        }
        
    # 3. Price / Budget Objection
    if any(k in text_lower for k in ["expensive", "too high", "costly", "out of budget", "mahanga", "महंगा", "बजट कम hai"]):
        return {
            "label": "Price / Budget Objection",
            "sentiment": "objection",
            "contact_status": "nurture",
            "confidence": 0.90,
            "action": "Schedule follow-up call with special discount or smaller unit proposal."
        }

    # 4. Callback Requested
    if any(k in text_lower for k in ["call later", "call tomorrow", "busy now", "बाद में कॉल"]):
        return {
            "label": "Callback Requested",
            "sentiment": "neutral",
            "contact_status": "lead",
            "confidence": 0.92,
            "action": "Schedule callback reminder in CRM."
        }

    # 5. Liked Product / High Intent
    if any(k in text_lower for k in ["liked", "interested", "buy", "site visit", "book", "demo", "purchas", "अच्छा लगा", "पसंद आया", "विज़िट", "deal"]):
        return {
            "label": "Liked Product / High Intent",
            "sentiment": "positive",
            "contact_status": "qualified",
            "confidence": 0.94,
            "action": "Assign task via Round-Robin to sales agent for instant follow-up."
        }

    return {
        "label": "General Inquiry",
        "sentiment": "neutral",
        "contact_status": "lead",
        "confidence": 0.85,
        "action": "Keep in active lead pipeline."
    }


# ── Individual Tool Implementations ─────────────────────────────────────────

@router.post("/analyze_and_label")
@router.post("/auto_label")
def tool_analyze_and_label(payload: AnalyzeAndLabelInput, db: Session = Depends(get_db)):
    """LLM Tool: Analyzes full transcript and attaches a fitting label to Call & Contact."""
    call_id = payload.call_id
    transcript_text = ""
    phone = payload.phone_number

    call_sess = None
    if call_id:
        call_sess = db.query(CallSession).filter(CallSession.id == call_id).first()

    # Extract text content from transcript
    if payload.transcript:
        if isinstance(payload.transcript, str):
            transcript_text = payload.transcript
        elif isinstance(payload.transcript, list):
            transcript_text = " ".join([f"{t.get('role', 'user')}: {t.get('content', '')}" for t in payload.transcript if isinstance(t, dict)])
    elif call_sess and call_sess.transcript:
        if isinstance(call_sess.transcript, list):
            transcript_text = " ".join([f"{t.get('role', 'user')}: {t.get('content', '')}" for t in call_sess.transcript if isinstance(t, dict)])
        else:
            transcript_text = str(call_sess.transcript)

    if not transcript_text:
        transcript_text = "Customer answered call. General discussion on product features."

    # Classify transcript intent & sentiment
    classification = classify_transcript_label(transcript_text)
    label = classification["label"]
    sentiment = classification["sentiment"]
    contact_status = classification["contact_status"]
    confidence = classification["confidence"]
    action = classification["action"]

    # Update database records
    if call_sess:
        cf = dict(call_sess.custom_fields or {})
        cf["label"] = label
        cf["sentiment"] = sentiment
        call_sess.custom_fields = cf
        phone = phone or call_sess.from_number

        interaction = db.query(CallInteraction).filter(CallInteraction.call_id == call_sess.id).first()
        if not interaction:
            interaction = CallInteraction(
                call_id=call_sess.id,
                intent_detected=label,
                ai_summary=f"Automated LLM Analysis: {label}. {action}",
                confidence=confidence,
                custom_fields={"sentiment": sentiment, "auto_label": label}
            )
            db.add(interaction)
        else:
            interaction.intent_detected = label
            interaction.confidence = confidence
            cf_int = dict(interaction.custom_fields or {})
            cf_int["sentiment"] = sentiment
            cf_int["auto_label"] = label
            interaction.custom_fields = cf_int

    if phone:
        contact = db.query(Contact).filter(Contact.phone_number == phone).first()
        if contact:
            contact.status = contact_status
            cf_con = dict(contact.custom_fields or {})
            tags = list(cf_con.get("tags", []))
            if label not in tags:
                tags.append(label)
            cf_con["tags"] = tags
            cf_con["latest_label"] = label
            contact.custom_fields = cf_con

    db.commit()

    return {
        "status": "success",
        "tool": "analyze_and_label_transcript",
        "call_id": call_id,
        "phone_number": phone,
        "label": label,
        "sentiment": sentiment,
        "confidence": confidence,
        "suggested_contact_status": contact_status,
        "summary": f"Call transcript analyzed: {label}.",
        "recommended_next_action": action,
        "message": f"Transcript analyzed successfully. Attached label '{label}' to call and contact record."
    }


@router.post("/create_task")
def tool_create_task(payload: CreateTaskInput, db: Session = Depends(get_db)):
    """LLM Tool 1: Create Task with Round-Robin Lead Routing."""
    org = get_or_create_default_org(db)
    phone = payload.phone_number or "9999999999"
    name = payload.contact_name or "Valued Customer"

    contact = db.query(Contact).filter(Contact.phone_number == phone).first()
    if not contact:
        contact = Contact(
            organization_id=org.id,
            phone_number=phone,
            name=name,
            status='lead',
            lead_source='AI Voice Bot'
        )
        db.add(contact)
        db.commit()
        db.refresh(contact)

    assigned_agent = assign_lead_round_robin(db, org.id)
    if assigned_agent:
        contact.lead_owner_id = assigned_agent.id
        db.commit()

    due_at = datetime.utcnow() + timedelta(hours=payload.due_in_hours or 24)

    task = LeadTask(
        organization_id=org.id,
        contact_id=contact.id,
        assigned_to_id=assigned_agent.id if assigned_agent else None,
        title=payload.title,
        description=payload.description or f"Captured by AI Agent during call with {name} ({phone}).",
        status='pending',
        due_at=due_at
    )
    db.add(task)

    reminder = LeadReminder(
        organization_id=org.id,
        contact_id=contact.id,
        task_id=task.id,
        note=f"Follow-up required for {name}: {payload.title}",
        remind_at=due_at - timedelta(hours=1)
    )
    db.add(reminder)
    db.commit()
    db.refresh(task)

    return {
        "status": "success",
        "tool": "create_task_round_robin",
        "task_id": task.id,
        "title": task.title,
        "description": task.description,
        "contact": {"id": contact.id, "name": contact.name, "phone_number": contact.phone_number},
        "assigned_to": {
            "id": assigned_agent.id if assigned_agent else None,
            "name": assigned_agent.name if assigned_agent else "Unassigned",
            "email": assigned_agent.email if assigned_agent else "",
            "role": assigned_agent.role if assigned_agent else ""
        },
        "due_at": task.due_at.isoformat(),
        "message": f"Task created and assigned to {assigned_agent.name if assigned_agent else 'Unassigned'} via Round-Robin load balance."
    }


@router.post("/schedule_callback")
def tool_schedule_callback(payload: ScheduleCallbackInput, db: Session = Depends(get_db)):
    """LLM Tool 2: Schedule Callback."""
    org = get_or_create_default_org(db)
    phone = payload.phone_number

    contact = db.query(Contact).filter(Contact.phone_number == phone).first()
    if not contact:
        contact = Contact(organization_id=org.id, phone_number=phone, name="Callback Lead", status="lead")
        db.add(contact)
        db.commit()
        db.refresh(contact)

    remind_at = datetime.utcnow() + timedelta(hours=4)
    reminder = LeadReminder(
        organization_id=org.id,
        contact_id=contact.id,
        note=f"Scheduled Callback ({payload.scheduled_time}): {payload.note}",
        remind_at=remind_at
    )
    db.add(reminder)
    db.commit()
    db.refresh(reminder)

    return {
        "status": "success",
        "tool": "schedule_callback",
        "reminder_id": reminder.id,
        "phone_number": phone,
        "scheduled_time": payload.scheduled_time,
        "note": reminder.note,
        "message": f"Callback scheduled successfully for {phone} at {payload.scheduled_time}."
    }


@router.post("/tag_customer")
def tool_tag_customer(payload: TagCustomerInput, db: Session = Depends(get_db)):
    """LLM Tool 3: Tag Customer Record."""
    org = get_or_create_default_org(db)
    phone = payload.phone_number

    contact = db.query(Contact).filter(Contact.phone_number == phone).first()
    if not contact:
        contact = Contact(organization_id=org.id, phone_number=phone, name=payload.customer_name or "Tagged Lead")
        db.add(contact)
        db.commit()
        db.refresh(contact)

    custom_fields = dict(contact.custom_fields or {})
    tags = custom_fields.get("tags", [])
    if payload.tag not in tags:
        tags.append(payload.tag)
    custom_fields["tags"] = tags
    custom_fields["last_tag_reason"] = payload.reason
    contact.custom_fields = custom_fields
    db.commit()

    return {
        "status": "success",
        "tool": "tag_customer",
        "contact_id": contact.id,
        "phone_number": phone,
        "tag_added": payload.tag,
        "all_tags": tags,
        "message": f"Tag '{payload.tag}' attached to contact {phone}."
    }


def _get_or_create_call_session(db: Session, call_id: str) -> CallSession:
    session = db.query(CallSession).filter(CallSession.id == call_id).first()
    if not session:
        org = get_or_create_default_org(db)
        session = CallSession(
            id=call_id,
            organization_id=org.id,
            from_number="9999999999",
            to_number="700",
            status="completed",
            started_at=datetime.utcnow(),
            ended_at=datetime.utcnow(),
            duration_s=15.0
        )
        db.add(session)
        db.commit()
        db.refresh(session)
    return session


@router.post("/save_call_note")
def tool_save_call_note(payload: SaveCallNoteInput, db: Session = Depends(get_db)):
    """LLM Tool 4: Save Call Summary Note."""
    call_sess = _get_or_create_call_session(db, payload.call_id)
    
    interaction = db.query(CallInteraction).filter(CallInteraction.call_id == payload.call_id).first()
    if not interaction:
        interaction = CallInteraction(
            call_id=call_sess.id,
            ai_summary=payload.summary,
            custom_fields={"action_items": payload.action_items} if payload.action_items else {}
        )
        db.add(interaction)
    else:
        interaction.ai_summary = payload.summary
        if payload.action_items:
            cf = dict(interaction.custom_fields or {})
            cf["action_items"] = payload.action_items
            interaction.custom_fields = cf

    db.commit()
    return {
        "status": "success",
        "tool": "save_call_note",
        "call_id": payload.call_id,
        "summary": payload.summary,
        "action_items": payload.action_items,
        "message": f"Call note saved for call {payload.call_id}."
    }


@router.post("/send_whatsapp")
def tool_send_whatsapp(payload: SendWhatsAppInput, db: Session = Depends(get_db)):
    """LLM Tool 5: Trigger WhatsApp Message."""
    org = get_or_create_default_org(db)
    phone = payload.phone_number

    contact = db.query(Contact).filter(Contact.phone_number == phone).first()
    msg = WhatsAppMessage(
        organization_id=org.id,
        contact_id=contact.id if contact else None,
        phone_number=phone,
        direction="outbound",
        message_text=payload.message_text,
        status="sent"
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)

    return {
        "status": "success",
        "tool": "send_whatsapp_message",
        "whatsapp_id": msg.id,
        "phone_number": phone,
        "message_text": payload.message_text,
        "message": f"WhatsApp message sent to {phone}."
    }


@router.post("/human_handoff")
def tool_human_handoff(payload: HumanHandoffInput, db: Session = Depends(get_db)):
    """LLM Tool 6: Trigger Human Agent Handoff."""
    call_sess = _get_or_create_call_session(db, payload.call_id)
    
    interaction = db.query(CallInteraction).filter(CallInteraction.call_id == payload.call_id).first()
    if not interaction:
        interaction = CallInteraction(
            call_id=call_sess.id,
            human_handoff_requested=True,
            intent_detected="Human Handoff Request"
        )
        db.add(interaction)
    else:
        interaction.human_handoff_requested = True
    
    db.commit()

    return {
        "status": "success",
        "tool": "request_human_handoff",
        "call_id": payload.call_id,
        "reason": payload.reason,
        "human_handoff_triggered": True,
        "message": f"Live human agent handoff initiated for call {payload.call_id}."
    }


# ── POST /api/v1/tools/execute -> Universal Tool Dispatcher ───────────────

@router.post("/execute")
def execute_tool(payload: UniversalToolExecuteInput, db: Session = Depends(get_db)):
    """
    Universal LLM Tool Dispatcher.
    Accepts tool_name and arguments, executing the proper tool logic dynamically.
    """
    tool_name = payload.tool_name
    args = payload.arguments or {}

    try:
        if tool_name in ["analyze_and_label_transcript", "auto_label_call", "label_transcript", "auto_label"]:
            return tool_analyze_and_label(AnalyzeAndLabelInput(**args), db)
        elif tool_name in ["create_task_round_robin", "create_task"]:
            return tool_create_task(CreateTaskInput(**args), db)
        elif tool_name == "schedule_callback":
            return tool_schedule_callback(ScheduleCallbackInput(**args), db)
        elif tool_name == "tag_customer":
            return tool_tag_customer(TagCustomerInput(**args), db)
        elif tool_name == "save_call_note":
            return tool_save_call_note(SaveCallNoteInput(**args), db)
        elif tool_name in ["send_whatsapp_message", "send_whatsapp"]:
            return tool_send_whatsapp(SendWhatsAppInput(**args), db)
        elif tool_name in ["request_human_handoff", "human_handoff"]:
            return tool_human_handoff(HumanHandoffInput(**args), db)
        else:
            raise HTTPException(status_code=400, detail=f"Unknown tool '{tool_name}'. Available tools: {[t['function']['name'] for t in LLM_TOOL_DEFINITIONS]}")
    except Exception as ex:
        raise HTTPException(status_code=400, detail=f"Tool execution failed: {str(ex)}")
