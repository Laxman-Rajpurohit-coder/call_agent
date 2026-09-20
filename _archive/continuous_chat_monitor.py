import os
import sys
import time
import re
import socket
import logging

# UTF-8 stdout configuration
try:
    sys.stdout.reconfigure(encoding='utf-8', line_buffering=True, errors='replace')
except Exception:
    pass

LOG_FILE = r"C:\daily_works\superfone_call\call_gateway.log"
MONITOR_LOG = r"C:\daily_works\superfone_call\chat_monitor.log"
PORTS_TO_CHECK = [9090, 9092, 9093, 9094, 9095, 9096]

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [CHAT_MONITOR] - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(MONITOR_LOG, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("chat_monitor")

def check_port_health():
    """Verify all 6 core microservice ports are listening without collisions."""
    healthy = True
    for port in PORTS_TO_CHECK:
        try:
            with socket.create_connection(('127.0.0.1', port), timeout=2.0):
                pass
        except Exception as e:
            logger.warning(f"Port {port} health check failed or not accepting connections: {e}")
            healthy = False
    return healthy

class CallSessionMonitor:
    def __init__(self):
        self.active_sessions = {}  # call_id -> dict of session state
        self.total_calls_checked = 0
        self.interference_alerts = 0
        self.error_alerts = 0

    def parse_line(self, line: str):
        # Detect new call session
        if "Call session started with call_id=" in line:
            m = re.search(r"call_id=([a-f0-9\-]+)", line)
            if m:
                cid = m.group(1)
                if cid in self.active_sessions:
                    logger.warning(f"INTERFERENCE WARNING: Duplicate call_id detected: {cid}")
                    self.interference_alerts += 1
                else:
                    self.active_sessions[cid] = {
                        "start_time": time.time(),
                        "utterances": 0,
                        "ai_responses": 0,
                        "barge_ins": 0,
                        "errors": 0
                    }
                    self.total_calls_checked += 1
                    logger.info(f"New call session initialized: {cid} | Active Concurrent: {len(self.active_sessions)}")

        # Detect User Utterance
        elif "USER_UTTERANCE" in line:
            m = re.search(r"call_id=([a-f0-9\-]+)", line)
            cid = m.group(1) if m else None
            if cid and cid in self.active_sessions:
                self.active_sessions[cid]["utterances"] += 1
            elif not cid:
                # Check for unassigned utterance (interfering or unassigned state)
                logger.warning(f"POTENTIAL INTERFERENCE: User utterance logged without explicit call_id mapping!")
                self.interference_alerts += 1

        # Detect AI Response
        elif "AI_RESPONSE" in line:
            m = re.search(r"call_id=([a-f0-9\-]+)", line)
            cid = m.group(1) if m else None
            if cid and cid in self.active_sessions:
                self.active_sessions[cid]["ai_responses"] += 1

        # Detect Barge-In
        elif "BARGE_IN_TRIGGERED" in line:
            m = re.search(r"call_id=([a-f0-9\-]+)", line)
            cid = m.group(1) if m else None
            if cid and cid in self.active_sessions:
                self.active_sessions[cid]["barge_ins"] += 1
                logger.info(f"Barge-in handled cleanly for call_id={cid}")

        # Detect Session Finished
        elif "Call session finished" in line or "Call disconnected" in line:
            m = re.search(r"call_id=([a-f0-9\-]+)", line)
            cid = m.group(1) if m else None
            if cid and cid in self.active_sessions:
                stats = self.active_sessions.pop(cid)
                dur = round(time.time() - stats["start_time"], 2)
                logger.info(f"Call session closed cleanly: {cid} | Duration: {dur}s | Utterances: {stats['utterances']} | AI Responses: {stats['ai_responses']}")
            elif cid:
                logger.info(f"Call session closed: {cid}")

        # Detect Errors or Exceptions
        elif "ERROR" in line or "Exception" in line or "Traceback" in line:
            logger.error(f"ERROR DETECTED IN LOG: {line[:120]}")
            self.error_alerts += 1

def main():
    logger.info("Starting Continuous Superfone Chat & Call Session Interference Monitor...")
    monitor = CallSessionMonitor()

    # Initial port health check
    check_port_health()

    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            f.write("")

    last_health_check = time.time()

    with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
        f.seek(0, os.SEEK_END)
        while True:
            line = f.readline()
            if not line:
                time.sleep(0.1)
                if time.time() - last_health_check > 30:
                    check_port_health()
                    last_health_check = time.time()
                continue

            monitor.parse_line(line.strip())

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Chat monitor stopped cleanly.")
