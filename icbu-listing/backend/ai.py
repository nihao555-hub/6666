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
import time
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

import requests

JSON_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)

# Transient model failures should not abort a whole batch — retry a few times first.
MAX_AI_ATTEMPTS = max(1, int(os.environ.get("AI_MAX_ATTEMPTS", "5")))
AI_RETRY_BASE_DELAY = max(0.0, float(os.environ.get("AI_RETRY_BASE_DELAY", "1.0")))


def _retry_delay(attempt: int) -> float:
    return AI_RETRY_BASE_DELAY * (2**attempt)


def _retryable_status(status_code: int) -> bool:
    return status_code == 429 or status_code >= 500


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


COPY_PROMPT = """You write Alibaba.com (ICBU) B2B wholesale listings. Buyers search by product type,
material, and use case — not marketing hype.

Hard rules — the platform rejects anything that breaks them:
- English only. No Chinese characters, no @, no ? or !, no email, no HTML tags.
- Use ONLY facts provided below. Do not invent brand, certifications (CE/FDA/ISO),
  measurements, colors, materials, or features that are not in the facts.
- If brand is empty in facts, do not mention any brand name.
- Title: at most {title_limit} UTF-8 bytes. No promotional spam such as Hot Sale,
  Best Seller, High Quality, Top Quality, 100% New, Free Shipping, Lowest Price.
- Title shape for ICBU search: [Product noun phrase] + [verified spec/size/count if in facts]
  + [material or key feature if in facts] + [buyer use case if in facts].
  Put the searchable product noun early. Do not repeat the same word twice.
- Keywords: exactly {keyword_count} phrases, each 2-4 English words, no punctuation.
  Slot 1: core product/category head term buyers would search.
  Slot 2: material, spec, or use-case modifier from facts (different words from title).
  Slot 3: buyer-intent term (bulk order, school supply, OEM gift set) only if supported by facts.
  Do not copy the title verbatim. Do not repeat words across all three keywords.
- Highlights: one factual paragraph, at most 400 characters, describing what the product is
  and who it is for. No claims you cannot support from facts.
- selling_points: 3 short phrases, each grounded in facts (material, spec, packaging, use).
- faqs: 2 entries about wholesale (MOQ, samples, lead time, customization). Answers must
  not invent policies — refer to MOQ/price from facts when present, otherwise stay generic.

Product facts (only source of truth):
{facts}

Return JSON only:
{{"title": "", "keywords": [], "highlights": "", "selling_points": [], "faqs": [{{"question": "", "answer": ""}}], "confidence": 0.0}}"""

FORBIDDEN_COPY = re.compile(r"[\u4e00-\u9fff@?!]")
HTML_TAG = re.compile(r"<[^>]+>")
EMAIL_LIKE = re.compile(r"\S+@\S+")
SPAM_PHRASES = (
    "hot sale",
    "best seller",
    "top quality",
    "high quality",
    "100% new",
    "free shipping",
    "lowest price",
    "best price",
    "factory price",
    "limited time",
)


def _utf8_byte_len(text: str) -> int:
    return len(text.encode("utf-8"))


def _strip_platform_forbidden(text: str) -> str:
    cleaned = HTML_TAG.sub("", text or "")
    cleaned = EMAIL_LIKE.sub("", cleaned)
    cleaned = FORBIDDEN_COPY.sub("", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def _trim_title_bytes(text: str, limit: int) -> str:
    title = _strip_platform_forbidden(text)
    for phrase in SPAM_PHRASES:
        title = re.sub(re.escape(phrase), "", title, flags=re.I)
    title = re.sub(r"\s+", " ", title).strip(" -")
    while title and _utf8_byte_len(title) > limit:
        if " " in title:
            title = title.rsplit(" ", 1)[0]
        else:
            title = title[:-1]
    return title


def _sanitize_keyword(raw: str) -> str:
    text = _strip_platform_forbidden(raw)
    text = re.sub(r"[,，;；/|]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    words = text.split()
    if len(words) < 2:
        return ""
    if len(words) > 4:
        text = " ".join(words[:4])
    return text


def sanitize_copy(
    copy: Copy,
    *,
    title_limit: int = 128,
    keyword_count: int = 3,
    brand: str = "",
) -> Copy:
    """Normalize AI copy to platform-safe, factual B2B wording."""
    title = _trim_title_bytes(copy.title, title_limit)
    if brand.strip():
        brand_lower = brand.strip().lower()
        if brand_lower not in title.lower():
            candidate = _trim_title_bytes(f"{brand.strip()} {title}", title_limit)
            if candidate:
                title = candidate

    title_tokens = {token for token in re.split(r"\W+", title.lower()) if len(token) > 2}
    seen: set[str] = set()
    keywords: list[str] = []
    for raw in copy.keywords:
        keyword = _sanitize_keyword(raw)
        if not keyword:
            continue
        key = keyword.lower()
        if key in seen:
            continue
        kw_tokens = {token for token in re.split(r"\W+", key) if len(token) > 2}
        if kw_tokens and kw_tokens <= title_tokens:
            continue
        seen.add(key)
        keywords.append(keyword)
        if len(keywords) >= keyword_count:
            break

    highlights = _strip_platform_forbidden(copy.highlights)[:400]
    selling_points = [_strip_platform_forbidden(item) for item in copy.selling_points if _strip_platform_forbidden(item)][:3]
    faqs: list[dict[str, str]] = []
    for item in copy.faqs:
        question = _strip_platform_forbidden(str(item.get("question") or ""))
        answer = _strip_platform_forbidden(str(item.get("answer") or ""))
        if question and answer:
            faqs.append({"question": question, "answer": answer})
            if len(faqs) >= 2:
                break

    return Copy(
        title=title,
        keywords=keywords,
        highlights=highlights,
        selling_points=selling_points,
        faqs=faqs,
        confidence=copy.confidence,
    )


ATTR_MAP_PROMPT = """You map a wholesale product to Alibaba.com official category fields.

You receive ALL seller facts (Excel columns, notes, specs, brand, price tiers) AND product photos.

Each field has a field_type:
- singleCheck / multiCheck: pick one option text exactly from the options list
- input / other text fields: write the factual value (model number, size text, etc.)

Rules:
- Fill ONLY when the seller would be 100% sure from their facts and photos.
- If two or more values could fit, return empty string — do not guess.
- Do not invent certifications, brands, origin, price, MOQ, or category.
- Never pick Other / Custom / 其他.

Return JSON only: {{"p-1": "China", "p-3": "GP-100", "p-9": "colored"}}"""


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

    def chat(
        self,
        messages: list[dict[str, Any]],
        temperature: float = 0.2,
        *,
        timeout: float | None = None,
    ) -> str:
        last_error: Exception | None = None
        for attempt in range(MAX_AI_ATTEMPTS):
            try:
                response = requests.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={"model": self.text_model, "messages": messages, "temperature": temperature},
                    timeout=self.timeout if timeout is None else timeout,
                )
                if response.status_code >= 400:
                    detail = f"模型返回 {response.status_code}: {response.text[:200]}"
                    if _retryable_status(response.status_code) and attempt < MAX_AI_ATTEMPTS - 1:
                        time.sleep(_retry_delay(attempt))
                        continue
                    raise AiUnavailable(detail)
                payload = response.json()
                choices = payload.get("choices") or []
                if not choices:
                    if attempt < MAX_AI_ATTEMPTS - 1:
                        time.sleep(_retry_delay(attempt))
                        continue
                    raise AiUnavailable("模型没有返回内容")
                return choices[0].get("message", {}).get("content") or ""
            except AiUnavailable as exc:
                last_error = exc
                raise
            except requests.exceptions.RequestException as exc:
                last_error = exc
                if attempt < MAX_AI_ATTEMPTS - 1:
                    time.sleep(_retry_delay(attempt))
                    continue
                raise AiUnavailable(f"模型请求失败: {exc}") from exc
        raise AiUnavailable(f"模型请求失败（已重试 {MAX_AI_ATTEMPTS} 次）: {last_error}")

    def _chat_json_once(
        self,
        messages: list[dict[str, Any]],
        temperature: float,
        *,
        timeout: float | None,
    ) -> dict[str, Any]:
        text = self.chat(messages, temperature, timeout=timeout)
        try:
            return extract_json(text)
        except (json.JSONDecodeError, ValueError):
            repair = messages + [
                {"role": "assistant", "content": text[:2000]},
                {"role": "user", "content": "Return the same answer as valid JSON only, no markdown fence."},
            ]
            repaired = self.chat(repair, 0.0, timeout=timeout)
            return extract_json(repaired)

    def chat_json(
        self,
        messages: list[dict[str, Any]],
        temperature: float = 0.2,
        *,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(MAX_AI_ATTEMPTS):
            try:
                return self._chat_json_once(messages, temperature, timeout=timeout)
            except (json.JSONDecodeError, ValueError) as exc:
                last_error = exc
                if attempt < MAX_AI_ATTEMPTS - 1:
                    time.sleep(_retry_delay(attempt))
                    continue
        raise AiUnavailable(f"模型返回的不是合法 JSON（已重试 {MAX_AI_ATTEMPTS} 次）: {last_error}")

    def understand(
        self,
        images: Sequence[ImageInput],
        hint: str = "",
        *,
        timeout: float | None = None,
    ) -> Understanding:
        if not images:
            raise AiUnavailable("没有图片可供识别")
        content: list[dict[str, Any]] = [{"type": "text", "text": UNDERSTAND_PROMPT}]
        if hint:
            content.append({"type": "text", "text": f"Seller note (may be Chinese): {hint}"})
        for image in images[:6]:
            content.append({"type": "image_url", "image_url": {"url": image.as_data_url()}})
        payload = self.chat_json([{"role": "user", "content": content}], timeout=timeout)
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
        payload = self.chat_json([{"role": "user", "content": prompt}], temperature=0.2)
        faqs = []
        for item in payload.get("faqs") or []:
            if isinstance(item, Mapping) and item.get("question") and item.get("answer"):
                faqs.append({"question": str(item["question"]), "answer": str(item["answer"])})
        raw = Copy(
            title=str(payload.get("title") or "").strip(),
            keywords=_str_list(payload.get("keywords"))[:keyword_count],
            highlights=str(payload.get("highlights") or "").strip(),
            selling_points=_str_list(payload.get("selling_points")),
            faqs=faqs,
            confidence=_confidence(payload.get("confidence")),
        )
        brand = str((extra_facts or {}).get("brand") or "").strip()
        return sanitize_copy(raw, title_limit=title_limit, keyword_count=keyword_count, brand=brand)

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
