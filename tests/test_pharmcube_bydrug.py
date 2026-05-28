from __future__ import annotations

import unittest

from tools.pharmcube import PharmcubeByDrugClient


class PharmcubeByDrugClientTest(unittest.TestCase):
    def test_parse_homepage_reads_public_news_and_reports(self) -> None:
        html = """
        <html><body><script>
        window.__NUXT__=(function(a,b,c,M,N,T){return {data:[{
        reportListPCList:[{fileName:"报告标题",resource:M,publishDate:N,esid:"report123",report_subtitle:"<p>报告摘要</p>"}],
        newsPCList:[{abstracts:"新闻摘要",esid:"news123",title:"新闻标题",resource:T,publishTime:N,tags:["ADC","出海"]}]
        }]}}(null,"","否","医药魔方","2026-05-28 22:11","医药速览"));
        </script></body></html>
        """

        items = PharmcubeByDrugClient().parse_homepage(html, max_items=10)

        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].title, "新闻标题")
        self.assertEqual(items[0].source, "医药魔方 ByDrug / 医药速览")
        self.assertEqual(items[0].published, "2026-05-28 22:11")
        self.assertEqual(items[0].link, "https://bydrug.pharmcube.com/news/detail/news123")
        self.assertIn("ADC", items[0].summary)
        self.assertEqual(items[1].title, "报告标题")
        self.assertEqual(items[1].source, "医药魔方报告 / 医药魔方")
        self.assertEqual(items[1].link, "https://bydrug.pharmcube.com/report/detail/report123")
        self.assertEqual(items[1].summary, "报告摘要")

    def test_parse_homepage_ignores_missing_nuxt_lists(self) -> None:
        items = PharmcubeByDrugClient().parse_homepage("<html></html>", max_items=10)

        self.assertEqual(items, [])


if __name__ == "__main__":
    unittest.main()
