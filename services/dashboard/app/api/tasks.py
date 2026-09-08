from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from pydantic import BaseModel

from services.dashboard.app.database import get_db
from services.dashboard.app.models.crm import LeadTask, Contact, TeamMember, Organization, LeadReminder
from services.dashboard.app.schemas.task_schemas import TaskCreate, TaskUpdate
from services.dashboard.app.services.lead_router_service import assign_lead_round_robin, get_or_create_default_org

router = APIRouter()

class LLMTaskToolInput(BaseModel):
    title: str
    description: Optional[str] = ""
    phone_number: Optional[str] = "9999999999"
    contact_name: Optional[str] = "Valued Customer"
    due_in_hours: Optional[int] = 24


@router.get("")
def list_tasks(db: Session = Depends(get_db)):
    tasks = db.query(LeadTask).order_by(LeadTask.created_at.desc()).all()
    results = []
    for t in tasks:
        contact = db.query(Contact).filter(Contact.id == t.contact_id).first() if t.contact_id else None
        agent = db.query(TeamMember).filter(TeamMember.id == t.assigned_to_id).first() if t.assigned_to_id else None
        results.append({
            'id': t.id,
            'title': t.title,
            'description': t.description,
            'status': t.status,
            'due_at': t.due_at,
            'created_at': t.created_at,
            'contact_id': t.contact_id,
            'contact_name': contact.name if contact else 'Lead',
            'contact_phone': contact.phone_number if contact else '',
            'lead_source': contact.lead_source if contact else 'Direct',
            'assigned_to_id': t.assigned_to_id,
            'assigned_to_name': agent.name if agent else 'Unassigned',
            'assigned_to_email': agent.email if agent else '',
            'custom_inquiry_data': t.custom_inquiry_data or (contact.custom_fields if contact else {})
        })
    return results


@router.post("")
def create_task(task_in: TaskCreate, db: Session = Depends(get_db)):
    org = get_or_create_default_org(db)
    
    # Round-Robin Auto Assignment if assigned_to_id is not provided or set to 'auto'/'round_robin'
    assigned_agent = None
    assigned_to_id = task_in.assigned_to_id
    
    if not assigned_to_id or assigned_to_id in ["auto", "round_robin", "unassigned", ""]:
        assigned_agent = assign_lead_round_robin(db, org.id)
        assigned_to_id = assigned_agent.id if assigned_agent else None
    else:
        assigned_agent = db.query(TeamMember).filter(TeamMember.id == assigned_to_id).first()
        if assigned_agent:
            assigned_agent.assigned_leads_count += 1
            db.commit()

    t = LeadTask(
        organization_id=org.id,
        contact_id=task_in.contact_id,
        assigned_to_id=assigned_to_id,
        title=task_in.title,
        description=task_in.description or "",
        due_at=task_in.due_at or (datetime.utcnow() + timedelta(hours=24)),
        custom_inquiry_data=task_in.custom_inquiry_data or {}
    )
    db.add(t)
    db.commit()
    db.refresh(t)

    # Automatically set a reminder for the assigned agent
    reminder = LeadReminder(
        organization_id=org.id,
        contact_id=task_in.contact_id,
        task_id=t.id,
        note=f"Task Reminder: {t.title}",
        remind_at=t.due_at - timedelta(hours=1) if t.due_at else datetime.utcnow() + timedelta(minutes=15)
    )
    db.add(reminder)
    db.commit()

    return {
        'id': t.id,
        'status': t.status,
        'title': t.title,
        'assigned_to_id': assigned_to_id,
        'assigned_to_name': assigned_agent.name if assigned_agent else 'Unassigned',
        'assigned_to_email': assigned_agent.email if assigned_agent else '',
        'due_at': t.due_at
    }


@router.post("/llm-create-task")
@router.post("/tools/create_task")
def llm_create_task_tool(payload: LLMTaskToolInput, db: Session = Depends(get_db)):
    """
    LLM Function Tool for Round-Robin Task Creation.
    Exposed for AI Agents to automatically create & assign tasks during calls.
    """
    org = get_or_create_default_org(db)
    
    # 1. Lookup or create contact
    phone = payload.phone_number or "9999999999"
    name = payload.contact_name or "Valued Customer"
    
    contact = db.query(Contact).filter(Contact.phone_number == phone).first()
    if not contact:
        contact = Contact(
            organization_id=org.id,
            phone_number=phone,
            name=name,
            status='lead',
            lead_source='AI Call Assistant'
        )
        db.add(contact)
        db.commit()
        db.refresh(contact)

    # 2. Round-Robin Load Balance Assignment
    assigned_agent = assign_lead_round_robin(db, org.id)
    if assigned_agent:
        contact.lead_owner_id = assigned_agent.id
        db.commit()

    due_at = datetime.utcnow() + timedelta(hours=payload.due_in_hours or 24)

    # 3. Create LeadTask
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

    # 4. Create LeadReminder
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
        "contact": {
            "id": contact.id,
            "name": contact.name,
            "phone_number": contact.phone_number
        },
        "assigned_to": {
            "id": assigned_agent.id if assigned_agent else None,
            "name": assigned_agent.name if assigned_agent else "Unassigned",
            "email": assigned_agent.email if assigned_agent else "",
            "role": assigned_agent.role if assigned_agent else "",
            "total_assigned_leads": assigned_agent.assigned_leads_count if assigned_agent else 0
        },
        "due_at": task.due_at.isoformat(),
        "message": f"Task successfully created and assigned to {assigned_agent.name if assigned_agent else 'Unassigned'} via Round-Robin load balancing."
    }


@router.patch("/{task_id}")
def update_task(task_id: str, upd: TaskUpdate, db: Session = Depends(get_db)):
    t = db.query(LeadTask).filter(LeadTask.id == task_id).first()
    if not t: 
        raise HTTPException(status_code=404, detail='Task not found')
    if upd.status: t.status = upd.status
    if upd.title: t.title = upd.title
    if upd.description: t.description = upd.description
    if upd.assigned_to_id: t.assigned_to_id = upd.assigned_to_id
    if upd.due_at: t.due_at = upd.due_at
    db.commit()
    db.refresh(t)
    return {'id': t.id, 'status': t.status}

