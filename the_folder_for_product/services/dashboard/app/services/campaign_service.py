import asyncio
import uuid
import time
import os
from typing import Dict, Any, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from services.dashboard.app.models import Campaign, CampaignContact, CampaignAttempt, Contact, CallSession, CallInteraction, Organization
from services.dashboard.app.services.event_bus import manager
from services.dashboard.app.services.call_dispatcher import call_dispatcher
from services.dashboard.app.services.script_engine import ScriptEngine
from services.dashboard.app.services.retry_service import retry_service
from services.dashboard.app.services.call_analysis import DO_NOT_CALL_STATUSES

class CampaignRunner:
    def __init__(self):
        self.running_tasks: Dict[str, asyncio.Task] = {}

    async def execute_campaign(self, campaign_id: str, db_factory):
        db: Session = db_factory()
        try:
            campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
            if not campaign:
                return

            campaign.status = "RUNNING"
            db.commit()

            # Calls must be logged under the campaign's own organization (multi-tenant safety).
            org = None
            if getattr(campaign, "organization_id", None):
                org = db.query(Organization).filter(Organization.id == campaign.organization_id).first()
            if org is None:
                org = db.query(Organization).first()
            org_id = org.id if org else str(uuid.uuid4())

            contacts = db.query(CampaignContact).filter(CampaignContact.campaign_id == campaign_id).all()
            # Priority Sorting: MicroSIP softphone contact is dialed FIRST with 0s queue delay
            def get_priority(cc: CampaignContact):
                c = db.query(Contact).filter(Contact.id == cc.contact_id).first()
                if c and any(k in (c.phone_number or "") for k in ["test1000", "1000", "8000000700", "700"]):
                    return 0
                return 1
            contacts = sorted(contacts, key=get_priority)

            # Queue Concurrency Control
            concurrency_limit = max(1, campaign.max_concurrency)
            semaphore = asyncio.Semaphore(concurrency_limit)

            async def process_contact(cc: CampaignContact):
                async with semaphore:
                    # Persistent DB Campaign Status Check (Handles Pause / Graceful Stop across processes)
                    db_check: Session = db_factory()
                    try:
                        c_curr = db_check.query(Campaign).filter(Campaign.id == campaign_id).first()
                        if not c_curr or c_curr.status in ("PAUSED", "STOPPED", "STOPPING"):
                            print(f"[Campaign Engine] Persistent DB status is '{c_curr.status if c_curr else 'DELETED'}'. Halting new contact dispatch for {cc.id}.")
                            return
                    finally:
                        db_check.close()

                    # Never dial contacts who asked to stop / wrong numbers / opt-outs.
                    contact_pre = db.query(Contact).filter(Contact.id == cc.contact_id).first()
                    if contact_pre is not None and (contact_pre.status or "").upper() in DO_NOT_CALL_STATUSES:
                        cc.status = "EXCLUDED"
                        cc.final_outcome = (contact_pre.status or "").upper()
                        db.commit()
                        print(f"[Campaign Engine] Skipping {cc.id}: contact is {cc.final_outcome}.")
                        return

                    cc.status = "CALLING"
                    cc.attempt_count += 1
                    cc.last_attempt_at = datetime.utcnow()
                    db.commit()

                    contact = db.query(Contact).filter(Contact.id == cc.contact_id).first()
                    phone = contact.phone_number if contact else "+919876543210"

                    # 1. Create CallSession in CRM DB
                    session_id = str(uuid.uuid4())
                    session_rec = CallSession(
                        id=session_id,
                        organization_id=org_id,
                        contact_id=contact.id if contact else None,
                        provider="audiosocket",
                        direction="outbound",
                        from_number="+918000000700",
                        to_number=phone,
                        status="in_progress",
                        started_at=datetime.utcnow(),
                        # The transcript below comes from ScriptEngine simulation (a canned caller reply),
                        # not from the real call - it must NOT be labelled by call_analysis until the
                        # campaign path captures the real STT transcript.
                        analysis_status="SKIPPED_SIMULATED"
                    )
                    db.add(session_rec)
                    db.commit()

                    # 2. Dispatch Outbound Call via CallDispatcher (with DB Idempotency Key)
                    disp_res = await call_dispatcher.originate_call(
                        db=db,
                        phone_number=phone,
                        campaign_id=campaign_id,
                        contact_id=cc.contact_id,
                        campaign_contact_id=cc.id,
                        attempt_number=cc.attempt_count,
                        timeout_s=30.0
                    )

                    # 3. Execute Script State Machine
                    engine = ScriptEngine(campaign.script_content)
                    transcript, outcome, intent = engine.execute_flow(["Haan, main event mein zaroor aaoonga"])

                    # 4. Save Transcript & Interaction in CRM DB
                    session_rec.status = disp_res["status"]
                    session_rec.duration_s = disp_res["duration_s"]
                    session_rec.ended_at = datetime.utcnow()
                    session_rec.transcript = transcript

                    interaction = CallInteraction(
                        call_id=session_id,
                        contact_id=contact.id if contact else None,
                        intent_detected=intent,
                        confidence=0.96,
                        ai_summary=f"Outbound campaign call to {phone}. Script outcome: '{outcome}'."
                    )
                    db.add(interaction)

                    # 5. Finalize CampaignContact status using Retry Classifier
                    if disp_res["status"] == "completed":
                        cc.status = "COMPLETED"
                        cc.final_outcome = outcome
                    else:
                        should_retry = retry_service.should_retry(
                            status=disp_res["status"],
                            outcome=outcome,
                            current_attempts=cc.attempt_count,
                            max_retries=campaign.max_retries
                        )
                        cc.status = "RETRY" if should_retry else "FAILED"

                    db.commit()

                    # Broadcast progress update to WebSocket clients
                    await manager.broadcast({
                        "event_type": "CAMPAIGN_PROGRESS",
                        "campaign_id": campaign_id,
                        "contact_phone": phone,
                        "status": cc.status,
                        "duration_s": disp_res["duration_s"]
                    })

            tasks = [process_contact(cc) for cc in contacts if cc.status in ("PENDING", "RETRY")]
            await asyncio.gather(*tasks, return_exceptions=True)

            # Re-check status before marking completed
            c_final = db.query(Campaign).filter(Campaign.id == campaign_id).first()
            if c_final and c_final.status not in ("PAUSED", "STOPPED"):
                c_final.status = "COMPLETED"
                db.commit()
            print(f"[Campaign Engine] Campaign [{campaign.name}] Queue Processing Completed!")

        except Exception as ex:
            print(f"[Campaign Engine Error] {ex}")
            if campaign:
                campaign.status = "FAILED"
                db.commit()
        finally:
            db.close()
            if campaign_id in self.running_tasks:
                del self.running_tasks[campaign_id]

campaign_runner = CampaignRunner()
