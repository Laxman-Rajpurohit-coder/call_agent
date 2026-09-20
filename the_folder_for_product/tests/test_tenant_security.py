import os
import sys
import uuid
from datetime import datetime, timedelta
import pytest
import jwt
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Setup paths
workspace_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if workspace_dir not in sys.path:
    sys.path.insert(0, workspace_dir)

from services.dashboard.app.config import settings
from services.dashboard.app.database import Base, get_db
from services.dashboard.app.main import app
from services.dashboard.app.dependencies import create_access_token, hash_password
from services.dashboard.app.models.crm import (
    Organization, TeamMember, Contact, LeadTask, CallSession, CallInteraction
)
from services.dashboard.app.models.campaign import Campaign, CampaignAgent
from services.dashboard.app.services.storage import RecordingStorageService, storage_service

# Create an isolated in-memory test SQLite database
TEST_DB_URL = "sqlite:///:memory:"
test_engine = create_engine(
    TEST_DB_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)

@pytest.fixture(scope="module", autouse=True)
def setup_test_db():
    """Create all tables in the test in-memory SQLite database."""
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)

@pytest.fixture(scope="module")
def db_session():
    """Provide a transactional database session for tests."""
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

@pytest.fixture(scope="module")
def seed_data(db_session):
    """Seed multi-tenant fixture data with Org A and Org B, agents, leads, tasks, and calls."""
    # Organizations
    org_a = Organization(
        id="org-a-1111",
        name="Smile Dental Clinic",
        slug="test-smile-dental",
        is_active=True
    )
    org_b = Organization(
        id="org-b-2222",
        name="Apex Super Specialty Hospital",
        slug="test-apex-hospital",
        is_active=True
    )
    db_session.add_all([org_a, org_b])
    db_session.flush()

    # Users in Org A
    admin_a = TeamMember(
        id="user-admin-a",
        organization_id=org_a.id,
        name="Dr. Sharma (Admin)",
        email="admin.a@test.com",
        role="ADMIN",
        password_hash=hash_password("admin123"),
        is_active=True
    )
    alex_a = TeamMember(
        id="user-alex-a",
        organization_id=org_a.id,
        name="Agent Alex",
        email="alex.a@test.com",
        role="AGENT",
        password_hash=hash_password("alex123"),
        is_active=True
    )
    vikas_a = TeamMember(
        id="user-vikas-a",
        organization_id=org_a.id,
        name="Agent Vikas",
        email="vikas.a@test.com",
        role="AGENT",
        password_hash=hash_password("vikas123"),
        is_active=True
    )
    viewer_a = TeamMember(
        id="user-viewer-a",
        organization_id=org_a.id,
        name="Audit Viewer",
        email="viewer.a@test.com",
        role="VIEWER",
        password_hash=hash_password("viewer123"),
        is_active=True
    )
    inactive_a = TeamMember(
        id="user-inactive-a",
        organization_id=org_a.id,
        name="Terminated Agent",
        email="inactive.a@test.com",
        role="AGENT",
        password_hash=hash_password("inactive123"),
        is_active=False
    )

    # Users in Org B
    agent_b = TeamMember(
        id="user-agent-b",
        organization_id=org_b.id,
        name="Agent John (Org B)",
        email="john.b@test.com",
        role="AGENT",
        password_hash=hash_password("john123"),
        is_active=True
    )

    db_session.add_all([admin_a, alex_a, vikas_a, viewer_a, inactive_a, agent_b])
    db_session.flush()

    # Contacts/Leads
    lead_alex = Contact(
        id="lead-alex-org-a",
        organization_id=org_a.id,
        phone_number="+919876543211",
        name="Ramesh Kumar (Alex's Lead)",
        lead_owner_id=alex_a.id,
        status="lead"
    )
    lead_vikas = Contact(
        id="lead-vikas-org-a",
        organization_id=org_a.id,
        phone_number="+919876543212",
        name="Suresh Patel (Vikas's Lead)",
        lead_owner_id=vikas_a.id,
        status="lead"
    )
    lead_org_b = Contact(
        id="lead-org-b",
        organization_id=org_b.id,
        phone_number="+919876543213",
        name="Org B Patient",
        lead_owner_id=agent_b.id,
        status="lead"
    )
    db_session.add_all([lead_alex, lead_vikas, lead_org_b])
    db_session.flush()

    # Tasks
    task_alex = LeadTask(
        id="task-alex-org-a",
        organization_id=org_a.id,
        contact_id=lead_alex.id,
        assigned_to_id=alex_a.id,
        title="Follow up with Ramesh",
        status="pending"
    )
    task_vikas = LeadTask(
        id="task-vikas-org-a",
        organization_id=org_a.id,
        contact_id=lead_vikas.id,
        assigned_to_id=vikas_a.id,
        title="Follow up with Suresh",
        status="pending"
    )
    task_org_b = LeadTask(
        id="task-org-b",
        organization_id=org_b.id,
        contact_id=lead_org_b.id,
        assigned_to_id=agent_b.id,
        title="Org B Hospital Task",
        status="pending"
    )
    db_session.add_all([task_alex, task_vikas, task_org_b])
    db_session.flush()

    # Call Sessions & test audio file
    test_recordings_dir = os.path.abspath(settings.RECORDINGS_DIR)
    os.makedirs(test_recordings_dir, exist_ok=True)
    sample_wav_path = os.path.join(test_recordings_dir, "test_call_sample.wav")
    with open(sample_wav_path, "wb") as f:
        # Minimal dummy WAV byte sequence
        f.write(b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x40\x1f\x00\x00\x40\x1f\x00\x00\x01\x00\x08\x00data\x00\x00\x00\x00")

    call_alex = CallSession(
        id="call-alex-org-a",
        organization_id=org_a.id,
        contact_id=lead_alex.id,
        handled_by_user_id=alex_a.id,
        from_number="+919876543210",
        to_number=lead_alex.phone_number,
        direction="OUTBOUND",
        status="COMPLETED",
        duration_s=45,
        recording_storage_key="test_call_sample.wav"
    )
    call_vikas = CallSession(
        id="call-vikas-org-a",
        organization_id=org_a.id,
        contact_id=lead_vikas.id,
        handled_by_user_id=vikas_a.id,
        from_number="+919876543210",
        to_number=lead_vikas.phone_number,
        direction="OUTBOUND",
        status="COMPLETED",
        duration_s=60,
        recording_storage_key="test_call_sample.wav"
    )
    call_org_b = CallSession(
        id="call-org-b",
        organization_id=org_b.id,
        contact_id=lead_org_b.id,
        handled_by_user_id=agent_b.id,
        from_number="+919999999999",
        to_number=lead_org_b.phone_number,
        direction="OUTBOUND",
        status="COMPLETED",
        duration_s=30,
        recording_storage_key="test_call_sample.wav"
    )
    db_session.add_all([call_alex, call_vikas, call_org_b])
    db_session.flush()

    # Campaigns & CampaignAgent Enrollments
    campaign_a = Campaign(
        id="campaign-org-a",
        organization_id=org_a.id,
        name="Smile Dental Follow-up Drive",
        status="RUNNING"
    )
    campaign_b = Campaign(
        id="campaign-org-b",
        organization_id=org_b.id,
        name="Apex Hospital Health Camp",
        status="RUNNING"
    )
    db_session.add_all([campaign_a, campaign_b])
    db_session.flush()

    # Alex enrolled in campaign_a; Vikas is NOT enrolled
    membership_alex = CampaignAgent(
        id="camp-agent-alex",
        campaign_id=campaign_a.id,
        user_id=alex_a.id,
        role_in_campaign="dialer"
    )
    db_session.add(membership_alex)
    db_session.commit()

    return {
        "org_a": org_a,
        "org_b": org_b,
        "admin_a": admin_a,
        "alex_a": alex_a,
        "vikas_a": vikas_a,
        "viewer_a": viewer_a,
        "inactive_a": inactive_a,
        "agent_b": agent_b,
        "lead_alex": lead_alex,
        "lead_vikas": lead_vikas,
        "lead_org_b": lead_org_b,
        "task_alex": task_alex,
        "task_vikas": task_vikas,
        "task_org_b": task_org_b,
        "call_alex": call_alex,
        "call_vikas": call_vikas,
        "call_org_b": call_org_b,
        "campaign_a": campaign_a,
        "campaign_b": campaign_b
    }

# ==============================================================================
# SECTION 1: AUTHENTICATION TESTS
# ==============================================================================

def test_auth_valid_token(seed_data):
    """Assert valid JWT authenticates and returns DB-authoritative user profile."""
    alex = seed_data["alex_a"]
    token = create_access_token({"sub": alex.id, "email": alex.email})
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.get("/api/v1/auth/me", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == alex.id
    assert data["organization_id"] == seed_data["org_a"].id
    assert data["role"] == "AGENT"

def test_auth_expired_token(seed_data):
    """Assert expired JWT is rejected with 401 Unauthorized."""
    alex = seed_data["alex_a"]
    expired_token = create_access_token(
        {"sub": alex.id, "email": alex.email},
        expires_delta=timedelta(seconds=-60)
    )
    headers = {"Authorization": f"Bearer {expired_token}"}

    resp = client.get("/api/v1/auth/me", headers=headers)
    assert resp.status_code == 401
    assert "expired" in resp.json()["detail"].lower()

def test_auth_invalid_signature(seed_data):
    """Assert JWT signed with rogue secret is rejected with 401 Unauthorized."""
    alex = seed_data["alex_a"]
    rogue_secret = "completely_wrong_secret_key_that_does_not_match_app_config_123"
    rogue_token = jwt.encode(
        {"sub": alex.id, "exp": datetime.utcnow() + timedelta(hours=1)},
        rogue_secret,
        algorithm="HS256"
    )
    headers = {"Authorization": f"Bearer {rogue_token}"}

    resp = client.get("/api/v1/auth/me", headers=headers)
    assert resp.status_code == 401
    assert "invalid" in resp.json()["detail"].lower()

def test_auth_inactive_user(seed_data):
    """Assert deactivated user (is_active=False) is rejected with 401 Unauthorized."""
    inactive = seed_data["inactive_a"]
    token = create_access_token({"sub": inactive.id, "email": inactive.email})
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.get("/api/v1/auth/me", headers=headers)
    assert resp.status_code == 401
    assert "deactivated" in resp.json()["detail"].lower()

# ==============================================================================
# SECTION 2: TENANT ISOLATION TESTS (STEALTH 404 & ORG_ID TAMPERING)
# ==============================================================================

def test_tenant_isolation_leads_stealth_404(seed_data):
    """Assert User in Org A requesting Org B's lead receives Stealth 404 (no enumeration)."""
    alex = seed_data["alex_a"]
    lead_b = seed_data["lead_org_b"]
    token = create_access_token({"sub": alex.id})
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.get(f"/api/v1/contacts/{lead_b.id}", headers=headers)
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()

def test_tenant_isolation_tasks_stealth_404(seed_data):
    """Assert User in Org A requesting Org B's task receives Stealth 404."""
    alex = seed_data["alex_a"]
    task_b = seed_data["task_org_b"]
    token = create_access_token({"sub": alex.id})
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.get(f"/api/v1/tasks/{task_b.id}", headers=headers)
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()

def test_tenant_isolation_calls_stealth_404(seed_data):
    """Assert User in Org A requesting Org B's call recording receives Stealth 404."""
    alex = seed_data["alex_a"]
    call_b = seed_data["call_org_b"]
    token = create_access_token({"sub": alex.id})
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.get(f"/api/v1/calls/{call_b.id}/recording", headers=headers)
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()

def test_client_org_id_tampering_rejected(seed_data, db_session):
    """
    Assert that client-supplied organization_id is ignored/rejected,
    and the resource is bound strictly to the DB user's organization_id.
    """
    alex = seed_data["alex_a"]
    token = create_access_token({"sub": alex.id})
    headers = {"Authorization": f"Bearer {token}"}

    # Alex attempts to inject Org B's ID in payload
    tampered_payload = {
        "phone_number": "+919111222333",
        "name": "Tampered Lead Injection",
        "organization_id": seed_data["org_b"].id
    }
    resp = client.post("/api/v1/contacts", json=tampered_payload, headers=headers)
    assert resp.status_code == 200

    # Verify DB: must belong to Org A, NEVER Org B!
    created_contact = db_session.query(Contact).filter(Contact.phone_number == "+919111222333").first()
    assert created_contact is not None
    assert created_contact.organization_id == seed_data["org_a"].id
    assert created_contact.organization_id != seed_data["org_b"].id

# ==============================================================================
# SECTION 3: INTRA-TENANT AGENT CONFIDENTIALITY (403 FORBIDDEN)
# ==============================================================================

def test_agent_cannot_access_other_agent_lead(seed_data):
    """Assert Agent Alex accessing Agent Vikas's assigned lead receives 403 Forbidden."""
    alex = seed_data["alex_a"]
    lead_vikas = seed_data["lead_vikas"]
    token = create_access_token({"sub": alex.id})
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.get(f"/api/v1/contacts/{lead_vikas.id}", headers=headers)
    assert resp.status_code == 403
    assert "access denied" in resp.json()["detail"].lower()

def test_agent_can_access_own_lead(seed_data):
    """Assert Agent Alex can access their own assigned lead."""
    alex = seed_data["alex_a"]
    lead_alex = seed_data["lead_alex"]
    token = create_access_token({"sub": alex.id})
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.get(f"/api/v1/contacts/{lead_alex.id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == lead_alex.id

def test_admin_can_access_any_tenant_lead(seed_data):
    """Assert Admin in Org A can access any lead within the organization."""
    admin = seed_data["admin_a"]
    lead_vikas = seed_data["lead_vikas"]
    token = create_access_token({"sub": admin.id})
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.get(f"/api/v1/contacts/{lead_vikas.id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == lead_vikas.id

def test_agent_cannot_access_other_agent_task(seed_data):
    """Assert Agent Alex accessing Agent Vikas's task receives 403 Forbidden."""
    alex = seed_data["alex_a"]
    task_vikas = seed_data["task_vikas"]
    token = create_access_token({"sub": alex.id})
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.get(f"/api/v1/tasks/{task_vikas.id}", headers=headers)
    assert resp.status_code == 403
    assert "access denied" in resp.json()["detail"].lower()

def test_agent_cannot_access_other_agent_call(seed_data):
    """Assert Agent Alex accessing Agent Vikas's handled call receives 403 Forbidden."""
    alex = seed_data["alex_a"]
    call_vikas = seed_data["call_vikas"]
    token = create_access_token({"sub": alex.id})
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.get(f"/api/v1/calls/{call_vikas.id}/recording", headers=headers)
    assert resp.status_code == 403
    assert "access denied" in resp.json()["detail"].lower()

def test_agent_can_access_own_call_recording(seed_data):
    """Assert Agent Alex can stream their own handled call recording."""
    alex = seed_data["alex_a"]
    call_alex = seed_data["call_alex"]
    token = create_access_token({"sub": alex.id})
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.get(f"/api/v1/calls/{call_alex.id}/recording", headers=headers)
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("audio/")

# ==============================================================================
# SECTION 4: CAMPAIGN MEMBERSHIP ISOLATION
# ==============================================================================

def test_campaign_enrolled_agent_permitted(seed_data):
    """Assert Agent Alex enrolled in Campaign A can access campaign contacts."""
    alex = seed_data["alex_a"]
    campaign_a = seed_data["campaign_a"]
    token = create_access_token({"sub": alex.id})
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.get(f"/api/v1/campaigns/{campaign_a.id}/contacts", headers=headers)
    assert resp.status_code == 200

def test_campaign_non_enrolled_agent_rejected(seed_data):
    """Assert Agent Vikas NOT enrolled in Campaign A receives 403 Forbidden."""
    vikas = seed_data["vikas_a"]
    campaign_a = seed_data["campaign_a"]
    token = create_access_token({"sub": vikas.id})
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.get(f"/api/v1/campaigns/{campaign_a.id}/contacts", headers=headers)
    assert resp.status_code == 403
    assert "access denied" in resp.json()["detail"].lower()

def test_campaign_cross_tenant_rejected(seed_data):
    """Assert Agent in Org A requesting Org B's campaign receives Stealth 404."""
    alex = seed_data["alex_a"]
    campaign_b = seed_data["campaign_b"]
    token = create_access_token({"sub": alex.id})
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.get(f"/api/v1/campaigns/{campaign_b.id}/contacts", headers=headers)
    assert resp.status_code == 404

# ==============================================================================
# SECTION 5: RECORDING AUTHORIZATION & PATH TRAVERSAL RESISTANCE
# ==============================================================================

def test_recording_path_traversal_rejected():
    """Assert RecordingStorageService rejects directory traversal attempts."""
    service = storage_service

    with pytest.raises(ValueError, match="Potential path traversal detected"):
        service.resolve_recording_path("../../etc/passwd")

    with pytest.raises(ValueError, match="Potential path traversal detected"):
        service.resolve_recording_path("..\\..\\windows\\system32\\calc.exe")

    with pytest.raises(ValueError, match="Potential path traversal detected"):
        service.resolve_recording_path("org_a/../../../secret.wav")

# ==============================================================================
# SECTION 6: ROLE PERMISSIONS & VIEWER MUTATION BLOCKS
# ==============================================================================

def test_viewer_role_mutation_blocked(seed_data):
    """Assert VIEWER role is strictly read-only and cannot mutate contacts or tasks."""
    viewer = seed_data["viewer_a"]
    token = create_access_token({"sub": viewer.id})
    headers = {"Authorization": f"Bearer {token}"}

    # Mutation 1: Create contact
    resp_create = client.post(
        "/api/v1/contacts",
        json={"phone_number": "+919555444333", "name": "Viewer Attempt"},
        headers=headers
    )
    assert resp_create.status_code == 403
    assert "read-only" in resp_create.json()["detail"].lower()

    # Mutation 2: Update task
    task_alex = seed_data["task_alex"]
    resp_task = client.patch(
        f"/api/v1/tasks/{task_alex.id}",
        json={"status": "completed"},
        headers=headers
    )
    assert resp_task.status_code == 403
    assert "read-only" in resp_task.json()["detail"].lower()

def test_admin_mutation_permitted(seed_data):
    """Assert ADMIN role can execute mutations successfully."""
    admin = seed_data["admin_a"]
    task_alex = seed_data["task_alex"]
    token = create_access_token({"sub": admin.id})
    headers = {"Authorization": f"Bearer {token}"}

    resp_task = client.patch(
        f"/api/v1/tasks/{task_alex.id}",
        json={"status": "completed"},
        headers=headers
    )
    assert resp_task.status_code == 200
    assert resp_task.json()["status"] == "completed"

# ==============================================================================
# SECTION 7: MULTI-TENANT PORTAL PROVISIONING TESTS (PHASE 3)
# ==============================================================================

def test_portal_provisioning_atomic(db_session):
    """Assert POST /api/v1/portals provisions 6 entities atomically in a transaction."""
    payload = {
        "name": "Metro Fertility Care",
        "slug": "metro-fertility",
        "industry": "Healthcare / Fertility",
        "portal_name": "Metro Fertility AI CRM",
        "subtitle": "Compassionate Fertility Consultations",
        "theme_primary": "#ec4899",
        "agent_name": "Maya",
        "services": [
            {"name": "IVF Initial Consultation", "price": 1500.0, "duration_mins": 45, "category": "Consultation"}
        ],
        "phone_numbers": [
            {"phone_number": "+919876500000", "provider": "Exotel", "purpose": "reception", "is_primary": True}
        ],
        "initial_user": {
            "name": "Dr. Ananya",
            "email": "ananya@metrofertility.com",
            "password": "secret_password_123",
            "role": "ADMIN"
        }
    }

    resp = client.post("/api/v1/portals", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["success"] is True
    assert data["portal"]["slug"] == "metro-fertility"

    # Verify entities in DB
    org = db_session.query(Organization).filter(Organization.slug == "metro-fertility").first()
    assert org is not None
    assert org.name == "Metro Fertility Care"
    assert org.portal_config.portal_name == "Metro Fertility AI CRM"
    assert org.agent_config.agent_name == "Maya"
    assert len(org.services) == 1
    assert org.services[0].name == "IVF Initial Consultation"
    assert len(org.phone_numbers) == 1
    assert org.phone_numbers[0].phone_number == "+919876500000"
    assert len(org.team_members) == 1
    assert org.team_members[0].email == "ananya@metrofertility.com"
    assert org.team_members[0].password_hash is not None

def test_portal_public_whitelist():
    """Assert GET /api/v1/portals/{slug}/public returns strict whitelist and zero secrets."""
    resp = client.get("/api/v1/portals/metro-fertility/public")
    assert resp.status_code == 200
    data = resp.json()

    # Verify public fields
    assert data["organization"]["slug"] == "metro-fertility"
    assert data["branding"]["theme_primary"] == "#ec4899"
    assert data["ai_receptionist"]["agent_name"] == "Maya"
    assert len(data["services"]) == 1
    assert data["services"][0]["name"] == "IVF Initial Consultation"

    # Strict assertion: NO sensitive fields exposed
    assert "password_hash" not in str(data)
    assert "secret" not in str(data)
    assert "sip_password" not in str(data)
    assert "audit_logs" not in data

def test_portal_slug_uniqueness():
    """Assert duplicate slug is rejected with 400 Bad Request."""
    payload = {
        "name": "Duplicate Metro",
        "slug": "metro-fertility",
        "industry": "Healthcare"
    }
    resp = client.post("/api/v1/portals", json=payload)
    assert resp.status_code == 400
    assert "already exists" in resp.json()["detail"].lower()
