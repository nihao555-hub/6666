"""Photobank upload.

Alibaba rejects listings that point at images outside the seller's own image
bank, so every picture we receive is uploaded first and the returned
`photobank_url` + `file_id` pair is what goes into the schema.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from icbu_api import IcbuApi  # noqa: E402


@dataclass
class BankImage:
    file_name: str
    file_id: str
    url: str

    @property
    def absolute_url(self) -> str:
        if self.url.startswith("//"):
            return f"https:{self.url}"
        return self.url

    def as_dict(self) -> dict[str, str]:
        return {"file_name": self.file_name, "file_id": self.file_id, "url": self.url, "preview": self.absolute_url}

    def as_schema_value(self) -> dict[str, Any]:
        return {"$value": self.url, "$attrs": {"fileId": self.file_id, "fileFlag": "no"}}


def parse_upload(payload: dict[str, Any]) -> BankImage | None:
    obj = ((payload or {}).get("result") or {}).get("response_object") or {}
    url = obj.get("photobank_url") or obj.get("url") or ""
    if not url:
        return None
    return BankImage(
        file_name=str(obj.get("file_name") or ""),
        file_id=str(obj.get("file_id") or ""),
        url=str(url),
    )


def upload(api: IcbuApi, file_name: str, content: bytes, group_id: str | None = None) -> BankImage:
    image = parse_upload(api.upload_image(file_name, content, group_id))
    if image is None:
        raise RuntimeError(f"图片 {file_name} 上传图片银行失败")
    return image


def from_dict(raw: dict[str, Any]) -> BankImage:
    return BankImage(
        file_name=str(raw.get("file_name") or ""),
        file_id=str(raw.get("file_id") or ""),
        url=str(raw.get("url") or ""),
    )
