"""
Gemini kalitini tez tekşiriş:
    python -m app.try_photo demo/tahlil_bahromova_naima.jpg
"""
import asyncio
import json
import sys
from pathlib import Path

from .config import load_env
from .extract import extract_from_image
from .rules import Patient, Visit, assess


async def main(path: str) -> None:
    load_env()
    p = Path(path)
    mime = "image/png" if p.suffix.lower() == ".png" else "image/jpeg"
    ex = await extract_from_image(p.read_bytes(), mime)
    print(json.dumps({k: ex[k] for k in ("patient_name", "test_date", "values", "warnings")},
                     ensure_ascii=False, indent=2))
    v = ex["values"]
    a = assess(Patient(age=27), [Visit(date="2026-11-17", sbp=v["sbp"], dbp=v["dbp"],
                                       protein_g_l=v["protein_g_l"], hb_g_l=v["hb_g_l"],
                                       glucose_fasting=v["glucose_fasting"])])
    icon = {"red": "🔴", "yellow": "🟡", "green": "🟢"}[a.zone]
    print(f"\n{icon} ZONA: {a.zone.upper()}\n{a.summary_uz}")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "demo/tahlil_bahromova_naima.jpg"))
