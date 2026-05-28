from __future__ import annotations

import unittest

from tools.wuxi.apptec import WuXiAppTecClient, WuXiSection


class WuXiAppTecClientTest(unittest.TestCase):
    def test_parse_listing_reads_news_cards(self) -> None:
        html = """
        <div class="list">
          <div class="list-item" data-v-55c3730e>
            <p class="date" data-v-55c3730e>2026/05/18</p>
            <h1 class="title" data-v-55c3730e>药明康德入选2026道琼斯领先全球指数</h1>
            <p class="content" data-v-55c3730e>上海，2026年5月18日 - 药明康德近日宣布公司入选指数。</p>
            <a href="/news/wuxi-news/v1bj6wuxvxdn4a55fcsnwt38" class="link" data-v-55c3730e>阅读更多</a>
          </div>
        </div>
        """
        section = WuXiSection(
            url="https://www.wuxiapptec.cn/news/wuxi-news",
            source="药明康德 / 公司新闻",
        )

        items = WuXiAppTecClient().parse_listing(html, section=section)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].title, "药明康德入选2026道琼斯领先全球指数")
        self.assertEqual(items[0].published, "2026-05-18")
        self.assertEqual(items[0].source, "药明康德 / 公司新闻")
        self.assertEqual(
            items[0].link,
            "https://www.wuxiapptec.cn/news/wuxi-news/v1bj6wuxvxdn4a55fcsnwt38",
        )
        self.assertIn("药明康德近日宣布", items[0].summary)


if __name__ == "__main__":
    unittest.main()
