import sys
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from top_client import SIGN_MD5, china_timestamp, sign_top_request


class SignTests(unittest.TestCase):
    def test_official_md5_example(self) -> None:
        # https://developer.alibaba.com/docs/doc.htm?articleId=101617&docType=1
        params = {
            "method": "taobao.item.seller.get",
            "app_key": "12345678",
            "session": "test",
            "timestamp": "2016-01-01 12:00:00",
            "format": "json",
            "v": "2.0",
            "sign_method": "md5",
            "fields": "num_iid,title,nick,price,num",
            "num_iid": "11223344",
        }
        self.assertEqual(
            sign_top_request(params, "helloworld", SIGN_MD5),
            "66987CB115214E59E6EC978214934FB8",
        )

    def test_china_timestamp(self) -> None:
        now = datetime(2016, 1, 1, 4, 0, 0, tzinfo=ZoneInfo("UTC"))
        self.assertEqual(china_timestamp(now), "2016-01-01 12:00:00")


if __name__ == "__main__":
    unittest.main()
