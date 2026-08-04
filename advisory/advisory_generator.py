"""
Phase 3 (Objective O5) — Personalized, Grounded Health Advisory Generation.

Grounded in CPCB & WHO 2021 ambient air quality standards.
Fuses local Ollama LLaMA 3.1 8B for natural rephrasing with strict factual guardrails.

Usage:
    .venv/bin/python advisory/advisory_generator.py --aqi 208 --age adult --respiratory --activity athlete
"""
import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(__file__))
from aqi_thresholds import categorize  # noqa: E402

load_dotenv()

PROVIDER = os.getenv("ADVISORY_LLM_PROVIDER", "ollama")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")

ACTIVITY_MAP = {
    "sedentary": "sedentary",
    "indoors": "sedentary",
    "rest": "sedentary",
    "moderate": "moderate",
    "walking": "moderate",
    "outdoor_worker": "outdoor_worker",
    "labor": "outdoor_worker",
    "worker": "outdoor_worker",
    "athlete": "athlete",
    "exercise": "athlete",
    "running": "athlete",
    "workout": "athlete",
}

def sanitize_activity(act: str) -> str:
    act_lower = str(act).lower().strip()
    for key, val in ACTIVITY_MAP.items():
        if key in act_lower:
            return val
    return "moderate"


def build_profile_notes(age_band, respiratory, cardiac, pregnant, activity_level):
    notes = []
    if age_band == "child":
        notes.append("children breathe faster and ingest more air volume relative to body mass")
    elif age_band == "elderly":
        notes.append("seniors have reduced cardiovascular and pulmonary reserves")

    if respiratory:
        notes.append("pre-existing respiratory conditions (asthma/COPD) trigger hyper-reactive airway spasms under PM2.5")
    if cardiac:
        notes.append("elevated fine particulate matter causes endothelial dysfunction and ischemic cardiac risk")
    if pregnant:
        notes.append("transplacental translocation of ultrafine particles poses fetal developmental risks")
    if activity_level in ("outdoor_worker", "athlete"):
        notes.append("high minute ventilation rate significantly amplifies deep alveolar particulate deposition")
    return notes


def calculate_risk(aqi_val, age_band, respiratory, cardiac, pregnant, activity_level):
    score = 0
    if aqi_val > 50: score += 1
    if aqi_val > 100: score += 2
    if aqi_val > 200: score += 3
    if aqi_val > 300: score += 4

    if age_band in ("child", "elderly"): score += 2
    if respiratory: score += 3
    if cardiac: score += 3
    if pregnant: score += 3
    if activity_level in ("outdoor_worker", "athlete"): score += 2

    if score <= 2:
        return "LOW RISK", "#10b981"
    elif score <= 5:
        return "MODERATE RISK", "#eab308"
    elif score <= 8:
        return "HIGH HEALTH RISK", "#f97316"
    else:
        return "SEVERE CRITICAL RISK", "#ef4444"


def get_dos_and_donts(aqi_val, respiratory, cardiac, activity_level):
    dos = []
    donts = []

    if aqi_val <= 100:
        dos.append("Enjoy normal outdoor activities and ventilate indoor spaces.")
        dos.append("Maintain routine physical exercise.")
        donts.append("Avoid idling vehicles near residential areas.")
    elif aqi_val <= 200:
        dos.append("Wear an N95 respirator if spending extended time near high-traffic roads.")
        dos.append("Run indoor air purifiers with HEPA filtration if available.")
        donts.append("Avoid prolonged heavy exertion outdoors during morning rush hours.")
        donts.append("Do not burn incense, candles, or biomass indoors.")
    elif aqi_val <= 300:
        dos.append("Wear an N95 or FFP2 respirator outdoors at all times.")
        dos.append("Keep windows closed; operate air purifiers on high mode.")
        dos.append("Use saline nasal spray and stay hydrated to clear upper respiratory mucosa.")
        donts.append("Do NOT engage in outdoor running, sports, or heavy physical work.")
        donts.append("Avoid morning outdoor walks (thermal inversion traps pollutants near ground).")
    else:
        dos.append("STAY INDOORS with sealed windows and HEPA air purification.")
        dos.append("Wear an N99 / FFP3 fitted mask if stepping outside is mandatory.")
        dos.append("Keep prescribed emergency inhalers (salbutamol) and cardiac medications at hand.")
        donts.append("STRICTLY NO outdoor exercise or non-essential travel.")
        donts.append("Do not open windows or doors even during daytime.")

    return dos, donts


def get_mask_recommendation(aqi_val):
    if aqi_val <= 100:
        return "Cloth Mask / Optional", "#84cc16"
    elif aqi_val <= 200:
        return "N95 Respirator Recommended for Sensitive Groups", "#eab308"
    elif aqi_val <= 300:
        return "Mandatory N95 / FFP2 Certified Respirator", "#f97316"
    else:
        return "N99 / FFP3 / Dual-Cartridge Mask Mandatory", "#ef4444"


def rephrase_with_ollama(template_text):
    import requests
    prompt = (
        "You are an expert pulmonologist and environmental medicine specialist. "
        "Rephrase the following air quality advisory to be empathetic, professional, clear, and actionable. "
        "Do NOT invent new numbers or change medical thresholds. Keep it to 3 concise, impactful sentences.\n\n"
        f"Input Advisory: {template_text}"
    )
    try:
        resp = requests.post(
            f"{OLLAMA_HOST}/api/generate",
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
            timeout=12,
        )
        resp.raise_for_status()
        text = resp.json().get("response", "").strip()
        if text:
            return text
    except Exception as e:
        print(f"Ollama rephrase fallback to template: {e}", file=sys.stderr)
    return template_text


def generate_full_advisory(aqi_val, age_band="adult", respiratory=False, cardiac=False,
                            pregnant=False, activity_level="moderate", language="en"):
    activity_level = sanitize_activity(activity_level)
    cat = categorize(aqi_val)
    risk_label, risk_color = calculate_risk(aqi_val, age_band, respiratory, cardiac, pregnant, activity_level)
    profile_notes = build_profile_notes(age_band, respiratory, cardiac, pregnant, activity_level)
    dos, donts = get_dos_and_donts(aqi_val, respiratory, cardiac, activity_level)
    mask_rec, mask_color = get_mask_recommendation(aqi_val)

    sensitive_flag = any([age_band in ("child", "elderly"), respiratory, cardiac, pregnant, activity_level in ("outdoor_worker", "athlete")])
    base_text = cat["sensitive"] if sensitive_flag else cat["general"]
    reason_str = (" Special risk factors: " + "; ".join(profile_notes) + ".") if profile_notes else ""
    raw_template = f"Air Quality Index is currently {aqi_val} ({cat['name']}). {base_text}{reason_str}"

    final_text = raw_template
    generated_by = "template"
    if PROVIDER == "ollama":
        final_text = rephrase_with_ollama(raw_template)
        generated_by = "ollama (llama3.1:8b)"

    # Calculate WHO exceedance multiplier (WHO daily PM2.5 guide = 15 ug/m3; approx PM2.5 ~ aqi * 0.45)
    est_pm25 = round(aqi_val * 0.45, 1)
    who_multiplier = round(est_pm25 / 15.0, 1)

    return {
        "aqi": aqi_val,
        "category": cat["name"],
        "risk_level": risk_label,
        "risk_color": risk_color,
        "executive_summary": final_text,
        "dos": dos,
        "donts": donts,
        "mask_recommendation": mask_rec,
        "mask_color": mask_color,
        "estimated_pm25": est_pm25,
        "who_guideline_multiplier": f"{who_multiplier}x WHO 2021 Daily Limit",
        "medical_warnings": [
            "Seek emergency care if experiencing acute shortness of breath or persistent chest pressure.",
            "Asthma patients: keep rescue bronchodilator inhaler accessible at all times.",
        ],
        "generated_by": generated_by,
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--aqi", type=float, required=True)
    p.add_argument("--age", default="adult")
    p.add_argument("--respiratory", action="store_true")
    p.add_argument("--cardiac", action="store_true")
    p.add_argument("--pregnant", action="store_true")
    p.add_argument("--activity", default="moderate")
    p.add_argument("--language", default="en")

    args = p.parse_args()
    result = generate_full_advisory(
        aqi_val=args.aqi,
        age_band=args.age,
        respiratory=args.respiratory,
        cardiac=args.cardiac,
        pregnant=args.pregnant,
        activity_level=args.activity,
        language=args.language,
    )
    print(json.dumps(result, indent=2))
