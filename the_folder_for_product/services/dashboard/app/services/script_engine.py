import json
from typing import Dict, Any, Optional, List, Tuple

DEFAULT_SCRIPT_FLOW = {
    "version": 1,
    "steps": [
        {
            "id": "welcome",
            "type": "say",
            "text": ""
        }
    ]
}

class ScriptEngine:
    def __init__(self, script_data: Optional[Any] = None):
        parsed = self._parse_script_input(script_data)
        if parsed and isinstance(parsed, dict) and "steps" in parsed and parsed["steps"]:
            self.flow = parsed
        else:
            clean_text = self._sanitize_text(script_data)
            self.flow = {
                "version": 1,
                "steps": [
                    {"id": "welcome", "type": "say", "text": clean_text}
                ]
            }

        self.steps_by_id = {s["id"]: s for s in self.flow.get("steps", []) if isinstance(s, dict) and "id" in s}

    def _parse_script_input(self, data: Any) -> Optional[Dict[str, Any]]:
        if not data:
            return DEFAULT_SCRIPT_FLOW
        
        current = data
        for _ in range(3):
            if isinstance(current, str):
                s = current.strip()
                if (s.startswith("{") and s.endswith("}")) or (s.startswith("[") and s.endswith("]")):
                    try:
                        current = json.loads(s)
                    except Exception:
                        break
                else:
                    break

        if isinstance(current, dict):
            if "steps" in current and isinstance(current["steps"], list):
                return current
            if "script_content" in current and current["script_content"]:
                return self._parse_script_input(current["script_content"])

        return None

    def _sanitize_text(self, raw_input: Any) -> str:
        if not raw_input:
            return ""
        
        if isinstance(raw_input, dict):
            if "text" in raw_input and isinstance(raw_input["text"], str):
                return raw_input["text"]
            if "script_content" in raw_input:
                return self._sanitize_text(raw_input["script_content"])
            return ""

        text_str = str(raw_input).strip()
        if text_str.startswith("{") and "}" in text_str:
            try:
                parsed = json.loads(text_str)
                if isinstance(parsed, dict):
                    if "script_content" in parsed:
                        return self._sanitize_text(parsed["script_content"])
                    if "text" in parsed:
                        return str(parsed["text"])
            except Exception:
                pass
            return ""

        return text_str

    def classify_intent(self, text: str) -> str:
        t = text.lower().strip()
        if any(w in t for w in ["haan", "yes", "zaroor", "aaoonga", "participate", "aaunga", "sahi", "sure", "interested"]):
            return "INTERESTED"
        elif any(w in t for w in ["nahi", "nahin", "no", "mat karo", "not interested", "fursat nahi"]):
            return "NOT_INTERESTED"
        elif any(w in t for w in ["baad mein", "later", "call back", "shaam", "phir", "bada"]):
            return "CALLBACK"
        elif any(w in t for w in ["manager", "human", "talk", "executive", "operator", "bande"]):
            return "HUMAN_HANDOFF"
        return "INTERESTED"  # Default optimistic fallback

    def execute_flow(self, user_responses: List[str]) -> Tuple[List[Dict[str, str]], str, str]:
        """
        Executes step state machine given user spoken inputs.
        Returns: (transcript_turns, final_outcome, final_intent)
        """
        transcript = []
        current_step_id = self.flow.get("steps", [{}])[0].get("id", "welcome")
        response_idx = 0
        final_outcome = "COMPLETED"
        final_intent = "INTERESTED"

        visited = set()
        while current_step_id and current_step_id not in visited:
            visited.add(current_step_id)
            step = self.steps_by_id.get(current_step_id)
            if not step:
                break

            step_type = step.get("type")

            if step_type == "say":
                transcript.append({"role": "assistant", "content": step.get("text", "")})
                # Check next step sequentially if not intent branch
                curr_idx = [i for i, s in enumerate(self.flow.get("steps", [])) if s["id"] == current_step_id][0]
                if curr_idx + 1 < len(self.flow.get("steps", [])):
                    current_step_id = self.flow["steps"][curr_idx + 1]["id"]
                else:
                    break

            elif step_type == "ask":
                transcript.append({"role": "assistant", "content": step.get("text", "")})
                # Consume user spoken response
                resp_text = user_responses[response_idx] if response_idx < len(user_responses) else "Haan"
                response_idx += 1
                transcript.append({"role": "user", "content": resp_text})

                # Move to next step (typically intent step)
                curr_idx = [i for i, s in enumerate(self.flow.get("steps", [])) if s["id"] == current_step_id][0]
                if curr_idx + 1 < len(self.flow.get("steps", [])):
                    current_step_id = self.flow["steps"][curr_idx + 1]["id"]
                else:
                    break

            elif step_type == "intent":
                last_user_input = transcript[-1]["content"] if transcript and transcript[-1]["role"] == "user" else "haan"
                detected_intent = self.classify_intent(last_user_input)
                final_intent = detected_intent

                branches = step.get("branches", {})
                next_step_id = branches.get(detected_intent, "confirmation")
                current_step_id = next_step_id

                if detected_intent == "HUMAN_HANDOFF":
                    final_outcome = "HUMAN_HANDOFF"
                elif detected_intent == "CALLBACK":
                    final_outcome = "CALLBACK"
                elif detected_intent == "NOT_INTERESTED":
                    final_outcome = "NOT_INTERESTED"
                else:
                    final_outcome = "INTERESTED"

        return transcript, final_outcome, final_intent
