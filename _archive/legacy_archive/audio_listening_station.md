# 🎧 Voice Evaluation Listening Station & Quality Calibration Console

This console provides a structured environment for manual quality auditing and subjective calibration across the three distinct audio pipeline stages:

1. **Stage 1: Raw Piper Output** (`tts_raw.wav` @ 22,050 Hz high-fidelity synthesis)
2. **Stage 2: Telephony-Resampled Output** (`tts_telephony.wav` @ 8,000 Hz 16-bit mono PCM)
3. **Stage 3: Live AudioSocket Playback Capture** (`audio_agent.wav` @ 8,000 Hz actual streamed call response)

---

## 1. Live Telephony AudioSocket Pipeline Samples

These recordings represent the actual agent voice streaming over the real-time telephony TCP pipeline (**VAD $\rightarrow$ Whisper STT $\rightarrow$ Qwen LLM $\rightarrow$ Piper TTS $\rightarrow$ AudioSocket stream**).

---

### 📍 Sample 1: Foundation Physical Address (`foundation_address_001`)

**Spoken Text:**
> *"The foundation is located in Gandhi Pura, Balotra, Barmer District, Rajasthan."*

- **Language:** English (`en`) | **Voice Model:** `en_US-lessac-medium`
- **Stage 3 (Live AudioSocket Playback Capture - 8,000 Hz PCM16):**

<audio controls preload="metadata" style="width: 100%; margin: 8px 0;">
  <source src="evaluation/artifacts/run-1787292723/foundation_address_001/audio_agent.wav" type="audio/wav">
  Your browser does not support audio playback.
</audio>

- **Automated Metadata:** Duration: `5.12s` | WER: `0.00` | Speech Rate: `2.34 WPS` | F0 Std: `38.4 Hz` | Clipping: `0` | Unexpected Gaps: `0`
- **Entities Preserved:** `Gandhi Pura`, `Balotra`, `Barmer`, `Rajasthan`

**Defect Checklist:**
- [ ] C1: Click / pop impulse
- [ ] C2: Abrupt chunk boundary
- [ ] C3: Repeated word or phrase
- [ ] C4: Missing word or syllable
- [ ] C5: Mid-word cutoff
- [ ] C6: Unnatural internal silence (>450ms)
- [ ] C7: Robotic / flat monotone delivery
- [ ] C8: Incorrect name/address pronunciation
- [ ] C9: Volume jump between chunks
- [ ] C10: Sentence-final intonation defect
- [ ] C11: Interrupted resumption flaw
- [ ] C12: Overlap with caller speech

---

### 👥 Sample 2: Foundation Directors (`foundation_directors_001`)

**Spoken Text:**
> *"The directors running the foundation are Sanjay Gahlot and Paras Mal Gahlot."*

- **Language:** English (`en`) | **Voice Model:** `en_US-lessac-medium`
- **Stage 3 (Live AudioSocket Playback Capture - 8,000 Hz PCM16):**

<audio controls preload="metadata" style="width: 100%; margin: 8px 0;">
  <source src="evaluation/artifacts/run-1787292723/foundation_directors_001/audio_agent.wav" type="audio/wav">
  Your browser does not support audio playback.
</audio>

- **Automated Metadata:** Duration: `5.20s` | WER: `0.00` | Speech Rate: `2.31 WPS` | F0 Std: `41.2 Hz` | Clipping: `0`
- **Entities Preserved:** `Sanjay Gahlot`, `Paras Mal Gahlot`

**Defect Checklist:**
- [ ] C1: Click / pop impulse
- [ ] C2: Abrupt chunk boundary
- [ ] C5: Mid-word cutoff
- [ ] C7: Robotic / flat delivery
- [ ] C8: Incorrect name pronunciation

---

### ⏰ Sample 3: Opening Hours (`opening_hours_001`)

**Spoken Text:**
> *"Our office hours are from 9:00 AM to 5:00 PM, Monday through Saturday."*

- **Language:** English (`en`) | **Voice Model:** `en_US-lessac-medium`
- **Stage 3 (Live AudioSocket Playback Capture - 8,000 Hz PCM16):**

<audio controls preload="metadata" style="width: 100%; margin: 8px 0;">
  <source src="evaluation/artifacts/run-1787292723/opening_hours_001/audio_agent.wav" type="audio/wav">
  Your browser does not support audio playback.
</audio>

- **Automated Metadata:** Duration: `4.80s` | WER: `0.00` | Speech Rate: `2.71 WPS` | Clipping: `0`
- **Entities Preserved:** `9:00 AM`, `5:00 PM`, `Monday`, `Saturday`

**Defect Checklist:**
- [ ] C1: Click / pop impulse
- [ ] C6: Unnatural internal silence
- [ ] C7: Robotic monotone
- [ ] C10: Sentence-final intonation defect

---

### ✋ Sample 4: Barge-In Interruption Response (`barge_in_director_001`)

**Scenario:** Caller interrupted the agent at 1000 ms during playback. The agent immediately halted playback, processed the interruption query, and streamed the new answer.

**Spoken Text:**
> *"The directors running the foundation are Sanjay Gahlot and Paras Mal Gahlot."*

- **Stage 3 (Live AudioSocket Playback Capture post-interruption - 8,000 Hz PCM16):**

<audio controls preload="metadata" style="width: 100%; margin: 8px 0;">
  <source src="evaluation/artifacts/run-1787293028/barge_in_director_001/audio_agent.wav" type="audio/wav">
  Your browser does not support audio playback.
</audio>

- **Automated Metadata:** Barge-In Stop Latency: `<350 ms` | Queue Underruns: `0` | WER: `0.00`

**Defect Checklist:**
- [ ] C1: Click / pop on playback stop or restart
- [ ] C11: Resumes previous sentence instead of answering interruption
- [ ] C12: Audio overlap with caller speech

---

### 🤫 Sample 5: Quiet Caller Handling (`quiet_hello_001`)

**Scenario:** Caller spoke quietly (amplitude peak ~600). Energy gate accepted the audio and the agent answered cleanly.

**Spoken Text:**
> *"Good morning! How can I assist you today?"*

- **Stage 3 (Live AudioSocket Playback Capture - 8,000 Hz PCM16):**

<audio controls preload="metadata" style="width: 100%; margin: 8px 0;">
  <source src="evaluation/artifacts/run-1787292880/quiet_hello_001/audio_agent.wav" type="audio/wav">
  Your browser does not support audio playback.
</audio>

- **Automated Metadata:** Input Peak: `612` | Gated: `Accepted` | Agent Duration: `2.40s` | Speech Rate: `2.92 WPS`

---

## 2. TTS Voice Fluency & Multilingual Stage Comparisons (100-Case Suite)

These samples allow side-by-side comparison across the **Raw Synthesis (22,050 Hz)** and **Telephony Conversion (8,000 Hz)** stages.

---

### 🏷️ Sample 6: Organization Entity Pronunciation (`num_ent_001`)

**Spoken Text:**
> *"The foundation is named Malisaini Samaj Seva Foundation."*

- **Voice Model:** `en_US-lessac-medium` | **Language:** English (`en`)

**Stage 1: Raw Piper Synthesis (22,050 Hz High-Fidelity):**
<audio controls preload="metadata" style="width: 100%; margin: 6px 0;">
  <source src="evaluation/tts/generated/num_ent_001/tts_raw.wav" type="audio/wav">
  Your browser does not support audio playback.
</audio>

**Stage 2: Telephony-Resampled Output (8,000 Hz PCM16):**
<audio controls preload="metadata" style="width: 100%; margin: 6px 0;">
  <source src="evaluation/tts/generated/num_ent_001/tts_telephony.wav" type="audio/wav">
  Your browser does not support audio playback.
</audio>

- **Automated Metadata:** Duration: `3.22s` | WER: `0.00` | Speech Rate: `2.48 WPS` | Clipping: `0`
- **Entity Accuracy:** `Malisaini Samaj Seva Foundation`: 100% matched

**Defect Checklist:**
- [ ] C1: Click / pop impulse
- [ ] C8: Mispronounced Indian proper noun ("Malisaini")
- [ ] C7: Robotic delivery

---

### 📖 Sample 7: Long Multi-Sentence Cadence (`eng_long_001`)

**Spoken Text:**
> *"The foundation is dedicated to improving community wellbeing across Rajasthan. We focus on educational scholarships for underprivileged children, essential medical aid for families, and vocational training for young adults."*

- **Voice Model:** `en_US-lessac-medium` | **Language:** English (`en`)

**Stage 1: Raw Piper Synthesis (22,050 Hz High-Fidelity):**
<audio controls preload="metadata" style="width: 100%; margin: 6px 0;">
  <source src="evaluation/tts/generated/eng_long_001/tts_raw.wav" type="audio/wav">
  Your browser does not support audio playback.
</audio>

**Stage 2: Telephony-Resampled Output (8,000 Hz PCM16):**
<audio controls preload="metadata" style="width: 100%; margin: 6px 0;">
  <source src="evaluation/tts/generated/eng_long_001/tts_telephony.wav" type="audio/wav">
  Your browser does not support audio playback.
</audio>

- **Automated Metadata:** Duration: `13.1s` | WER: `0.069` | Speech Rate: `2.29 WPS` | F0 Std: `41.2 Hz` | RMS: `-17.6 dBFS` | Unexpected Gaps: `1`

**Defect Checklist:**
- [ ] C2: Abrupt waveform discontinuity between clauses
- [ ] C6: Unnatural silence / long gap (>450ms)
- [ ] C7: Monotone pitch drift
- [ ] C9: Volume jump across sentences

---

### 🇮🇳 Sample 8: Hindi Welcome Greeting (`hin_care_002`)

**Spoken Text (Devanagari):**
> *"मालीसैनी समाज सेवा फाउंडेशन में आपका स्वागत है।"*

- **Voice Model:** `hi_IN-pratham-medium` | **Language:** Hindi (`hi`)

**Stage 1: Raw Piper Synthesis (22,050 Hz High-Fidelity):**
<audio controls preload="metadata" style="width: 100%; margin: 6px 0;">
  <source src="evaluation/tts/generated/hin_care_002/tts_raw.wav" type="audio/wav">
  Your browser does not support audio playback.
</audio>

**Stage 2: Telephony-Resampled Output (8,000 Hz PCM16):**
<audio controls preload="metadata" style="width: 100%; margin: 6px 0;">
  <source src="evaluation/tts/generated/hin_care_002/tts_telephony.wav" type="audio/wav">
  Your browser does not support audio playback.
</audio>

- **Automated Metadata:** Duration: `3.05s` | Speech Rate: `2.62 WPS` | F0 Mean: `158.4 Hz` | F0 Std: `32.1 Hz`

**Defect Checklist:**
- [ ] C8: Incorrect Hindi pronunciation or stress
- [ ] C7: Flat robotic tone
- [ ] C1: Click or clipping artifact

---

### 🔀 Sample 9: Hinglish Office Description (`hng_care_002`)

**Spoken Text:**
> *"Foundation ka office Gandhi Pura, Balotra me situated hai."*

- **Voice Model:** `en_US-lessac-medium` | **Language:** Hinglish (`hi-en`)

**Stage 1: Raw Piper Synthesis (22,050 Hz High-Fidelity):**
<audio controls preload="metadata" style="width: 100%; margin: 6px 0;">
  <source src="evaluation/tts/generated/hng_care_002/tts_raw.wav" type="audio/wav">
  Your browser does not support audio playback.
</audio>

**Stage 2: Telephony-Resampled Output (8,000 Hz PCM16):**
<audio controls preload="metadata" style="width: 100%; margin: 6px 0;">
  <source src="evaluation/tts/generated/hng_care_002/tts_telephony.wav" type="audio/wav">
  Your browser does not support audio playback.
</audio>

- **Automated Metadata:** Duration: `3.64s` | Speech Rate: `2.47 WPS` | CER: `0.04` | Entities: `Gandhi Pura`, `Balotra` matched

**Defect Checklist:**
- [ ] C8: Code-switching pronunciation unnatural
- [ ] C7: Robotic tone on loan words
