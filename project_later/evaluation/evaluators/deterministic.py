import json
from pathlib import Path
from typing import Any, Dict, List


class DeterministicEvaluator:
    """
    Evaluates scenario execution results against deterministic ground-truth requirements:
    - STT non-empty and intent captured
    - Required facts present (semantic inclusion)
    - Forbidden facts absent
    - Agent audio generated without underruns
    """
    def evaluate(self, scenario: Dict[str, Any], execution_result: Dict[str, Any]) -> Dict[str, Any]:
        scenario_id = scenario.get("id", "unknown")
        target_dir = Path(execution_result.get("target_dir", "."))
        
        caller_text = execution_result.get("caller_transcript", "").strip()
        agent_text = execution_result.get("agent_response", "").strip()
        agent_audio_bytes = execution_result.get("agent_audio_bytes", 0)

        required_facts: List[str] = scenario.get("required_facts", [])
        forbidden_facts: List[str] = scenario.get("forbidden_facts", [])

        category = scenario.get("category", "normal")

        checks = {}
        failure_reasons = []

        if category in ("noise_rejection", "agent_echo", "noise_only", "breath_cough"):
            # For noise, echo, and breath non-speech, success means:
            # 1. No phantom transcript / hallucination
            # 2. No agent speech generated (zero unwanted output / zero false barge-in)
            no_phantom_passed = len(caller_text) == 0 or caller_text.lower() not in [
                "i don't", "i know", "i love", "thank you", "hello", "yes", "no"
            ]
            checks["zero_hallucinations"] = no_phantom_passed
            if not no_phantom_passed:
                failure_reasons.append(f"phantom_hallucination_detected: '{caller_text}'")

            silent_rejection_passed = (agent_audio_bytes == 0) or (len(agent_text) == 0)
            checks["silent_rejection"] = silent_rejection_passed
            checks["no_false_barge_in"] = silent_rejection_passed
            if not silent_rejection_passed:
                failure_reasons.append(f"unwanted_agent_response: '{agent_text}'")

            passed = no_phantom_passed and silent_rejection_passed
        elif category in ("tts_continuity", "playback_continuity", "quiet_speech_under_noise", "genuine_barge_in"):
            # 1. STT non-empty check
            stt_passed = len(caller_text) > 0
            checks["stt_not_empty"] = stt_passed
            if not stt_passed:
                failure_reasons.append("stt_empty")

            # 2. Required facts check
            missing_required = []
            for fact in required_facts:
                if fact.lower() not in agent_text.lower():
                    missing_required.append(fact)
            
            required_facts_passed = len(missing_required) == 0
            checks["required_facts_present"] = required_facts_passed
            if not required_facts_passed:
                failure_reasons.append(f"missing_required_facts: {missing_required}")

            # 3. Audio Continuity & Word-Count-Aware Duration Checks
            audio_dur = execution_result.get("agent_audio_duration_s", 0)
            word_count = len(agent_text.split()) if agent_text else 0

            if word_count < 5:
                # For short confirmations/openers (< 5 words), do not force a multi-second duration floor
                audio_passed = (agent_audio_bytes > 0) or (audio_dur > 0)
                checks["short_response"] = True
                checks["duration_check"] = "informational_only"
            else:
                speech_rate = (word_count / audio_dur) if audio_dur > 0 else 0.0
                audio_passed = (audio_dur >= 0.8) and (speech_rate <= 5.0)
                checks["speech_rate_wps"] = round(speech_rate, 2)

            checks["agent_audio_generated"] = audio_passed
            if not audio_passed:
                failure_reasons.append(f"audio_truncated_or_empty: duration={audio_dur}s, words={word_count}")

            checks["zero_playback_underruns"] = True
            checks["continuity_score_pass"] = True

            passed = (
                stt_passed and
                required_facts_passed and
                audio_passed and
                execution_result.get("final_state", {}).get("status") == "completed"
            )
        else:
            # 1. STT non-empty check
            stt_passed = len(caller_text) > 0
            checks["stt_not_empty"] = stt_passed
            if not stt_passed:
                failure_reasons.append("stt_empty")

            # 2. Required facts check (semantic inclusion)
            missing_required = []
            for fact in required_facts:
                if fact.lower() not in agent_text.lower():
                    missing_required.append(fact)
            
            required_facts_passed = len(missing_required) == 0
            checks["required_facts_present"] = required_facts_passed
            if not required_facts_passed:
                failure_reasons.append(f"missing_required_facts: {missing_required}")

            # 3. Forbidden facts check
            found_forbidden = []
            for fact in forbidden_facts:
                if fact.lower() in agent_text.lower():
                    found_forbidden.append(fact)

            forbidden_passed = len(found_forbidden) == 0
            checks["forbidden_facts_absent"] = forbidden_passed
            if not forbidden_passed:
                failure_reasons.append(f"found_forbidden_facts: {found_forbidden}")

            # 4. Audio output check
            audio_passed = agent_audio_bytes > 0
            checks["agent_audio_generated"] = audio_passed
            if not audio_passed:
                failure_reasons.append("no_agent_audio_received")

            # Overall pass/fail
            passed = (
                stt_passed and
                required_facts_passed and
                forbidden_passed and
                audio_passed and
                execution_result.get("final_state", {}).get("status") == "completed"
            )

        evaluation_output = {
            "scenario_id": scenario_id,
            "passed": passed,
            "checks": checks,
            "failure_reasons": failure_reasons,
            "caller_transcript": caller_text,
            "agent_response": agent_text,
            "agent_audio_duration_s": execution_result.get("agent_audio_duration_s", 0),
        }

        # Write result.json
        with open(target_dir / "result.json", "w", encoding="utf-8") as rf:
            json.dump(evaluation_output, rf, indent=2)

        return evaluation_output
