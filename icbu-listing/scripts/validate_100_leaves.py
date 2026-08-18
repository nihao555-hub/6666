#!/usr/bin/env python3
"""Sample ~100 leaf categories and verify evidence-gated + AI schema fill.

Usage (from icbu-listing/):
  python3 scripts/validate_100_leaves.py [--limit 100] [--live-ai] [--fetch]

Without --live-ai, only deterministic fact→option mapping is measured.
With --live-ai, unresolved required attrs are sent to the configured model.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "server"))

from dotenv import load_dotenv  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

load_dotenv(ROOT / ".env")

from ai import AiClient, Understanding  # noqa: E402
from schema import index_fields, parse_schema  # noqa: E402

from server.models import Shop  # noqa: E402
from server.services import catalog  # noqa: E402
from server.services.fact_bundle import FactBundle  # noqa: E402
from server.services.schema_fill import fill_category_draft  # noqa: E402
from server.services.shop_client import shop_api  # noqa: E402


class MockEvidenceAi:
    """Pick the first official option that appears in seller facts — contract stand-in for live AI."""

    def chat_json(self, messages: list[dict[str, Any]], temperature: float = 0.0) -> dict[str, Any]:
        body = messages[0]["content"]
        facts_start = body.find("Facts:")
        attrs_start = body.find("Attributes:")
        if facts_start < 0 or attrs_start < 0:
            return {}
        facts_blob = body[facts_start:attrs_start].lower()
        attrs = json.loads(body[attrs_start + len("Attributes:") : body.rfind("\n\n")].strip())
        out: dict[str, str] = {}
        for field_id, meta in attrs.items():
            for option in meta.get("options") or []:
                token = str(option).lower().strip()
                if not token or token in {"other", "custom", "其他"}:
                    continue
                if token in facts_blob:
                    out[field_id] = str(option)
                    break
                for piece in token.replace("/", " ").split():
                    if len(piece) >= 3 and piece in facts_blob:
                        out[field_id] = str(option)
                        break
                if field_id in out:
                    break
        return out


def sample_leaf_ids(session: Session, limit: int, seed: int) -> list[str]:
    rows = session.execute(
        text("SELECT category_id FROM category_nodes WHERE is_leaf = 1 ORDER BY category_id")
    ).fetchall()
    ids = [str(row[0]) for row in rows]
    if len(ids) <= limit:
        return ids
    random.seed(seed)
    step = max(1, len(ids) // limit)
    picked = ids[::step][:limit]
    if len(picked) < limit:
        extra = [item for item in ids if item not in picked]
        random.shuffle(extra)
        picked.extend(extra[: limit - len(picked)])
    return picked[:limit]


def rich_bundle(category_name: str) -> FactBundle:
    return FactBundle(
        sku="SAMPLE-001",
        name=category_name or "Wholesale sample product",
        brand="SampleBrand",
        origin="China",
        price="1.50",
        moq="500",
        note="500@1.50; 1000@1.20; OEM welcome",
        specs={
            "material": "Plastic and metal",
            "color": "Red, Blue, Black",
            "size": "10cm",
            "weight": "120g",
            "certification": "CE",
            "usage": "Daily use, retail, gift",
        },
    )


def required_option_fields(xml: str) -> list[tuple[str, str]]:
    specs = index_fields(parse_schema(xml))
    out: list[tuple[str, str]] = []
    for group_id in ("icbuCatProp", "saleProp"):
        group = specs.get(group_id)
        if group is None:
            continue
        for child in group.children:
            if child.required and child.options:
                out.append((group_id, child.id))
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--live-ai", action="store_true")
    parser.add_argument("--mock-ai", action="store_true", help="Deterministic AI shim for contract runs")
    parser.add_argument("--fetch", action="store_true", help="Fetch missing schemas from ICBU API")
    parser.add_argument("--db", default=str(ROOT / "data" / "auto-shoper.db"))
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"Database not found: {db_path}", file=sys.stderr)
        return 1

    engine = create_engine(f"sqlite:///{db_path}")
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    shop = session.query(Shop).filter(Shop.access_token != "").first()
    if shop is None:
        print("No authorized shop in database — cannot fetch schemas.", file=sys.stderr)
        return 1
    api = shop_api(shop)

    ai = None
    if args.mock_ai:
        ai = MockEvidenceAi()
    elif args.live_ai:
        ai = AiClient.from_env_or_none()
        if ai is None:
            print("OPENAI_API_KEY missing — cannot run live AI pass.", file=sys.stderr)
            return 1

    leaf_ids = sample_leaf_ids(session, args.limit, args.seed)
    defaults = {
        "origin": "China",
        "brand": "SampleBrand",
        "priceUnit": "Piece/Pieces",
        "saleType": "Unit",
        "shippingTemplateId": "",
        "ladderPeriod": "15",
        "paymentMethod": "T/T",
        "port": "Ningbo",
        "market": "询盘",
        "logisticsProperty": "general_cargo_0",
        "marketSample": "Unavailable",
        "language": "en_US",
    }

    stats = {
        "leaves_targeted": len(leaf_ids),
        "schema_ok": 0,
        "schema_failed": 0,
        "required_option_fields": 0,
        "filled_local": 0,
        "filled_ai": 0,
        "still_missing": 0,
        "ai_calls": 0,
    }
    failures: list[dict[str, str]] = []

    for index, category_id in enumerate(leaf_ids, start=1):
        node = catalog.get_node(session, api, category_id, fetch=False)
        label = catalog.label(node) if node else category_id
        try:
            xml = catalog.get_schema_xml(session, api, category_id, "en_US", fetch=args.fetch)
        except Exception as exc:  # noqa: BLE001
            stats["schema_failed"] += 1
            failures.append({"category_id": category_id, "error": str(exc)[:200]})
            continue
        if not xml.strip():
            stats["schema_failed"] += 1
            failures.append({"category_id": category_id, "error": "empty schema"})
            continue
        stats["schema_ok"] += 1

        bundle = rich_bundle(label)
        understanding = bundle.enrich(
            Understanding(
                product_name=bundle.name,
                material=bundle.specs.get("material", ""),
                colors=["Red", "Blue", "Black"],
                usage=bundle.specs.get("usage", ""),
                features=["OEM welcome", "Bulk order"],
                specs=dict(bundle.specs),
            )
        )
        try:
            report = fill_category_draft(
                xml,
                understanding=understanding,
                bundle=bundle,
                defaults=defaults,
                category_values={},
                price=bundle.price,
                moq=bundle.moq,
                ai=ai,
                images_applied=True,
                category_id=category_id,
                title=f"Wholesale {bundle.name[:40]}",
                keywords=["wholesale", "factory", "bulk"],
                highlights=bundle.text_blob(),
            )
        except Exception as exc:  # noqa: BLE001
            failures.append({"category_id": category_id, "error": f"fill failed: {exc}"[:200]})
            continue
        stats["ai_calls"] += report.stats.ai_calls

        req_fields = required_option_fields(xml)
        stats["required_option_fields"] += len(req_fields)
        for group_id, field_id in req_fields:
            group_values = report.values.get(group_id) or {}
            if field_id in group_values:
                path = f"{group_id}.{field_id}"
                source = report.evidence.get(path) or report.evidence.get(field_id)
                if source and source.source == "ai":
                    stats["filled_ai"] += 1
                else:
                    stats["filled_local"] += 1
            else:
                stats["still_missing"] += 1

        if index % 10 == 0:
            print(f"… {index}/{len(leaf_ids)} leaves processed", flush=True)
        time.sleep(0.05)

    session.close()

    summary = {
        **stats,
        "live_ai": bool(args.live_ai),
        "mock_ai": bool(args.mock_ai),
        "fill_rate_local": round(stats["filled_local"] / max(stats["required_option_fields"], 1), 3),
        "fill_rate_ai": round(stats["filled_ai"] / max(stats["required_option_fields"], 1), 3),
        "missing_rate": round(stats["still_missing"] / max(stats["required_option_fields"], 1), 3),
        "failures_sample": failures[:5],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    # Pass when schemas parse and AI path fills at least some gated attrs when enabled.
    if stats["schema_ok"] < min(10, args.limit):
        return 2
    if args.live_ai and stats["filled_ai"] == 0 and stats["still_missing"] > 0:
        return 3
    if args.mock_ai and stats["filled_ai"] == 0 and stats["required_option_fields"] > 0:
        return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
