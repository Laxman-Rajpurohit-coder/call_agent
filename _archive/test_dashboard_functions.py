import urllib.request
import json
import traceback

BASE_URL = "http://localhost:9090"

endpoints_to_test = [
    ("GET", "/api/v1/health", None),
    ("GET", "/api/v1/overview", None),
    ("GET", "/api/v1/calls", None),
    ("GET", "/api/v1/contacts", None),
    ("GET", "/api/v1/campaigns", None),
    ("GET", "/api/v1/evaluations", None),
    ("GET", "/api/v1/load-tests", None),
    ("GET", "/api/v1/auth/agents", None),
    ("GET", "/api/v1/auth/status", None),
    ("GET", "/api/v1/leads", None),
    ("GET", "/api/v1/reminders", None),
    ("GET", "/api/v1/reminders/active", None),
    ("GET", "/api/v1/tasks", None),
    ("GET", "/api/v1/team/members", None),
    ("GET", "/api/v1/team/stats", None),
    ("GET", "/api/v1/whatsapp/chats", None),
    ("GET", "/api/v1/tools", None),
    ("GET", "/", None),
]

print(f"{'METHOD':<6} {'ENDPOINT':<32} {'STATUS':<8} {'DETAILS'}")
print("-" * 75)

for method, endpoint, payload in endpoints_to_test:
    url = f"{BASE_URL}{endpoint}"
    req = urllib.request.Request(url, method=method)
    if payload:
        data = json.dumps(payload).encode('utf-8')
        req.add_header('Content-Type', 'application/json')
    else:
        data = None
        
    try:
        with urllib.request.urlopen(req, data=data, timeout=5) as res:
            status = res.status
            body = res.read().decode('utf-8')
            try:
                parsed = json.loads(body)
                if isinstance(parsed, list):
                    detail = f"OK (Array count: {len(parsed)})"
                elif isinstance(parsed, dict):
                    keys = list(parsed.keys())[:4]
                    detail = f"OK (Keys: {keys})"
                else:
                    detail = "OK"
            except Exception:
                detail = f"OK (HTML/Text bytes: {len(body)})"
            print(f"{method:<6} {endpoint:<32} {status:<8} {detail}")
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='ignore')
        print(f"{method:<6} {endpoint:<32} {e.code:<8} HTTPError: {body[:60]}")
    except Exception as ex:
        print(f"{method:<6} {endpoint:<32} {'ERR':<8} {str(ex)[:60]}")
