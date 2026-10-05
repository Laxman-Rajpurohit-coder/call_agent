from sqlalchemy.orm import Session
from typing import Dict, Any, Tuple
import json

from services.dashboard.app.models.crm import (
    IncomingCallConfig, AgentConfig, PhoneNumber, CallSession
)

def resolve_incoming_call(db: Session, to_number: str, organization_id: str) -> Tuple[str, int, Dict[str, Any]]:
    """
    Resolves the configuration for an incoming call following the hierarchy:
    1. Phone-specific config
    2. Organization default config
    3. Legacy AgentConfig
    
    Returns:
        (incoming_config_id, config_version, config_snapshot_json)
    """
    
    # 1. Try Phone-specific config
    phone = db.query(PhoneNumber).filter(
        PhoneNumber.phone_number == to_number,
        PhoneNumber.organization_id == organization_id
    ).first()
    
    if phone:
        phone_config = db.query(IncomingCallConfig).filter(
            IncomingCallConfig.phone_number_id == phone.id,
            IncomingCallConfig.is_active == True
        ).first()
        
        if phone_config:
            return _build_snapshot(phone_config)
            
    # 2. Try Organization default config (phone_number_id IS NULL)
    org_default = db.query(IncomingCallConfig).filter(
        IncomingCallConfig.organization_id == organization_id,
        IncomingCallConfig.phone_number_id == None,
        IncomingCallConfig.is_active == True
    ).order_by(IncomingCallConfig.priority.desc()).first()
    
    if org_default:
        return _build_snapshot(org_default)
        
    # 3. Fallback to Legacy AgentConfig
    legacy_config = db.query(AgentConfig).filter(
        AgentConfig.organization_id == organization_id
    ).first()
    
    if legacy_config:
        # Wrap legacy config in standard snapshot shape
        snapshot = {
            "ai_name": legacy_config.agent_name or "Agent",
            "voice_model": legacy_config.voice_model,
            "primary_language": legacy_config.language,
            "system_instructions": legacy_config.system_instructions,
            "max_call_duration_s": legacy_config.max_call_duration_s,
            "is_legacy_fallback": True
        }
        return (None, 0, snapshot)
        
    raise ValueError(f"No valid configuration found for {to_number} in org {organization_id}")


def _build_snapshot(config: IncomingCallConfig) -> Tuple[str, int, Dict[str, Any]]:
    # Convert config columns to dictionary snapshot
    snapshot = {c.name: getattr(config, c.name) for c in config.__table__.columns if c.name not in ["id", "created_at", "updated_at"]}
    return (config.id, config.config_version, snapshot)


def compile_runtime_prompt(snapshot: Dict[str, Any], crm_context: Dict[str, Any]) -> str:
    """
    Compiles the final system prompt by mixing the static config snapshot 
    with the dynamic caller / CRM context.
    """
    
    if snapshot.get("is_legacy_fallback"):
        return f"SYSTEM INSTRUCTIONS:\\n{snapshot.get('system_instructions', '')}\\nCALLER CONTEXT:\\n{json.dumps(crm_context)}"

    prompt_parts = []
    
    # Identity
    ai_name = snapshot.get("ai_name", "AI")
    role = snapshot.get("role_description", "Receptionist")
    prompt_parts.append(f"IDENTITY: You are {ai_name}, acting as a {role}.")
    
    # Business Context
    biz_name = snapshot.get("business_name")
    if biz_name:
        biz_desc = snapshot.get("business_description", "")
        prompt_parts.append(f"BUSINESS: {biz_name}\\n{biz_desc}")
        
    services = snapshot.get("services_offered", [])
    if services:
        prompt_parts.append("SERVICES OFFERED: " + ", ".join(services))
        
    # Objectives & Rules
    objective = snapshot.get("primary_objective")
    if objective:
        prompt_parts.append(f"PRIMARY OBJECTIVE: {objective}")
        
    rules = snapshot.get("behavior_rules", [])
    if rules:
        rule_str = "\\n- ".join(rules)
        prompt_parts.append(f"BEHAVIOR RULES:\\n- {rule_str}")
        
    # Language
    langs = snapshot.get("supported_languages", [])
    if langs:
        prompt_parts.append(f"SUPPORTED LANGUAGES: {snapshot.get('primary_language', 'en')}, " + ", ".join(langs))
        if snapshot.get("allow_language_switching"):
            prompt_parts.append("You may switch languages if the caller speaks in a supported language.")
            
    # Knowledge Base
    faq = snapshot.get("faq_knowledge_base")
    if faq:
        prompt_parts.append(f"KNOWLEDGE BASE / FAQ:\\n{faq}")
        
    # CRM Context
    if crm_context:
        prompt_parts.append(f"CALLER / CRM CONTEXT:\\n{json.dumps(crm_context, indent=2)}")
        
    # Advanced Instructions
    sys_inst = snapshot.get("system_instructions")
    if sys_inst:
        prompt_parts.append(f"ADVANCED SYSTEM INSTRUCTIONS:\\n{sys_inst}")
        
    return "\\n\\n".join(prompt_parts)

def initialize_call_session(db: Session, to_number: str, organization_id: str, crm_context: Dict[str, Any], **call_kwargs) -> CallSession:
    """
    Convenience method to resolve config, snapshot it, and create the CallSession
    """
    config_id, config_version, snapshot = resolve_incoming_call(db, to_number, organization_id)
    
    import uuid
    session = CallSession(
        id=str(uuid.uuid4()),
        organization_id=organization_id,
        to_number=to_number,
        incoming_config_id=config_id,
        config_version=config_version,
        config_snapshot=snapshot,
        **call_kwargs
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session
