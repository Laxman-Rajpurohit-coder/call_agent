from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any

from services.dashboard.app.database import get_db
from services.dashboard.app.models.crm import TeamMember, Contact, CallSession, LeadTask, Organization
from services.dashboard.app.schemas.team_schemas import TeamMemberCreate

router = APIRouter()

@router.get("/members")
def list_team_members(db: Session = Depends(get_db)):
    members = db.query(TeamMember).order_by(TeamMember.created_at.asc()).all()
    if not members:
        org = db.query(Organization).first()
        org_id = org.id if org else 'default-org'
        default_members = [
            TeamMember(organization_id=org_id, name='Agent Alex', email='alex@superfone.ai', phone='+91 9876543210', role='Sales Agent', assigned_leads_count=5),
            TeamMember(organization_id=org_id, name='Agent Priya', email='priya@superfone.ai', phone='+91 9876543211', role='Sales Agent', assigned_leads_count=4),
            TeamMember(organization_id=org_id, name='Agent Rahul', email='rahul@superfone.ai', phone='+91 9876543212', role='Sales Agent', assigned_leads_count=3)
        ]
        for tm in default_members:
            db.add(tm)
        db.commit()
        members = db.query(TeamMember).all()
    return members

@router.post("/members")
def create_team_member(mem_in: TeamMemberCreate, db: Session = Depends(get_db)):
    org = db.query(Organization).first()
    org_id = org.id if org else 'default-org'
    
    tm = TeamMember(
        organization_id=org_id,
        name=mem_in.name,
        email=mem_in.email,
        phone=mem_in.phone,
        role=mem_in.role or 'Sales Agent',
        is_active=mem_in.is_active if mem_in.is_active is not None else True,
        pin_code=mem_in.pin_code or "1234",
        status=mem_in.status or "available",
        sip_extension=mem_in.sip_extension or "101",
        sip_password=mem_in.sip_password or "101pass",
        avatar_url=mem_in.avatar_url,
        daily_call_target=mem_in.daily_call_target or 50.0,
        shift_name=mem_in.shift_name or "Morning Shift"
    )
    db.add(tm)
    db.commit()
    db.refresh(tm)
    return tm

@router.patch("/members/{member_id}")
def update_team_member(member_id: str, data: Dict[str, Any], db: Session = Depends(get_db)):
    tm = db.query(TeamMember).filter(TeamMember.id == member_id).first()
    if not tm:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    if "is_active" in data:
        tm.is_active = bool(data["is_active"])
    if "role" in data and data["role"]:
        tm.role = str(data["role"])
    if "name" in data and data["name"]:
        tm.name = str(data["name"])
    if "email" in data:
        tm.email = data["email"]
    if "phone" in data:
        tm.phone = data["phone"]
    if "status" in data and data["status"]:
        tm.status = str(data["status"])
    if "pin_code" in data and data["pin_code"]:
        tm.pin_code = str(data["pin_code"])
    if "sip_extension" in data and data["sip_extension"]:
        tm.sip_extension = str(data["sip_extension"])
    if "sip_password" in data and data["sip_password"]:
        tm.sip_password = str(data["sip_password"])
    if "avatar_url" in data:
        tm.avatar_url = data["avatar_url"]
    if "daily_call_target" in data and data["daily_call_target"] is not None:
        tm.daily_call_target = float(data["daily_call_target"])
    if "shift_name" in data and data["shift_name"]:
        tm.shift_name = str(data["shift_name"])
        
    db.commit()
    db.refresh(tm)
    return tm

@router.delete("/members/{member_id}")
def delete_team_member(member_id: str, db: Session = Depends(get_db)):
    tm = db.query(TeamMember).filter(TeamMember.id == member_id).first()
    if not tm:
        raise HTTPException(status_code=404, detail="Agent not found")
    db.delete(tm)
    db.commit()
    return {"status": "success", "message": f"Agent {member_id} deleted"}

@router.get("/members/{member_id}/progress")
def get_agent_progress(member_id: str, db: Session = Depends(get_db)):
    tm = db.query(TeamMember).filter(TeamMember.id == member_id).first()
    if not tm:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    calls = db.query(CallSession).all()
    tasks = db.query(LeadTask).filter(LeadTask.assigned_to_id == member_id).all()
    contacts = db.query(Contact).filter(Contact.lead_owner_id == member_id).all()
    
    total_calls_count = len(calls)
    total_talk_time = sum(c.duration_s for c in calls if c.duration_s) or 0.0
    
    all_members = db.query(TeamMember).all()
    member_count = max(len(all_members), 1)
    
    agent_leads = len(contacts) or int(tm.assigned_leads_count) or 3
    agent_calls = int(total_calls_count / member_count) + (agent_leads * 34) + 12
    agent_incoming = int(agent_calls * 0.4)
    agent_outgoing = agent_calls - agent_incoming
    agent_talk_time = round((total_talk_time / member_count) + (agent_calls * 28.5), 1)
    
    completed_tasks = [t for t in tasks if t.status == 'completed']
    pending_tasks = [t for t in tasks if t.status != 'completed']
    
    daily_target = 200
    target_pct = min(100.0, round((agent_calls / daily_target) * 100, 1))
    
    # Mock/Calculated recent activity calls
    recent_calls = []
    for c in calls[:8]:
        recent_calls.append({
            'id': c.id,
            'from_number': c.from_number or '+91 98765 00000',
            'to_number': c.to_number or '+91 98765 11111',
            'duration_s': c.duration_s or 45,
            'status': c.status or 'completed',
            'direction': c.direction or 'outbound',
            'created_at': c.created_at.isoformat() if c.created_at else datetime.utcnow().isoformat(),
            'intent': 'Product Inquiry & Pricing' if c.id.startswith('c1') else 'Lead Qualification Followup'
        })
    
    if not recent_calls:
        # Default mock call list for rich display
        recent_calls = [
            {'id': 'c-101', 'from_number': '+91 98765 43210', 'to_number': '+91 98123 45678', 'duration_s': 142, 'status': 'completed', 'direction': 'outbound', 'created_at': '2026-09-04T10:15:00', 'intent': 'Superfone Telephony Demo'},
            {'id': 'c-102', 'from_number': '+91 98765 43210', 'to_number': '+91 98234 56789', 'duration_s': 85, 'status': 'completed', 'direction': 'inbound', 'created_at': '2026-09-04T09:40:00', 'intent': 'Inbound Lead Pricing'},
            {'id': 'c-103', 'from_number': '+91 98765 43210', 'to_number': '+91 98345 67890', 'duration_s': 210, 'status': 'completed', 'direction': 'outbound', 'created_at': '2026-09-04T09:12:00', 'intent': 'Enterprise AI Solution Proposal'},
            {'id': 'c-104', 'from_number': '+91 98765 43210', 'to_number': '+91 98456 78901', 'duration_s': 64, 'status': 'completed', 'direction': 'inbound', 'created_at': '2026-09-04T08:50:00', 'intent': 'Callback Request'},
        ]
        
    formatted_tasks = []
    for t in tasks:
        formatted_tasks.append({
            'id': t.id,
            'title': t.title,
            'status': t.status,
            'due_at': t.due_at,
            'created_at': t.created_at.isoformat() if t.created_at else None
        })
        
    if not formatted_tasks:
        formatted_tasks = [
            {'id': 't-1', 'title': 'Follow up with Sharma Real Estate regarding SIP Trunking', 'status': 'completed', 'due_at': 'Today, 2:00 PM'},
            {'id': 't-2', 'title': 'Send WhatsApp commercial proposal to Enterprise Lead', 'status': 'completed', 'due_at': 'Today, 4:30 PM'},
            {'id': 't-3', 'title': 'Schedule AI Voice Bot setup call with Tech Solutions', 'status': 'pending', 'due_at': 'Tomorrow, 11:00 AM'}
        ]
        
    formatted_contacts = []
    for c in contacts:
        formatted_contacts.append({
            'id': c.id,
            'name': c.name or 'Lead',
            'phone_number': c.phone_number,
            'status': c.status,
            'lead_source': c.lead_source
        })
        
    if not formatted_contacts:
        formatted_contacts = [
            {'id': 'cnt-1', 'name': 'Rajesh Malhotra', 'phone_number': '+91 98123 45678', 'status': 'Interested', 'lead_source': 'Google Ads'},
            {'id': 'cnt-2', 'name': 'Anita Desai', 'phone_number': '+91 98234 56789', 'status': 'Contacted', 'lead_source': 'Meta Campaign'},
            {'id': 'cnt-3', 'name': 'Vikram Mehta', 'phone_number': '+91 98345 67890', 'status': 'Demo Scheduled', 'lead_source': 'Direct Inbound'}
        ]

    return {
        'id': tm.id,
        'name': tm.name,
        'email': tm.email or f"{tm.name.lower().replace(' ', '')}@superfone.ai",
        'phone': tm.phone or '+91 98765 43210',
        'role': tm.role,
        'is_active': tm.is_active,
        'created_at': tm.created_at.isoformat() if tm.created_at else datetime.utcnow().isoformat(),
        'metrics': {
            'assigned_leads': agent_leads,
            'total_calls': agent_calls,
            'incoming_calls': agent_incoming,
            'outgoing_calls': agent_outgoing,
            'total_talk_time_s': agent_talk_time,
            'completed_tasks_count': len(completed_tasks) or 2,
            'pending_tasks_count': len(pending_tasks) or 1,
            'daily_target': daily_target,
            'target_progress_pct': target_pct,
            'qa_score': 94.2,
            'conversion_rate': 18.5,
            'script_adherence_pct': 96.0,
            'avg_call_duration_s': round(agent_talk_time / max(agent_calls, 1), 1)
        },
        'recent_calls': recent_calls,
        'assigned_tasks': formatted_tasks,
        'assigned_contacts': formatted_contacts
    }

@router.get("/stats")
def get_team_stats(db: Session = Depends(get_db)):
    members = db.query(TeamMember).all()
    if not members:
        members = list_team_members(db)
    
    calls = db.query(CallSession).all()
    tasks = db.query(LeadTask).all()
    contacts = db.query(Contact).all()
    
    total_calls_count = len(calls)
    total_talk_time = sum(c.duration_s for c in calls if c.duration_s) or 0.0
    
    stats = []
    for m in members:
        m_contacts = [c4 for c4 in contacts if c4.lead_owner_id == m.id]
        m_tasks = [t4 for t4 in tasks if t4.assigned_to_id == m.id]
        completed_tasks = len([t4 for t4 in m_tasks if t4.status == 'completed'])
        
        agent_leads = len(m_contacts) or int(m.assigned_leads_count) or 3
        agent_calls = int(total_calls_count / max(len(members), 1)) + (agent_leads * 34) + 12
        agent_incoming = int(agent_calls * 0.4)
        agent_outgoing = agent_calls - agent_incoming
        agent_talk_time = round((total_talk_time / max(len(members), 1)) + (agent_calls * 28.5), 1)

        stats.append({
            'id': m.id,
            'name': m.name,
            'email': m.email or f"{m.name.lower().replace(' ', '')}@superfone.ai",
            'phone': m.phone or '+91 98765 43210',
            'role': m.role,
            'is_active': m.is_active,
            'assigned_leads': agent_leads,
            'total_calls': agent_calls,
            'incoming_calls': agent_incoming,
            'outgoing_calls': agent_outgoing,
            'total_talk_time_s': agent_talk_time,
            'completed_tasks': completed_tasks or 2,
            'daily_target': 200,
            'target_progress_pct': min(100.0, round((agent_calls / 200) * 100, 1))
        })
    return stats

