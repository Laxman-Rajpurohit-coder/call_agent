from typing import Dict, List, Any

VOICE_CATALOG = {
    "languages": [
        {
            "code": "hi-IN",
            "name": "Hindi",
            "accents": ["Indian"],
            "stt_primary": "deepgram",
            "llm_primary": "groq",
            "tts_primary": "cartesia",
            "default_voice": "hindi_female_01"
        },
        {
            "code": "hinglish-IN",
            "name": "Hinglish",
            "accents": ["Indian"],
            "stt_primary": "deepgram",
            "llm_primary": "groq",
            "tts_primary": "cartesia",
            "default_voice": "hinglish_female_01"
        },
        {
            "code": "en-IN",
            "name": "English (India)",
            "accents": ["Indian"],
            "stt_primary": "deepgram",
            "llm_primary": "groq",
            "tts_primary": "cartesia",
            "default_voice": "en_in_female_01"
        },
        {
            "code": "en-US",
            "name": "English (US)",
            "accents": ["US"],
            "stt_primary": "deepgram",
            "llm_primary": "groq",
            "tts_primary": "cartesia",
            "default_voice": "en_us_female_01"
        },
        {
            "code": "en-UK",
            "name": "English (UK)",
            "accents": ["UK"],
            "stt_primary": "deepgram",
            "llm_primary": "groq",
            "tts_primary": "cartesia",
            "default_voice": "en_uk_female_01"
        },
        {
            "code": "en-AU",
            "name": "English (Australia)",
            "accents": ["Australian"],
            "stt_primary": "deepgram",
            "llm_primary": "groq",
            "tts_primary": "cartesia",
            "default_voice": "en_au_female_01"
        },
        {
            "code": "bn-IN",
            "name": "Bengali",
            "accents": ["Indian"],
            "stt_primary": "deepgram",
            "llm_primary": "groq",
            "tts_primary": "cartesia",
            "default_voice": "bn_female_01"
        },
        {
            "code": "ta-IN",
            "name": "Tamil",
            "accents": ["Indian"],
            "stt_primary": "deepgram",
            "llm_primary": "groq",
            "tts_primary": "cartesia",
            "default_voice": "ta_female_01"
        },
        {
            "code": "te-IN",
            "name": "Telugu",
            "accents": ["Indian"],
            "stt_primary": "deepgram",
            "llm_primary": "groq",
            "tts_primary": "cartesia",
            "default_voice": "te_female_01"
        },
        {
            "code": "mr-IN",
            "name": "Marathi",
            "accents": ["Indian"],
            "stt_primary": "deepgram",
            "llm_primary": "groq",
            "tts_primary": "cartesia",
            "default_voice": "mr_female_01"
        },
        {
            "code": "gu-IN",
            "name": "Gujarati",
            "accents": ["Indian"],
            "stt_primary": "deepgram",
            "llm_primary": "groq",
            "tts_primary": "cartesia",
            "default_voice": "gu_female_01"
        },
        {
            "code": "kn-IN",
            "name": "Kannada",
            "accents": ["Indian"],
            "stt_primary": "deepgram",
            "llm_primary": "groq",
            "tts_primary": "cartesia",
            "default_voice": "kn_female_01"
        },
        {
            "code": "ml-IN",
            "name": "Malayalam",
            "accents": ["Indian"],
            "stt_primary": "deepgram",
            "llm_primary": "groq",
            "tts_primary": "cartesia",
            "default_voice": "ml_female_01"
        },
        {
            "code": "pa-IN",
            "name": "Punjabi",
            "accents": ["Indian"],
            "stt_primary": "deepgram",
            "llm_primary": "groq",
            "tts_primary": "cartesia",
            "default_voice": "pa_female_01"
        },
        {
            "code": "ur-IN",
            "name": "Urdu",
            "accents": ["Indian"],
            "stt_primary": "deepgram",
            "llm_primary": "groq",
            "tts_primary": "cartesia",
            "default_voice": "ur_female_01"
        }
    ]
}

class VoiceCatalogManager:
    def get_catalog(self) -> Dict[str, Any]:
        return VOICE_CATALOG

    def get_language_config(self, lang_code: str) -> Dict[str, Any]:
        for lang in VOICE_CATALOG["languages"]:
            if lang["code"] == lang_code:
                return lang
        return VOICE_CATALOG["languages"][0] # Default Hindi

voice_catalog_manager = VoiceCatalogManager()
