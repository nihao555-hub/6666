#!/usr/bin/env python3
"""Live smoke: three products, six Alibaba slots, each with a public reference photo."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from server.config import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from server.services.grsai_images import generate_one  # noqa: E402
from server.services.image_templates import plan_stack  # noqa: E402

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/opt/cursor/artifacts/icbu-three-scenes")

# Wikimedia Commons originals, rehosted on this run's public app so the
# China image host can fetch them. Used only as identity-lock references.
# 1) 油漆刷 — File:Paint brush.JPG (English ferrule text "100% PURE BRISTLES")
# 2) Arabic name — Hykker TWS (brand printed on the case)
# 3) Spanish name — File:Coffee_mug.jpg (Swedish print already on the mug)
PUBLIC_REF_BASE = os.environ.get(
    "PUBLIC_REF_BASE",
    "https://milk-loads-foreign-identify.trycloudflare.com/refs",
)
SCENES = [
    {
        "id": "paint-brush",
        "product_name": "油漆刷",
        "note": "猪鬃刷毛，拉丝铁皮箍，哑光木柄",
        "family_id": "tools",
        "ref": f"{PUBLIC_REF_BASE}/paint-brush.jpg",
    },
    {
        "id": "earbuds",
        "product_name": "سماعات أذن لاسلكية",
        "note": "glossy white plastic case, soft silicone tips",
        "family_id": "electronics",
        "ref": f"{PUBLIC_REF_BASE}/earbuds.jpg",
    },
    {
        "id": "ceramic-mug",
        "product_name": "Taza de cerámica",
        "note": "glazed white ceramic, printed graphic on the front",
        "family_id": "home",
        "ref": f"{PUBLIC_REF_BASE}/ceramic-mug.jpg",
    },
]


def download(url: str, dest: Path) -> None:
    if dest.is_file() and dest.stat().st_size > 1000:
        return
    response = requests.get(url, timeout=60, headers={"User-Agent": "AutoShoper/1.0"})
    response.raise_for_status()
    dest.write_bytes(response.content)


def ref_candidates(url: str) -> list[str]:
    """Wikimedia first; wsrv.nl if the China image host cannot reach Commons."""
    hostless = url.replace("https://", "").replace("http://", "")
    return [url, f"https://wsrv.nl/?url={hostless}&w=1200"]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    report: list[dict] = []
    for scene in SCENES:
        folder = OUT / scene["id"]
        folder.mkdir(parents=True, exist_ok=True)
        ref_path = folder / "00-reference.jpg"
        print(f"== {scene['product_name']}  ref", flush=True)
        download(scene["ref"], ref_path)
        plan = plan_stack(
            family_id=scene["family_id"],
            product_name=scene["product_name"],
            note=scene["note"],
            reference_urls=[scene["ref"]],
        )
        (folder / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
        refs = ref_candidates(scene["ref"])
        identity = ""
        slots_out = []
        for item in plan["slots"]:
            started = time.time()
            print(f"   {item['index']}. {item['id']} {item['name']}", flush=True)
            last_error = None
            content = b""
            remote = ""
            used_refs: list[str] = []
            for candidate in refs:
                used_refs = [candidate]
                if identity and identity not in used_refs:
                    used_refs.append(identity)
                try:
                    content, remote = generate_one(item["prompt"], urls=used_refs)
                    last_error = None
                    break
                except Exception as exc:  # noqa: BLE001
                    last_error = exc
                    print(f"      retry after {exc}", flush=True)
            if last_error is not None:
                raise last_error
            ext = "jpg" if remote.lower().endswith((".jpg", ".jpeg")) else "png"
            filename = f"{int(item['index']):02d}-{item['id']}.{ext}"
            (folder / filename).write_bytes(content)
            if item["id"] == "main":
                identity = remote
            slots_out.append(
                {
                    "id": item["id"],
                    "name": item["name"],
                    "file": filename,
                    "seconds": round(time.time() - started, 1),
                    "prompt": item["prompt"],
                    "remote_url": remote,
                }
            )
        row = {
            "id": scene["id"],
            "product_name": scene["product_name"],
            "product_brief": plan["product_brief"],
            "family": plan["family"]["id"],
            "reference": scene["ref"],
            "slots": slots_out,
        }
        report.append(row)
        (folder / "result.json").write_text(json.dumps(row, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("done", OUT, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
