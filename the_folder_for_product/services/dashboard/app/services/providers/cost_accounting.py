import os

class CostAccounting:
    def __init__(self):
        # Default rates (configurable via environment)
        self.deepgram_stt_cost_per_min = float(os.environ.get("DEEPGRAM_STT_COST_PER_MIN", "0.0043"))
        self.groq_llm_cost_per_1m_tokens = float(os.environ.get("GROQ_LLM_COST_PER_1M_TOKENS", "0.05"))
        self.cartesia_tts_cost_per_1k_chars = float(os.environ.get("CARTESIA_TTS_COST_PER_1K_CHARS", "0.015"))

    def calculate_stt_cost(self, audio_seconds: float) -> float:
        minutes = audio_seconds / 60.0
        return round(minutes * self.deepgram_stt_cost_per_min, 6)

    def calculate_llm_cost(self, input_tokens: int, output_tokens: int) -> float:
        total_tokens = input_tokens + output_tokens
        return round((total_tokens / 1_000_000.0) * self.groq_llm_cost_per_1m_tokens, 6)

    def calculate_tts_cost(self, char_count: int) -> float:
        return round((char_count / 1_000.0) * self.cartesia_tts_cost_per_1k_chars, 6)

cost_accounting = CostAccounting()
