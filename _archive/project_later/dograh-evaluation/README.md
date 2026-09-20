# Dograh Self-Hosted Voice Agent Platform Evaluation Sandbox

This sandbox evaluates **Dograh Self-Hosted** against our frozen reference baseline (`v0.1.2-eval-echo-noise-gate`).

---

## 1. Directory Structure

```text
dograh-evaluation/
├── docker-compose.yml           # Dograh Voice Runtime + PostgreSQL container
├── tools/
│   ├── crm_bridge.py            # FastAPI/aiohttp MCP & HTTP tool bridge
│   ├── db_schema.sql            # PostgreSQL / SQLite relational CRM schema
│   ├── test_tools_db.py         # Unit tests verifying DB persistence
│   └── crm.db                   # SQLite persistent database for tools
├── evaluation/
│   ├── diagnostics/
│   │   └── audio_stages.py      # 3-stage audio capture (raw, telephony, playback)
│   └── run_comparison.py        # 25-call comparative benchmark runner
└── README.md
```

---

## 2. Running the CRM Tool Bridge

Start the standalone tool server on port `9098`:
```powershell
& ".\venv\Scripts\python.exe" dograh-evaluation/tools/crm_bridge.py
```

Endpoints exposed:
- `POST /tools/tag_customer` (`{customer_id, tag, reason}`)
- `POST /tools/save_call_note` (`{call_id, summary, action_items, customer_id}`)
- `POST /tools/schedule_callback` (`{customer_id, phone_number, scheduled_time}`)
- `GET /tools/verify/{table_name}` (Direct DB verification)

---

## 3. Running the 25-Call Comparative Benchmark

Run the automated 25-call benchmark (10 normal calls, 5 interruptions, 5 noise resilience, 5 long cadence) across either platform:

```powershell
& ".\venv\Scripts\python.exe" dograh-evaluation/evaluation/run_comparison.py current_baseline
```

---

## 4. Decision Gate Criteria

Adopt **Dograh Self-Hosted** if it satisfies:
- [ ] $\ge 90\%$ pass on 25 comparative test calls
- [ ] $0$ audible mid-sentence cutoffs or queue underflows
- [ ] $100\%$ database persistence for CRM tool actions
- [ ] Clean SIP/RTP audio connection to Asterisk
