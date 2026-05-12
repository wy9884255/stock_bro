from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from stock_bro.cls import fetch_cls_limit_up_analysis, write_json


class ClsTests(unittest.TestCase):
    def test_fetch_cls_limit_up_analysis_extracts_article_metadata(self) -> None:
        import stock_bro.cls as cls

        original = cls.fetch_cls_html
        cls.fetch_cls_html = lambda url, timeout=15.0: """
            <html>
              <head><title>5月12日涨停分析|财联社</title></head>
              <body>
                2026年05月12日 15:49:17
                财联社5月12日电，今日共55股涨停，12股炸板，封板率为82%。
                <img src="https://image.cls.cn/images/20260512/example_1000x15944.jpg">
                关联个股 金螳螂 +10.07% 航天科技 +10.01%
              </body>
            </html>
        """
        try:
            analysis = fetch_cls_limit_up_analysis("https://www.cls.cn/detail/2368985")
        finally:
            cls.fetch_cls_html = original

        self.assertEqual(analysis.trade_date, "2026-05-12")
        self.assertEqual(analysis.title, "5月12日涨停分析")
        self.assertEqual(analysis.published_at, "2026年05月12日 15:49:17")
        self.assertEqual(len(analysis.images), 1)
        self.assertEqual(len(analysis.classification_images), 1)
        self.assertEqual(analysis.related_stocks[0].name, "金螳螂")

    def test_write_json_uses_trade_date_suffix(self) -> None:
        import stock_bro.cls as cls

        original = cls.fetch_cls_html
        cls.fetch_cls_html = lambda url, timeout=15.0: """
            <html><head><title>5月12日涨停分析</title></head><body></body></html>
        """
        try:
            analysis = fetch_cls_limit_up_analysis("https://www.cls.cn/detail/2368985")
        finally:
            cls.fetch_cls_html = original

        with tempfile.TemporaryDirectory() as tmp:
            path = write_json(analysis, Path(tmp))
            data = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(path.name, "20260512_limit_up_analysis.json")
        self.assertEqual(data["title"], "5月12日涨停分析")


if __name__ == "__main__":
    unittest.main()
