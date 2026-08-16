import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from gop_client import sign_gop_request, to_api_path


class GopSignTests(unittest.TestCase):
    def test_official_sha256_example(self) -> None:
        # jaq-doc article 121120, /order/get example
        params = {
            "access_token": "test",
            "app_key": "123456",
            "order_id": "1234",
            "sign_method": "sha256",
            "timestamp": "1517820392000",
        }
        self.assertEqual(
            sign_gop_request("/order/get", params, "helloworld"),
            "4190D32361CFB9581350222F345CB77F3B19F0E31D162316848A2C1FFD5FAB4A",
        )

    def test_dotted_method_to_path(self) -> None:
        self.assertEqual(to_api_path("alibaba.icbu.product.list"), "/alibaba/icbu/product/list")
        self.assertEqual(to_api_path("/alibaba/icbu/product/list"), "/alibaba/icbu/product/list")


if __name__ == "__main__":
    unittest.main()
