"""
Path C Production Agent Voice Registry
Default Primary Voice: Marwadi (M1 Kavita Marwadi / M3 Shreeraj Marwadi)
"""

SELECTED_VOICES = {
    # ── MARWADI (PRIMARY DEFAULT) ─────────────────────────────────────────────
    "marwadi_female": {
        "id": "M1",
        "name": "Kavita (Respectful Marwadi Female)",
        "uuid": "56e35e2d-6eb6-4226-ab8b-9776515a7094",
        "lang": "mrw",
        "gender": "female"
    },
    "marwadi_male": {
        "id": "M3",
        "name": "Shreeraj (Respectful Marwadi Male)",
        "uuid": "c7be5dde-c1e6-4ebe-9096-ddc4b4edb1cc",
        "lang": "mrw",
        "gender": "male"
    },

    # ── HINDI ─────────────────────────────────────────────────────────────────
    "hi_female": {
        "id": "H1",
        "name": "Kavita (Native Hindi Customer Care)",
        "uuid": "56e35e2d-6eb6-4226-ab8b-9776515a7094",
        "lang": "hi",
        "gender": "female"
    },
    "hi_male": {
        "id": "H4",
        "name": "Ayush (Warm Hindi Male)",
        "uuid": "791d5162-d5eb-40f0-8189-f19db44611d8",
        "lang": "hi",
        "gender": "male"
    },

    # ── ENGLISH / HINGLISH ───────────────────────────────────────────────────
    "en_female": {
        "id": "E1",
        "name": "Arushi (Native Indian English / Hinglish)",
        "uuid": "95d51f79-c397-46f9-b49a-23763d3eaa2d",
        "lang": "en",
        "gender": "female"
    },
    "en_male": {
        "id": "E4",
        "name": "Kabir (Service Specialist Indian English)",
        "uuid": "cb9c954d-bcaa-43ed-82bf-aeb5e88a3cb5",
        "lang": "en",
        "gender": "male"
    }
}

def get_voice_uuid(lang: str = "mrw", gender: str = "female") -> str:
    """Returns Cartesia voice UUID. Defaults to M1 Kavita Marwadi."""
    lang_clean = lang.lower()
    gender_clean = gender.lower()

    if "en" in lang_clean or "hing" in lang_clean:
        key = f"en_{gender_clean}"
    elif "hi" in lang_clean:
        key = f"hi_{gender_clean}"
    else:
        key = f"marwadi_{gender_clean}"

    v_obj = SELECTED_VOICES.get(key, SELECTED_VOICES["marwadi_female"])
    return v_obj["uuid"]
