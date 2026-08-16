"""End-to-end dry run: photo in, schema-valid draft out.

Nothing is published. The script stops right before `schema.add` and prints the
document that would have been submitted, so the whole pipeline can be checked
against a live shop without creating a listing.

    set -a && source .env && set +a
    python3 backend/smoke_draft.py path/to/photo.jpg [more.jpg ...]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai import AiClient, ImageInput  # noqa: E402
from schema import build_item_param, parse_schema  # noqa: E402

from server.db import SessionLocal, init_db  # noqa: E402
from server.models import Shop, User  # noqa: E402
from server.services import catalog, pipeline  # noqa: E402
from server.services.images import BankImage  # noqa: E402
from server.services.shop_client import shop_api  # noqa: E402


def main(paths: list[str]) -> int:
    init_db()
    db = SessionLocal()
    try:
        user = db.query(User).first()
        shop = db.query(Shop).filter(Shop.user_id == user.id).first() if user else None
        if shop is None:
            print("先在网页里注册并「接入环境店铺」，或跑 tests 生成数据")
            return 1

        api = shop_api(shop)
        ai = AiClient.from_env_or_none()
        print(f"店铺: {shop.name}  AI: {'on' if ai else 'off'}")

        uploads = [ImageInput(filename=Path(p).name, content=Path(p).read_bytes()) for p in paths]
        understanding, error = pipeline.understand(ai, uploads, "")
        if error:
            print("识别失败:", error)
            return 1
        print("识别:", json.dumps(understanding.raw, ensure_ascii=False)[:400])

        # Reuse whatever is already in the shop's image bank instead of
        # uploading test pictures into a real seller's account.
        listed = ((api.list_images(0, 1, len(uploads)).get("result") or {}).get("pagination_query_list") or {}).get("list") or []
        bank = [BankImage(file_name=i.get("file_name", ""), file_id=str(i.get("id")), url=i.get("url", "")) for i in listed]
        print(f"复用图片银行里的 {len(bank)} 张图")

        result = pipeline.build_draft(
            db,
            api,
            shop,
            understanding=understanding,
            images=bank,
            price="1.80",
            moq="500",
            defaults={"origin": "China", "priceUnit": "Piece/Pieces"},
            ai=ai,
        )

        print(f"\n类目: {result.category_name} ({result.category_id}) 置信度 {result.category_confidence:.0%}")
        print(f"状态: {result.status}")
        print("标题:", result.title)
        for issue in result.issues:
            print(f"  [{issue['level']}] {issue.get('field_name')}: {issue['message']}")

        if result.category_id:
            xml = catalog.get_schema_xml(db, api, result.category_id)
            document = build_item_param(parse_schema(xml), result.values)
            print("\n将要提交的 itemParam（未发布）:")
            print(document[:2500])
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:] or []))
