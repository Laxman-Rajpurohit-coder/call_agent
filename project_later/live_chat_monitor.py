import os
import sys
import time
import re

sys.stdout.reconfigure(encoding='utf-8')

# ANSI color codes
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
MAGENTA = "\033[95m"
BLUE = "\033[94m"
GRAY = "\033[90m"
BOLD = "\033[1m"
RESET = "\033[0m"

LOG_FILE = r"C:\daily_works\superfone_call\call_gateway.log"

def banner():
    print(f"\n{BOLD}{CYAN}==============================================================={RESET}")
    print(f"{BOLD}{GREEN}        🎙️  SUPERFONE AI — LIVE CALL CHAT MONITOR  🤖          {RESET}")
    print(f"{BOLD}{CYAN}==============================================================={RESET}")
    print(f"{GRAY}Tailing live audio socket events in real-time... Press Ctrl+C to exit.{RESET}\n")

def process_line(line: str):
    ts_match = re.match(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3})", line)
    timestamp = ts_match.group(1).split(" ")[1] if ts_match else ""

    if "Call session started with call_id=" in line:
        cid_match = re.search(r"call_id=([a-f0-9\-]+)", line)
        cid = cid_match.group(1)[:8] if cid_match else "unknown"
        print(f"\n{BOLD}{BLUE}📞 [Call Connected: {cid}] — {timestamp}{RESET}")
        print(f"{GRAY}{'─' * 55}{RESET}")

    elif "AI_RESPONSE" in line:
        m = re.search(r"text='([^']*)'", line)
        if m:
            text = m.group(1)
            print(f"{BOLD}{GREEN}🤖 AI Assistant:{RESET} {text}")

    elif "USER_UTTERANCE" in line:
        m = re.search(r"text='([^']*)'", line)
        if m:
            text = m.group(1)
            if text.strip():
                print(f"\n{BOLD}{CYAN}👤 Caller (You):{RESET} {BOLD}{text}{RESET}")

    elif "BARGE_IN_TRIGGERED" in line:
        m = re.search(r"reason='([^']*)'", line)
        reason = m.group(1) if m else "caller spoke"
        print(f"{BOLD}{YELLOW}⚡ [Interruption / Barge-in: {reason}]{RESET}")

    elif "DTMF 0 detected" in line:
        print(f"{BOLD}{MAGENTA}🔀 [Human Agent Transfer Requested (DTMF 0)]{RESET}")

    elif "Call session finished" in line or "Call disconnected" in line:
        print(f"{GRAY}{'─' * 55}{RESET}")
        print(f"{BOLD}{GRAY}📴 [Call Ended] — {timestamp}{RESET}\n")

def main():
    os.system("color")
    banner()

    # Ensure log file exists
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            f.write("")

    with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
        # Seek to end of file to tail live events
        f.seek(0, os.SEEK_END)
        while True:
            line = f.readline()
            if not line:
                time.sleep(0.05)
                continue
            process_line(line.strip())

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{GRAY}Live monitor stopped.{RESET}")
