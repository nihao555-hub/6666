"""AI layer: one vision pass to understand the goods, one pass to write copy.

Deliberately not one model call per field. The understanding pass returns a
structured record; category and attribute alignment are deterministic code on
top of the official schema; only the wording is generated again at the end,
under the constraints the schema declares for that category.
"""

from __future__ import annotations

import base64
import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

import requests

JSON_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)


class AiUnavailable(RuntimeError):
    """Raised when no model is configured or the provider refuses the call."""


@dataclass
class ImageInput:
    filename: str
    content: bytes | None = None
    url: str | None = None

    def as_data_url(self) -> str:
        if self.url:
            return self.url
        payload = base64.b64encode(self.content or b"").decode("ascii")
        return f"data:{_mime(self.filename)};base64,{payload}"


@dataclass
class Understanding:
    product_name: str = ""
    category_hint: str = ""
    material: str = ""
    colors: list[str] = field(default_factory=list)
    style: str = ""
    usage: str = ""
    audience: str = ""
    features: list[str] = field(default_factory=list)
    specs: dict[str, str] = field(default_factory=dict)
    is_set: bool = False
    image_quality: str = "ok"
    confidence: float = 0.0
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "Understanding":
        return cls(
            product_name=str(payload.get("product_name") or "").strip(),
            category_hint=str(payload.get("category_hint") or "").strip(),
            material=str(payload.get("material") or "").strip(),
            colors=_str_list(payload.get("colors")),
            style=str(payload.get("style") or "").strip(),
            usage=str(payload.get("usage") or "").strip(),
            audience=str(payload.get("audience") or "").strip(),
            features=_str_list(payload.get("features")),
            specs={str(k): str(v) for k, v in (payload.get("specs") or {}).items()},
            is_set=bool(payload.get("is_set")),
            image_quality=str(payload.get("image_quality") or "ok"),
            confidence=_confidence(payload.get("confidence")),
            raw=dict(payload),
        )


@dataclass
class Copy:
    title: str = ""
    keywords: list[str] = field(default_factory=list)
    highlights: str = ""
    selling_points: list[str] = field(default_factory=list)
    faqs: list[dict[str, str]] = field(default_factory=list)
    confidence: float = 0.0


def _mime(filename: str) -> str:
    lowered = filename.lower()
    if lowered.endswith(".png"):
        return "image/png"
    if lowered.endswith(".webp"):
        return "image/webp"
    if lowered.endswith(".gif"):
        return "image/gif"
    return "image/jpeg"


def _str_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, Sequence):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _confidence(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, number))


def extract_json(text: str) -> dict[str, Any]:
    candidate = text.strip()
    fenced = JSON_FENCE.search(candidate)
    if fenced:
        candidate = fenced.group(1).strip()
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start >= 0 and end > start:
        candidate = candidate[start : end + 1]
    return json.loads(candidate)


UNDERSTAND_PROMPT = """You are a sourcing expert for Alibaba.com (ICBU) wholesale listings.
Look at the product photos and describe the goods factually. Do not invent
certifications, brands or measurements you cannot see.

Return JSON only, no prose:
{
  "product_name": "plain english noun phrase, e.g. colored pencil set",
  "category_hint": "english leaf category guess, e.g. Colored Pencils",
  "material": "",
  "colors": [],
  "style": "",
  "usage": "who uses it and where",
  "audience": "e.g. students, hotels, retailers",
  "features": ["short factual feature", "..."],
  "specs": {"attribute": "value"},
  "is_set": false,
  "image_quality": "ok | watermark | low_resolution | not_a_product",
  "confidence": 0.0
}
confidence is your certainty about product_name and category_hint."""


COPY_PROMPT = """You write Alibaba.com (ICBU) listings for B2B buyers.

Hard rules, the platform rejects anything that breaks them:
- English only. No Chinese characters, no @, no ? or !, no email, no HTML tags.
- Title: at most {title_limit} bytes, no promotional claims, no brand you were not given.
  Shape it as: modifier + material/feature + product noun + use case. Wholesale-friendly.
- Keywords: exactly {keyword_count}, each 2-4 words, no punctuation, no separators.
- Highlights: one paragraph, at most 400 characters, factual.
- selling_points: 3 short phrases.
- faqs: 2 entries, question and answer, practical for a wholesale buyer (MOQ, samples, lead time, customisation).

Product facts:
{facts}

Return JSON only:
{{"title": "", "keywords": [], "highlights": "", "selling_points": [], "faqs": [{{"question": "", "answer": ""}}], "confidence": 0.0}}"""


ATTR_MAP_PROMPT = """You map a wholesale product to Alibaba.com official attribute options.

You receive ALL seller facts (Excel columns, notes, specs, brand, price tiers) AND product photos.

Rules:
- Fill an option ONLY when the seller would be 100% sure which one to pick from their facts and photos.
- If two or more options could reasonably fit, return empty string — do not guess.
- Use option display text exactly as given for that attribute id.
- Do not invent certifications, brands, origin, price, MOQ, or category.
- Never pick Other / Custom / 其他.

Return JSON only: {{"p-1": "China", "p-9": "colored"}}"""


class AiClient:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        text_model: str,
        timeout: float = 120.0,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.text_model = text_model
        self.timeout = timeout

    @classmethod
    def from_env(cls) -> "AiClient":
        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            raise AiUnavailable("OPENAI_API_KEY 没有配置")
        return cls(
            api_key=api_key,
            base_url=os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            text_model=os.environ.get("TEXT_MODEL", "gpt-4o-mini"),
            timeout=float(os.environ.get("AI_TIMEOUT_SECONDS", "120")),
        )

    @classmethod
    def from_env_or_none(cls) -> "AiClient | None":
        try:
            return cls.from_env()
        except AiUnavailable:
            return None

    def chat(self, messages: list[dict[str, Any]], temperature: float = 0.2) -> str:
        response = requests.post(
            f"{self.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={"model": self.text_model, "messages": messages, "temperature": temperature},
            timeout=self.timeout,
        )
        if response.status_code >= 400:
            raise AiUnavailable(f"模型返回 {response.status_code}: {response.text[:200]}")
        payload = response.json()
        choices = payload.get("choices") or []
        if not choices:
            raise AiUnavailable("模型没有返回内容")
        return choices[0].get("message", {}).get("content") or ""

    def chat_json(self, messages: list[dict[str, Any]], temperature: float = 0.2) -> dict[str, Any]:
        text = self.chat(messages, temperature)
        try:
            return extract_json(text)
        except (json.JSONDecodeError, ValueError):
            repair = messages + [
                {"role": "assistant", "content": text[:2000]},
                {"role": "user", "content": "Return the same answer as valid JSON only, no markdown fence."},
            ]
            return extract_json(self.chat(repair, 0.0))

    def understand(self, images: Sequence[ImageInput], hint: str = "") -> Understanding:
        if not images:
            raise AiUnavailable("没有图片可供识别")
        content: list[dict[str, Any]] = [{"type": "text", "text": UNDERSTAND_PROMPT}]
        if hint:
            content.append({"type": "text", "text": f"Seller note (may be Chinese): {hint}"})
        for image in images[:6]:
            content.append({"type": "image_url", "image_url": {"url": image.as_data_url()}})
        payload = self.chat_json([{"role": "user", "content": content}])
        return Understanding.from_payload(payload)

    def write_copy(
        self,
        understanding: Understanding,
        *,
        title_limit: int = 128,
        keyword_count: int = 3,
        extra_facts: Mapping[str, Any] | None = None,
        angle: str = "",
    ) -> Copy:
        facts = {
            "product_name": understanding.product_name,
            "material": understanding.material,
            "colors": understanding.colors,
            "style": understanding.style,
            "usage": understanding.usage,
            "audience": understanding.audience,
            "features": understanding.features,
            "specs": understanding.specs,
            "is_set": understanding.is_set,
        }
        facts.update(extra_facts or {})
        prompt = COPY_PROMPT.format(
            title_limit=title_limit,
            keyword_count=keyword_count,
            facts=json.dumps(facts, ensure_ascii=False, indent=2),
        )
        if angle:
            # Same goods listed in a second shop: the platform groups listings
            # whose titles only differ in wording, so ask for a genuinely
            # different angle rather than a paraphrase.
            prompt += (
                f"\n\nThis listing must not read like a reworded copy of another one. "
                f"Lead with this angle and pick different keywords accordingly: {angle}"
            )
        payload = self.chat_json([{"role": "user", "content": prompt}], temperature=0.4)
        faqs = []
        for item in payload.get("faqs") or []:
            if isinstance(item, Mapping) and item.get("question") and item.get("answer"):
                faqs.append({"question": str(item["question"]), "answer": str(item["answer"])})
        return Copy(
            title=str(payload.get("title") or "").strip(),
            keywords=_str_list(payload.get("keywords"))[:keyword_count],
            highlights=str(payload.get("highlights") or "").strip(),
            selling_points=_str_list(payload.get("selling_points")),
            faqs=faqs,
            confidence=_confidence(payload.get("confidence")),
        )

    def map_attributes(
        self,
        *,
        images: Sequence[ImageInput],
        facts: Mapping[str, Any],
        attributes: Mapping[str, Any],
    ) -> dict[str, str]:
        """One multimodal call: seller facts + photos → official option labels."""
        prompt = (
            f"{ATTR_MAP_PROMPT}\n\n"
            f"Seller facts: {json.dumps(dict(facts), ensure_ascii=False)}\n"
            f"Attributes: {json.dumps(dict(attributes), ensure_ascii=False)}"
        )
        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        for image in images[:6]:
            content.append({"type": "image_url", "image_url": {"url": image.as_data_url()}})
        payload = self.chat_json([{"role": "user", "content": content}], temperature=0.0)
        return {str(key): str(value).strip() for key, value in payload.items() if value not in (None, "")}

    def shortlist(
        self,
        question: str,
        options: Sequence[str],
        context: Mapping[str, Any],
        limit: int = 3,
    ) -> list[str]:
        """Narrow a level of the category tree instead of committing to one branch.

        A single wrong turn near the root cannot be recovered from later, so the
        caller keeps several branches alive and reranks the leaves at the end.
        """
        if not options:
            return []
        prompt = (
            f"{question}\n"
            "Choose the branches that could plausibly contain this product. "
            f"Return at most {limit}, best first. Copy the option text exactly.\n\n"
            f"Product: {json.dumps(dict(context), ensure_ascii=False)}\n"
            f"Options: {json.dumps(list(options)[:120], ensure_ascii=False)}\n\n"
            '{"choices": ["...", "..."]}'
        )
        payload = self.chat_json([{"role": "user", "content": prompt}], temperature=0.0)
        return _str_list(payload.get("choices"))[:limit]

    def rank_categories(self, paths: Sequence[str], context: Mapping[str, Any]) -> dict[str, Any]:
        """Final pick between full root-to-leaf paths."""
        prompt = (
            "Pick the single Alibaba.com leaf category this wholesale product belongs in.\n"
            f"Product: {json.dumps(dict(context), ensure_ascii=False)}\n"
            f"Candidates: {json.dumps(list(paths)[:40], ensure_ascii=False)}\n\n"
            "Copy one candidate exactly. confidence is how sure you are it is the right leaf.\n"
            '{"choice": "", "confidence": 0.0}'
        )
        payload = self.chat_json([{"role": "user", "content": prompt}], temperature=0.0)
        return {
            "choice": str(payload.get("choice") or "").strip(),
            "confidence": _confidence(payload.get("confidence")),
        }

    def pick_option(self, question: str, options: Sequence[str], context: Mapping[str, Any]) -> dict[str, Any]:
        """Last resort for an attribute that fuzzy matching could not resolve."""
        prompt = (
            "Pick the single best option for a wholesale product attribute.\n"
            f"Attribute: {question}\n"
            f"Options: {json.dumps(list(options)[:60], ensure_ascii=False)}\n"
            f"Product: {json.dumps(dict(context), ensure_ascii=False)}\n"
            'Return JSON only: {"option": "exact option text or empty", "confidence": 0.0}'
        )
        payload = self.chat_json([{"role": "user", "content": prompt}], temperature=0.0)
        return {
            "option": str(payload.get("option") or "").strip(),
            "confidence": _confidence(payload.get("confidence")),
        }
