"""Seller fact bundle — category-agnostic input for dynamic schema fill.

The Excel / feed sheet only lands here. Official leaf fields are filled later
from schema.get + evidence-gated AI, not copied into the spreadsheet.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Mapping

from ai import Understanding  # noqa: E402

from .excel_import import ExcelRow, SPEC_LABELS

LADDER_CHUNK = re.compile(
    r"(?P<qty>\d+)\s*(?:件|pcs|pc|units?|sets?)?\s*[@＠:：]\s*\$?\s*(?P<price>\d+(?:\.\d+)?)",
    re.I,
)
LADDER_PAIR = re.compile(
    r"(?P<qty>\d+)\s*(?:件|pcs)?\s*(?:[/,，]\s*|\s+)\$?\s*(?P<price>\d+(?:\.\d+)?)\s*(?:usd|美元|/pcs)?",
    re.I,
)


@dataclass(frozen=True)
class PriceTier:
    quantity: str
    price: str
    source: str = "excel"


@dataclass(frozen=True)
class VariantFact:
    sku: str
    color: str = ""
    size: str = ""
    price: str = ""
    moq: str = ""
    source: str = "excel"


@dataclass(frozen=True)
class Evidence:
    source: str  # excel | note | spec | shop | vision | user
    quote: str = ""

    def as_dict(self) -> dict[str, str]:
        return {"source": self.source, "quote": self.quote}


@dataclass
class FactBundle:
    parent_sku: str = ""
    sku: str = ""
    name: str = ""
    brand: str = ""
    note: str = ""
    specs: dict[str, str] = field(default_factory=dict)
    price_tiers: list[PriceTier] = field(default_factory=list)
    variants: list[VariantFact] = field(default_factory=list)
    moq: str = ""
    price: str = ""
    origin: str = ""
    evidence: dict[str, Evidence] = field(default_factory=dict)

    def record(self, key: str, source: str, quote: str = "") -> None:
        if key and source:
            self.evidence[key] = Evidence(source=source, quote=quote[:240])

    def has(self, key: str) -> bool:
        return key in self.evidence

    def text_blob(self) -> str:
        bits = [self.name, self.note]
        bits.extend(f"{SPEC_LABELS.get(k, k)} {v}" for k, v in self.specs.items() if str(v).strip())
        return " ".join(part for part in bits if part).strip()

    def enrich(self, understanding: Understanding) -> Understanding:
        """Merge table facts into vision understanding without dropping photo cues."""
        specs = dict(understanding.specs)
        for key, value in self.specs.items():
            if str(value).strip():
                specs[key] = str(value).strip()
        colors = list(understanding.colors)
        if self.specs.get("color"):
            for part in re.split(r"[,，/;；]", str(self.specs["color"])):
                token = part.strip()
                if token and token not in colors:
                    colors.append(token)
        name = understanding.product_name or self.name
        hint = understanding.category_hint or self.name or name
        return Understanding(
            product_name=name,
            category_hint=hint,
            material=understanding.material or self.specs.get("material", ""),
            colors=colors or understanding.colors,
            style=understanding.style,
            usage=understanding.usage,
            audience=understanding.audience,
            features=list(understanding.features),
            specs=specs,
            is_set=understanding.is_set,
            image_quality=understanding.image_quality,
            confidence=understanding.confidence,
            raw={**dict(understanding.raw), "fact_bundle": self.as_dict()},
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "parent_sku": self.parent_sku,
            "sku": self.sku,
            "name": self.name,
            "brand": self.brand,
            "note": self.note,
            "specs": dict(self.specs),
            "price_tiers": [{"quantity": t.quantity, "price": t.price} for t in self.price_tiers],
            "variants": [
                {"sku": v.sku, "color": v.color, "size": v.size, "price": v.price, "moq": v.moq}
                for v in self.variants
            ],
            "moq": self.moq,
            "price": self.price,
            "origin": self.origin,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "FactBundle":
        tiers = [
            PriceTier(str(item.get("quantity") or ""), str(item.get("price") or ""))
            for item in (payload.get("price_tiers") or [])
            if isinstance(item, Mapping)
        ]
        variants = [
            VariantFact(
                sku=str(item.get("sku") or ""),
                color=str(item.get("color") or ""),
                size=str(item.get("size") or ""),
                price=str(item.get("price") or ""),
                moq=str(item.get("moq") or ""),
            )
            for item in (payload.get("variants") or [])
            if isinstance(item, Mapping)
        ]
        specs_raw = payload.get("specs") or {}
        specs = {str(k): str(v) for k, v in specs_raw.items() if str(v).strip()} if isinstance(specs_raw, Mapping) else {}
        return cls(
            parent_sku=str(payload.get("parent_sku") or ""),
            sku=str(payload.get("sku") or ""),
            name=str(payload.get("name") or ""),
            brand=str(payload.get("brand") or ""),
            note=str(payload.get("note") or ""),
            specs=specs,
            price_tiers=tiers,
            variants=variants,
            moq=str(payload.get("moq") or ""),
            price=str(payload.get("price") or ""),
            origin=str(payload.get("origin") or ""),
        )

    def facts_for_ai(self, understanding: Understanding | None = None) -> dict[str, Any]:
        u = understanding or Understanding()
        specs = {**self.specs, **u.specs}
        labeled = {SPEC_LABELS.get(k, k): v for k, v in specs.items() if str(v).strip()}
        return {
            "sku": self.sku,
            "name": self.name,
            "product_name": u.product_name or self.name,
            "category_hint": u.category_hint or self.name,
            "material": u.material or self.specs.get("material", ""),
            "colors": u.colors,
            "specs": specs,
            "specs_labeled": labeled,
            "features": u.features,
            "usage": u.usage,
            "note": self.note,
            "brand": self.brand,
            "price": self.price,
            "moq": self.moq,
            "origin": self.origin,
            "text_blob": self.text_blob(),
            "price_tiers": [{"quantity": t.quantity, "price": t.price} for t in self.price_tiers],
            "vision": {
                "product_name": u.product_name,
                "material": u.material,
                "colors": u.colors,
                "features": u.features,
                "specs": u.specs,
                "usage": u.usage,
                "audience": u.audience,
            },
        }

    def ladder_values(self, max_slots: int = 4) -> dict[str, dict[str, str]]:
        tiers = self.price_tiers[:max_slots]
        if not tiers and self.price and self.moq:
            tiers = [PriceTier(quantity=self.moq, price=self.price, source="excel")]
        out: dict[str, dict[str, str]] = {}
        for index, tier in enumerate(tiers):
            out[f"ladderPrice_{index}"] = {"quantity": tier.quantity, "price": tier.price}
        return out


def parse_price_tiers(*texts: str, fallback_moq: str = "", fallback_price: str = "") -> list[PriceTier]:
    tiers: list[PriceTier] = []
    seen: set[tuple[str, str]] = set()
    for raw in texts:
        for chunk in re.split(r"[;；\n|]", str(raw or "")):
            chunk = chunk.strip()
            if not chunk:
                continue
            match = LADDER_CHUNK.search(chunk) or LADDER_PAIR.search(chunk)
            if not match:
                continue
            qty, price = match.group("qty"), match.group("price")
            key = (qty, price)
            if key in seen:
                continue
            seen.add(key)
            tiers.append(PriceTier(quantity=qty, price=price, source="note"))
    if not tiers and fallback_moq and fallback_price:
        tiers.append(PriceTier(quantity=fallback_moq, price=fallback_price, source="excel"))
    return tiers[:4]


def from_excel_row(row: ExcelRow) -> FactBundle:
    bundle = FactBundle(
        sku=(row.sku or "").strip(),
        name=(row.name or row.title or "").strip(),
        brand=(row.brand or "").strip(),
        note=(row.note or "").strip(),
        specs={k: str(v).strip() for k, v in row.specs.items() if str(v).strip()},
        moq=(row.moq or "").strip(),
        price=(row.price or "").strip(),
        origin=(row.origin or "").strip(),
    )
    if row.spec.strip():
        bundle.specs.setdefault("generic", row.spec.strip())
    bundle.price_tiers = parse_price_tiers(row.note, row.spec, fallback_moq=bundle.moq, fallback_price=bundle.price)
    if bundle.sku:
        bundle.record("sku", "excel", bundle.sku)
    if bundle.name:
        bundle.record("name", "excel", bundle.name)
    if bundle.brand:
        bundle.record("brand", "excel", bundle.brand)
    if bundle.note:
        bundle.record("note", "excel", bundle.note[:120])
    if bundle.price:
        bundle.record("price", "excel", bundle.price)
    if bundle.moq:
        bundle.record("moq", "excel", bundle.moq)
    if bundle.origin:
        bundle.record("origin", "excel", bundle.origin)
    for key, value in bundle.specs.items():
        bundle.record(f"spec.{key}", "excel", f"{SPEC_LABELS.get(key, key)} {value}")
    for tier in bundle.price_tiers:
        bundle.record(f"ladder:{tier.quantity}", tier.source, f"{tier.quantity}@{tier.price}")
    return bundle
