"""Local 5.0 gate matches official quality buckets."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from schema import SchemaField, SchemaOption, SchemaRule  # noqa: E402
from server.services.pipeline import apply_content, apply_trade_terms  # noqa: E402
from server.services.quality import score_listing  # noqa: E402
from server.services.images import BankImage  # noqa: E402
from ai import Copy, Understanding  # noqa: E402


def _option_field(field_id: str, label: str, value: str = "1") -> SchemaField:
    return SchemaField(
        id=field_id,
        name=field_id,
        type="singleCheck",
        options=[SchemaOption(value=value, display_name=label)],
    )


class QualityTests(unittest.TestCase):
    def test_complete_evidence_scores_five(self) -> None:
        fields = [
            _option_field("priceUnit", "Piece/Pieces", "17"),
            _option_field("saleType", "Unit", "u"),
            _option_field("scPrice", "Tiered pricing by quantity", "t"),
            _option_field("paymentMethod", "T/T", "tt"),
            _option_field("port", "Ningbo", "nb"),
            SchemaField(id="ladderPeriod", name="发货期", type="complex"),
            SchemaField(id="shippingTemplate", name="运费", type="complex"),
            _option_field("logisticsProperty", "普货", "n"),
            SchemaField(id="pkgWeight", name="重量", type="input"),
            SchemaField(id="pkgMeasure", name="尺寸", type="complex"),
            _option_field("marketSample", "Unavailable", "s"),
            SchemaField(id="superText", name="详描", type="input"),
            SchemaField(id="detailImage", name="详情图", type="multiComplex"),
            SchemaField(id="companyFaqDesc", name="FAQ", type="multiComplex"),
            SchemaField(id="productTitle", name="标题", type="input"),
            SchemaField(id="productKeywords", name="词", type="complex"),
            SchemaField(id="textDesc", name="描述", type="input"),
            SchemaField(
                id="icbuCatProp",
                name="属性",
                type="complex",
                children=[
                    SchemaField(
                        id="p-1",
                        name="原产地",
                        type="singleCheck",
                        rules=[SchemaRule(name="requiredRule", value="true")],
                    )
                ],
            ),
        ]
        values = {
            "catId": "21110712",
            "productTitle": "Colored Pencil Set for Students",
            "productKeywords": {"productKeywords_0": "colored pencil", "productKeywords_1": "school pencil", "productKeywords_2": "drawing set"},
            "icbuCatProp": {"p-1": "100000458"},
            "priceUnit": "17",
            "saleType": "u",
            "scPrice": "t",
            "ladderPrice": {"ladderPrice_0": {"quantity": "500", "price": "1.80"}},
            "minOrderQuantity": "500",
            "paymentMethod": ["tt"],
            "port": "nb",
            "ladderPeriod": {"ladderPeriod_0": {"quantity": "500", "period": "15"}},
            "shippingTemplate": {"templateType": "FREIGHT_NEGOTIATION"},
            "logisticsProperty": ["n"],
            "pkgWeight": "0.5",
            "pkgMeasure": {"length": "20", "width": "10", "height": "5"},
            "marketSample": "s",
            "textDesc": "Student colored pencil set for classroom and homework use.",
            "superText": "<p>Student colored pencil set</p>",
            "detailImage": [{"gallery": "1"}],
            "companyFaqDesc": [{"question": "MOQ?", "answers": "500"}],
        }
        report = score_listing(
            values=values,
            fields=fields,
            image_count=4,
            price="1.80",
            moq="500",
            category_id="21110712",
        )
        self.assertTrue(report["ready"], report["missing"])
        self.assertEqual(report["score"], 5.0)

    def test_one_photo_cannot_reach_five(self) -> None:
        report = score_listing(
            values={"productTitle": "Brush", "productKeywords": {"a": "paint brush", "b": "wall brush", "c": "decorating"}, "icbuCatProp": {"p-1": "1"}, "textDesc": "x"},
            image_count=1,
            price="1.8",
            moq="500",
            category_id="21111112",
        )
        self.assertFalse(report["ready"])
        self.assertIn("实拍图至少 3 张", report["missing"])

    def test_quality_issue_is_red(self) -> None:
        from server.services.quality import quality_issue

        issue = quality_issue({"ready": False, "score": 4.2, "missing": ["英文标题"]})
        self.assertIsNotNone(issue)
        self.assertEqual(issue["level"], "red")
        self.assertIn("4.2", issue["message"])

    def test_trade_defaults_are_applied_from_shop_not_invented(self) -> None:
        specs = {
            "priceUnit": _option_field("priceUnit", "Piece/Pieces", "17"),
            "saleType": _option_field("saleType", "Unit", "u"),
            "scPrice": _option_field("scPrice", "Tiered pricing by quantity", "t"),
            "paymentMethod": SchemaField(
                id="paymentMethod",
                name="付款",
                type="multiCheck",
                options=[SchemaOption(value="tt", display_name="T/T"), SchemaOption(value="wu", display_name="Western Union")],
            ),
            "port": _option_field("port", "Ningbo", "nb"),
            "ladderPeriod": SchemaField(
                id="ladderPeriod",
                name="发货期",
                type="complex",
                children=[
                    SchemaField(
                        id="ladderPeriod_0",
                        name="",
                        type="complex",
                        children=[
                            SchemaField(id="quantity", name="quantity", type="input"),
                            SchemaField(id="period", name="period", type="input"),
                        ],
                    )
                ],
            ),
        }
        values: dict = {}
        apply_trade_terms(
            specs,
            values,
            {"priceUnit": "Piece/Pieces", "paymentMethod": "T/T, Western Union", "port": "Ningbo", "ladderPeriod": "15"},
            "1.80",
            "500",
        )
        self.assertEqual(values["paymentMethod"], ["tt", "wu"])
        self.assertEqual(values["port"], "nb")
        self.assertEqual(values["ladderPeriod"]["ladderPeriod_0"]["period"], "15")
        self.assertEqual(values["ladderPeriod"]["ladderPeriod_0"]["quantity"], "500")

    def test_logistics_attributes_match_by_official_value_and_allow_several(self) -> None:
        """«普货» only comes back on zh calls; the value is what is stable."""
        specs = {
            "logisticsProperty": SchemaField(
                id="logisticsProperty",
                name="Logistics attribute",
                type="multiCheck",
                options=[
                    SchemaOption(value="general_cargo_0", display_name="Ordinary goods"),
                    SchemaOption(value="battery.pureBattery", display_name="Pure battery"),
                ],
            )
        }
        english: dict = {}
        apply_trade_terms(specs, english, {"logisticsProperty": "general_cargo_0"}, "1.80", "500")
        self.assertEqual(english["logisticsProperty"], ["general_cargo_0"])

        several: dict = {}
        apply_trade_terms(specs, several, {"logisticsProperty": "general_cargo_0,battery.pureBattery"}, "1.80", "500")
        self.assertEqual(several["logisticsProperty"], ["general_cargo_0", "battery.pureBattery"])

    def test_super_text_and_faq_come_from_evidence(self) -> None:
        specs = {
            "productTitle": SchemaField(id="productTitle", name="t", type="input"),
            "productKeywords": SchemaField(id="productKeywords", name="k", type="complex"),
            "textDesc": SchemaField(id="textDesc", name="d", type="input"),
            "superText": SchemaField(id="superText", name="s", type="input"),
            "companyFaqDesc": SchemaField(id="companyFaqDesc", name="f", type="multiComplex"),
            "detailImage": SchemaField(
                id="detailImage",
                name="img",
                type="multiComplex",
                children=[SchemaField(id="gallery", name="gallery", type="singleCheck")],
            ),
            "scImages": SchemaField(id="scImages", name="sc", type="complex"),
        }
        copy = Copy(
            title="Paint Brush Set",
            keywords=["paint brush", "wall brush", "decorating"],
            highlights="Natural bristle wall brush for contractors.",
            selling_points=["Natural bristle", "Wooden handle"],
            faqs=[{"question": "Can I order a sample?", "answer": "Yes, sample policy follows the shop default."}],
        )
        understanding = Understanding(material="bristle", colors=["black"], specs={"Size": "2 inch"})
        values: dict = {}
        apply_content(
            specs,
            values,
            copy.title,
            copy.keywords,
            copy.highlights,
            [BankImage("a.jpg", "fid-1", "//img/a.jpg")],
            copy=copy,
            understanding=understanding,
        )
        self.assertIn("Natural bristle", values["superText"])
        self.assertNotIn("CE", values["superText"])
        self.assertEqual(values["companyFaqDesc"][0]["question"], "Can I order a sample?")
        self.assertEqual(values["detailImage"][0]["images"][0]["$attrs"]["fileId"], "fid-1")


if __name__ == "__main__":
    unittest.main()
