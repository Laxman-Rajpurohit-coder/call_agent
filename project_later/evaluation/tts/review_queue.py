import glob
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


def build_review_queue(report_json_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Classifies TTS evaluation results into 3 tiers:
      - PASS: Automated metrics healthy. No listening needed.
      - REVIEW: Ambiguous / borderline items (e.g., punctuation pause >450ms, number formatting).
      - FAIL: Hard defects (audio clipping >0, corrupted audio, missing critical entities).
    Generates a focused, lightweight Review Station containing ONLY review/fail items.
    """
    if not report_json_path:
        reports = glob.glob("evaluation/reports/tts/*.json")
        if not reports:
            print("No TTS evaluation reports found in evaluation/reports/tts/")
            return {}
        report_json_path = sorted(reports)[-1]

    path = Path(report_json_path)
    with open(path, "r", encoding="utf-8") as f:
        report_data = json.load(f)

    run_id = report_data.get("run_id", "unknown_run")
    results: List[Dict[str, Any]] = report_data.get("results", [])

    pass_cases = []
    review_cases = []
    fail_cases = []

    for r in results:
        case_id = r.get("case_id", "")
        text = r.get("text", "")
        lang = r.get("language", "en")
        cat = r.get("category", "general")
        
        waveform = r.get("waveform", {})
        prosody = r.get("prosody", {})
        pronunciation = r.get("pronunciation", {})

        clipping = waveform.get("clipping_sample_count", 0)
        clicks = waveform.get("click_count", 0)
        dur_ms = waveform.get("audio_duration_ms", 0)
        unexpected_gaps = waveform.get("unexpected_gaps_count", 0)
        gaps_max_ms = waveform.get("internal_silence_max_ms", 0)

        wer = pronunciation.get("wer", 0.0)
        cer = pronunciation.get("cer", 0.0)
        entities_passed = pronunciation.get("entities_passed", True)
        missing_entities = pronunciation.get("missing_entities", [])
        asr_transcript = pronunciation.get("asr_transcript", "")

        wps = prosody.get("speech_rate_wps", 0.0)
        clunks = prosody.get("clunking_flags", [])

        # ── 3-Tier Classification Logic ──
        reasons = []
        is_fail = False

        # Hard Fail Conditions
        if dur_ms < 200:
            reasons.append("FAIL: Empty or corrupted audio file")
            is_fail = True
        if clipping > 0:
            reasons.append(f"FAIL: Audio clipping detected ({clipping} samples)")
            is_fail = True
        if not entities_passed and cer > 0.15:
            reasons.append(f"FAIL: Critical entity corrupted: {missing_entities}")
            is_fail = True

        if is_fail:
            fail_cases.append({
                "case_id": case_id,
                "text": text,
                "language": lang,
                "category": cat,
                "status": "FAIL",
                "reasons": reasons,
                "wer": wer,
                "wps": wps,
                "asr_transcript": asr_transcript,
                "audio_path": f"evaluation/tts/generated/{case_id}/tts_telephony.wav",
            })
            continue

        # Review / Borderline Conditions
        is_review = False
        if unexpected_gaps > 0:
            reasons.append(f"REVIEW: Long clause pause ({gaps_max_ms}ms > 450ms) - verify naturalness")
            is_review = True
        if not entities_passed and cer <= 0.15:
            reasons.append(f"REVIEW: Number formatting / punctuation variance (CER={cer}): {missing_entities}")
            is_review = True
        if lang in ("hi", "hi-en") and wer > 0.30:
            reasons.append(f"REVIEW: Multilingual/Hinglish transcription variance (WER={wer})")
            is_review = True
        elif lang == "en" and wer > 0.15:
            reasons.append(f"REVIEW: English pronunciation ASR variance (WER={wer})")
            is_review = True
        if wps > 3.6 or (wps < 1.6 and len(text.split()) > 3):
            reasons.append(f"REVIEW: Out-of-standard speech rate ({wps} WPS)")
            is_review = True

        if is_review:
            review_cases.append({
                "case_id": case_id,
                "text": text,
                "language": lang,
                "category": cat,
                "status": "REVIEW",
                "reasons": reasons,
                "wer": wer,
                "wps": wps,
                "asr_transcript": asr_transcript,
                "audio_path": f"evaluation/tts/generated/{case_id}/tts_telephony.wav",
            })
        else:
            pass_cases.append(case_id)

    total_count = len(results)
    pass_count = len(pass_cases)
    review_count = len(review_cases)
    fail_count = len(fail_cases)

    # CLI Output
    print(f"\n========================================================")
    print(f"  TTS QUALITY AUDIT REVIEW QUEUE ({run_id})")
    print(f"========================================================")
    print(f"  Total Test Cases:       {total_count}")
    print(f"  Automated Pass (Clean): {pass_count} ({round(pass_count/total_count*100, 1)}%) [No Listening Required]")
    print(f"  Needs Review:           {review_count} ({round(review_count/total_count*100, 1)}%) [Flagged for Verification]")
    print(f"  Hard Failures:          {fail_count}")
    print(f"========================================================\n")

    if review_cases:
        print("Flagged Cases for Listener Review:")
        for r in review_cases[:12]:
            print(f"  - [{r['case_id']}] ({r['language']}) {r['reasons'][0]}")
        if len(review_cases) > 12:
            print(f"    ... (+ {len(review_cases) - 12} more items)")

    # ── Generate Lightweight Review HTML Console ──
    html_items = ""
    for idx, item in enumerate(fail_cases + review_cases, start=1):
        c_id = item["case_id"]
        status = item["status"]
        badge_cls = "badge-danger" if status == "FAIL" else "badge-warning"
        reasons_html = "".join(f"<li>{reason}</li>" for reason in item["reasons"])
        audio_src = item["audio_path"]

        html_items += f"""
        <div class="review-card">
            <div class="card-header">
                <div>
                    <span class="badge {badge_cls}">{status}</span>
                    <strong style="font-size: 16px; margin-left: 8px;">{c_id}</strong>
                    <span class="lang-tag">{item['language']}</span>
                    <span class="cat-tag">{item['category']}</span>
                </div>
                <div><small style="color: #94a3b8;">WER: {item['wer']} | Rate: {item['wps']} WPS</small></div>
            </div>
            <div style="margin: 10px 0;">
                <div style="color: #f8fafc; font-weight: 500;">"{item['text']}"</div>
                <div style="color: #94a3b8; font-size: 12px; font-family: monospace; margin-top: 4px;">ASR: {item['asr_transcript']}</div>
            </div>
            <div class="reasons-box">
                <ul>{reasons_html}</ul>
            </div>
            <audio controls preload="metadata" style="width: 100%; margin: 8px 0;">
                <source src="../../{audio_src}" type="audio/wav">
                Your browser does not support audio playback.
            </audio>
            <div class="checklist">
                <label><input type="checkbox"> C1: Click/Pop</label>
                <label><input type="checkbox"> C6: Unnatural Silence</label>
                <label><input type="checkbox"> C7: Robotic Tone</label>
                <label><input type="checkbox"> C8: Mispronunciation</label>
                <label><input type="checkbox"> C10: Intonation Flaw</label>
                <label style="color: #10b981; font-weight: 600;"><input type="checkbox"> Approved / Natural</label>
            </div>
        </div>
        """

    html_doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>TTS Human Review Queue - {run_id}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0f172a; color: #f8fafc; padding: 24px; }}
        .container {{ max-width: 900px; margin: 0 auto; }}
        h1 {{ color: #f8fafc; font-size: 24px; }}
        .scorecard {{ display: flex; gap: 16px; margin: 20px 0; }}
        .card {{ background: #1e293b; border-radius: 8px; padding: 14px 20px; border: 1px solid #334155; flex: 1; text-align: center; }}
        .card-val {{ font-size: 24px; font-weight: 700; color: #38bdf8; margin-top: 4px; }}
        .badge {{ padding: 3px 8px; border-radius: 12px; font-size: 11px; font-weight: 600; text-transform: uppercase; }}
        .badge-danger {{ background: #ef444422; color: #ef4444; border: 1px solid #ef4444; }}
        .badge-warning {{ background: #f59e0b22; color: #f59e0b; border: 1px solid #f59e0b; }}
        .lang-tag, .cat-tag {{ background: #334155; color: #cbd5e1; padding: 2px 6px; border-radius: 4px; font-size: 11px; margin-left: 4px; }}
        .review-card {{ background: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 16px; margin-bottom: 16px; }}
        .card-header {{ display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #334155; padding-bottom: 8px; }}
        .reasons-box {{ background: #0f172a; border-left: 3px solid #f59e0b; padding: 8px 12px; margin: 8px 0; border-radius: 0 4px 4px 0; font-size: 13px; color: #fbbf24; }}
        .reasons-box ul {{ margin: 0; padding-left: 18px; }}
        .checklist {{ display: flex; flex-wrap: wrap; gap: 12px; font-size: 12px; color: #94a3b8; margin-top: 10px; padding-top: 8px; border-top: 1px solid #334155; }}
        .checklist label {{ display: flex; align-items: center; gap: 4px; cursor: pointer; }}
    </style>
</head>
<body>
<div class="container">
    <h1>TTS Human Listener Review Queue</h1>
    <p style="color: #94a3b8;">Run: <code>{run_id}</code> | Reviewing only flagged/borderline samples ({review_count + fail_count} of {total_count})</p>

    <div class="scorecard">
        <div class="card"><div style="color: #94a3b8;">Total Evaluated</div><div class="card-val">{total_count}</div></div>
        <div class="card"><div style="color: #94a3b8;">Automated Pass</div><div class="card-val" style="color: #10b981;">{pass_count}</div></div>
        <div class="card"><div style="color: #94a3b8;">Needs Review</div><div class="card-val" style="color: #f59e0b;">{review_count}</div></div>
        <div class="card"><div style="color: #94a3b8;">Hard Failures</div><div class="card-val" style="color: #ef4444;">{fail_count}</div></div>
    </div>

    <h2>Items Requiring Listener Verification</h2>
    {html_items if html_items else '<p style="color: #10b981;">All samples passed automated checks cleanly. No manual listening needed!</p>'}
</div>
</body>
</html>
"""

    out_html = Path("evaluation/reports/tts") / "audio_listening_station_review.html"
    with open(out_html, "w", encoding="utf-8") as hf:
        hf.write(html_doc)

    print(f"\nGenerated Focused Listener Review Station at: {out_html}")
    return {
        "total": total_count,
        "pass": pass_count,
        "review": review_count,
        "fail": fail_count,
        "review_station_html": str(out_html),
    }


if __name__ == "__main__":
    report_arg = sys.argv[1] if len(sys.argv) > 1 else None
    build_review_queue(report_arg)
