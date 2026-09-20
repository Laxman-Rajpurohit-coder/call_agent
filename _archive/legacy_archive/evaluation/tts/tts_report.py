import glob
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


def generate_tts_html_report(report_json_path: str, output_html_path: Optional[str] = None) -> str:
    path = Path(report_json_path)
    if not path.exists():
        raise FileNotFoundError(f"Report JSON not found: {report_json_path}")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    run_id = data.get("run_id", "unknown_run")
    total = data.get("total_cases", 0)
    passed = data.get("passed_count", 0)
    flagged = data.get("flagged_count", 0)
    pass_rate = round(data.get("pass_rate", 0.0) * 100, 1)

    results: List[Dict[str, Any]] = data.get("results", [])

    # Compute aggregate metrics
    wers = [r.get("pronunciation", {}).get("wer", 0.0) for r in results if "pronunciation" in r]
    avg_wer = round(sum(wers) / len(wers), 3) if wers else 0.0

    wps_list = [r.get("prosody", {}).get("speech_rate_wps", 0.0) for r in results if "prosody" in r]
    avg_wps = round(sum(wps_list) / len(wps_list), 2) if wps_list else 0.0

    total_clipping = sum(r.get("waveform", {}).get("clipping_sample_count", 0) for r in results)
    total_clicks = sum(r.get("waveform", {}).get("click_count", 0) for r in results)
    total_clunks = sum(len(r.get("prosody", {}).get("clunking_flags", [])) for r in results)

    # Category summaries
    cat_map = {}
    for r in results:
        cat = r.get("category", "other")
        if cat not in cat_map:
            cat_map[cat] = {"total": 0, "passed": 0, "wers": []}
        cat_map[cat]["total"] += 1
        if r.get("passed"):
            cat_map[cat]["passed"] += 1
        cat_map[cat]["wers"].append(r.get("pronunciation", {}).get("wer", 0.0))

    cat_rows = ""
    for cat, stats in cat_map.items():
        c_tot = stats["total"]
        c_pas = stats["passed"]
        c_rate = round((c_pas / c_tot) * 100, 1) if c_tot > 0 else 0.0
        c_wer = round(sum(stats["wers"]) / len(stats["wers"]), 3) if stats["wers"] else 0.0
        cat_rows += f"""
        <tr>
            <td><strong>{cat}</strong></td>
            <td>{c_tot}</td>
            <td>{c_pas}</td>
            <td><span class="badge {'badge-success' if c_rate >= 80 else 'badge-warning'}">{c_rate}%</span></td>
            <td>{c_wer}</td>
        </tr>
        """

    # Detailed Result Table
    rows = ""
    for idx, r in enumerate(results, start=1):
        c_id = r.get("case_id")
        text = r.get("text", "")
        lang = r.get("language", "en")
        p_status = r.get("passed", False)
        status_badge = '<span class="badge badge-success">CLEAN</span>' if p_status else '<span class="badge badge-danger">FLAGGED</span>'
        
        pron = r.get("pronunciation", {})
        pros = r.get("prosody", {})
        wave = r.get("waveform", {})

        wer = pron.get("wer", 0.0)
        asr_t = pron.get("asr_transcript", "")
        wps = pros.get("speech_rate_wps", 0.0)
        clunks = pros.get("clunking_flags", [])
        clunk_badges = "".join(f'<span class="clunk-tag">{c}</span>' for c in clunks) if clunks else '<span class="text-muted">None</span>'

        rows += f"""
        <tr class="{'table-row-flagged' if not p_status else ''}">
            <td>{idx}</td>
            <td><code>{c_id}</code></td>
            <td><span class="lang-tag">{lang}</span></td>
            <td>
                <div class="ref-text">{text}</div>
                <div class="asr-text"><small>ASR: {asr_t}</small></div>
            </td>
            <td>{status_badge}</td>
            <td>{wer}</td>
            <td>{wps} WPS</td>
            <td>{clunk_badges}</td>
        </tr>
        """

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>TTS Voice Fluency & Quality Report - {run_id}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background: #0f172a; color: #f8fafc; padding: 24px; }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        h1, h2, h3 {{ color: #e2e8f0; font-weight: 600; }}
        .scorecard {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 16px; margin: 24px 0; }}
        .card {{ background: #1e293b; border-radius: 8px; padding: 18px; border: 1px solid #334155; text-align: center; }}
        .card-val {{ font-size: 28px; font-weight: 700; color: #38bdf8; margin-top: 6px; }}
        .badge {{ padding: 4px 10px; border-radius: 12px; font-size: 12px; font-weight: 600; }}
        .badge-success {{ background: #10b98122; color: #10b981; border: 1px solid #10b981; }}
        .badge-danger {{ background: #ef444422; color: #ef4444; border: 1px solid #ef4444; }}
        .badge-warning {{ background: #f59e0b22; color: #f59e0b; border: 1px solid #f59e0b; }}
        .clunk-tag {{ background: #dc262622; color: #f87171; border: 1px solid #dc2626; padding: 2px 6px; border-radius: 4px; font-size: 11px; margin: 2px; display: inline-block; }}
        .lang-tag {{ background: #3b82f622; color: #60a5fa; padding: 2px 6px; border-radius: 4px; font-size: 11px; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 16px; background: #1e293b; border-radius: 8px; overflow: hidden; }}
        th, td {{ padding: 12px 14px; text-align: left; border-bottom: 1px solid #334155; font-size: 14px; }}
        th {{ background: #0f172a; color: #94a3b8; font-weight: 600; text-transform: uppercase; font-size: 11px; }}
        .ref-text {{ color: #f8fafc; font-weight: 500; }}
        .asr-text {{ color: #94a3b8; font-family: monospace; margin-top: 4px; }}
        .text-muted {{ color: #64748b; font-size: 12px; }}
        .table-row-flagged {{ background: #ef444409; }}
    </style>
</head>
<body>
<div class="container">
    <h1>TTS Voice Quality & Fluency Scorecard</h1>
    <p style="color: #94a3b8;">Run ID: <code>{run_id}</code> | Automated Screening Suite (100 Cases)</p>

    <div class="scorecard">
        <div class="card"><div style="color: #94a3b8;">Total Cases</div><div class="card-val">{total}</div></div>
        <div class="card"><div style="color: #94a3b8;">Clean / Passed</div><div class="card-val" style="color: #10b981;">{passed}</div></div>
        <div class="card"><div style="color: #94a3b8;">Flagged Review</div><div class="card-val" style="color: #f87171;">{flagged}</div></div>
        <div class="card"><div style="color: #94a3b8;">Pass Rate</div><div class="card-val">{pass_rate}%</div></div>
        <div class="card"><div style="color: #94a3b8;">Average WER</div><div class="card-val">{avg_wer}</div></div>
        <div class="card"><div style="color: #94a3b8;">Average WPS</div><div class="card-val">{avg_wps}</div></div>
        <div class="card"><div style="color: #94a3b8;">Clunking Defects</div><div class="card-val" style="color: {'#10b981' if total_clunks == 0 else '#f87171'};">{total_clunks}</div></div>
    </div>

    <h2>Category Breakdown</h2>
    <table>
        <thead>
            <tr>
                <th>Category</th>
                <th>Total Cases</th>
                <th>Passed</th>
                <th>Pass Rate</th>
                <th>Avg WER</th>
            </tr>
        </thead>
        <tbody>
            {cat_rows}
        </tbody>
    </table>

    <h2 style="margin-top: 36px;">Detailed Case Verification Matrix</h2>
    <table>
        <thead>
            <tr>
                <th>#</th>
                <th>Case ID</th>
                <th>Lang</th>
                <th>Text & Independent ASR Transcript</th>
                <th>Status</th>
                <th>WER</th>
                <th>Speech Rate</th>
                <th>Clunking Flags</th>
            </tr>
        </thead>
        <tbody>
            {rows}
        </tbody>
    </table>
</div>
</body>
</html>
"""
    if not output_html_path:
        output_html_path = str(path.parent / f"{run_id}.html")

    with open(output_html_path, "w", encoding="utf-8") as hf:
        hf.write(html_content)

    print(f"Generated HTML report at: {output_html_path}")
    return output_html_path


if __name__ == "__main__":
    if len(sys.argv) > 1:
        generate_tts_html_report(sys.argv[1])
    else:
        # Pick latest report
        reports = glob.glob("evaluation/reports/tts/*.json")
        if reports:
            latest = sorted(reports)[-1]
            generate_tts_html_report(latest)
        else:
            print("No TTS reports found.")
