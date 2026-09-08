import re
from typing import Any, Dict, List, Optional
import httpx


def levenshtein_distance(ref_tokens: List[str], hyp_tokens: List[str]) -> int:
    """Computes Levenshtein edit distance between token sequences."""
    n = len(ref_tokens)
    m = len(hyp_tokens)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        dp[i][0] = i
    for j in range(m + 1):
        dp[0][j] = j

    for i in range(1, n + 1):
        for j in range(1, m + 1):
            if ref_tokens[i - 1] == hyp_tokens[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]
            else:
                dp[i][j] = 1 + min(dp[i - 1][j], dp[i][j - 1], dp[i - 1][j - 1])

    return dp[n][m]


def normalize_text(text: str) -> str:
    """Normalizes text for linguistic scoring."""
    t = text.lower()
    t = re.sub(r"[^\w\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


class PronunciationAndEntityEvaluator:
    """
    Evaluates TTS pronunciation accuracy and critical entity preservation
    by sending rendered audio through an independent ASR transcription pass.
    """

    def __init__(self, stt_url: str = "http://127.0.0.1:9094/stt"):
        self.stt_url = stt_url

    async def evaluate_pronunciation(
        self,
        pcm_bytes: bytes,
        reference_text: str,
        expected_entities: Optional[List[str]] = None,
        language: str = "en",
    ) -> Dict[str, Any]:
        expected_entities = expected_entities or []
        asr_text = ""
        asr_conf = 0.0

        # Run independent ASR transcription on the generated audio
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(self.stt_url, content=pcm_bytes)
                if resp.status_code == 200:
                    data = resp.json()
                    asr_text = data.get("text", "").strip()
                    asr_conf = float(data.get("confidence", 0.0))
        except Exception as e:
            return {
                "error": f"ASR transcription failed: {e}",
                "wer": 1.0,
                "cer": 1.0,
                "passed": False,
            }

        # 1. Word Error Rate (WER) & Character Error Rate (CER)
        ref_norm = normalize_text(reference_text)
        hyp_norm = normalize_text(asr_text)

        ref_words = ref_norm.split()
        hyp_words = hyp_norm.split()

        ref_chars = list(ref_norm.replace(" ", ""))
        hyp_chars = list(hyp_norm.replace(" ", ""))

        if len(ref_words) > 0:
            word_dist = levenshtein_distance(ref_words, hyp_words)
            wer = round(word_dist / float(len(ref_words)), 3)
        else:
            wer = 0.0 if len(hyp_words) == 0 else 1.0

        if len(ref_chars) > 0:
            char_dist = levenshtein_distance(ref_chars, hyp_chars)
            cer = round(char_dist / float(len(ref_chars)), 3)
        else:
            cer = 0.0 if len(hyp_chars) == 0 else 1.0

        # 2. Critical Entity Preservation
        missing_entities = []
        entity_matches = {}
        for ent in expected_entities:
            ent_norm = normalize_text(ent)
            matched = ent_norm in hyp_norm
            entity_matches[ent] = matched
            if not matched:
                missing_entities.append(ent)

        entities_passed = len(missing_entities) == 0

        # Pronunciation Pass Criteria
        # For Hindi/Hinglish, allow higher phoneme tolerance than clean English
        wer_ceiling = 0.35 if language in ("hi", "hi-en") else 0.20
        passed = (wer <= wer_ceiling) and entities_passed

        failures = []
        if wer > wer_ceiling:
            failures.append(f"high_wer: {wer} > {wer_ceiling}")
        if not entities_passed:
            failures.append(f"missing_critical_entities: {missing_entities}")

        return {
            "reference_text": reference_text,
            "asr_transcript": asr_text,
            "asr_confidence": asr_conf,
            "wer": wer,
            "cer": cer,
            "entity_matches": entity_matches,
            "missing_entities": missing_entities,
            "entities_passed": entities_passed,
            "passed": passed,
            "failures": failures,
        }
