from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from tools.rss.reader import RSSItem
from workflows.storage import RunStorage
from workflows.xiaohongshu_flow import XiaohongshuDailyFlow


class FakeRSSReader:
    def fetch_many(self, max_items: int = 24):
        return [
            RSSItem(
                title="Lilly oncology drug reaches Phase 3 endpoint",
                link="https://example.com/lilly-phase-3",
                summary="A clinical trial update with oncology and regulatory implications.",
                source="Example Bio",
                published="2026-05-24",
            ),
            RSSItem(
                title="Big pharma signs AI drug discovery collaboration",
                link="https://example.com/ai-deal",
                summary="The licensing deal expands AI discovery capabilities.",
                source="Example Bio",
                published="2026-05-24",
            ),
            RSSItem(
                title="Old biotech financing story from 2024",
                link="https://example.com/old-story",
                summary="This stale item should not be used for today's topic selection.",
                source="Example Bio",
                published="2024-05-24",
            ),
        ], []


class EmptyApiClient:
    def search_recent(self, *args, **kwargs):
        return []

    def recent_drug_approvals(self, *args, **kwargs):
        return []


class XiaohongshuFlowTest(unittest.TestCase):
    def test_flow_generates_publishable_files(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            flow = XiaohongshuDailyFlow(storage=RunStorage(root))
            flow.research_agent.rss_reader = FakeRSSReader()
            flow.research_agent.pubmed_client = EmptyApiClient()
            flow.research_agent.clinical_trials_client = EmptyApiClient()
            flow.research_agent.fda_client = EmptyApiClient()

            payload = flow.run(topic_hint="AI 制药", max_hotspots=2)

            run_dir = root / payload["run_id"]
            self.assertTrue((run_dir / "ceo_brief.md").exists())
            self.assertTrue((run_dir / "research_report.md").exists())
            self.assertTrue((run_dir / "xiaohongshu_post.md").exists())
            self.assertEqual(payload["research"]["total_items"], 2)
            self.assertEqual(len(payload["research"]["source_items"]), 2)
            self.assertEqual(payload["item_posts"], [])
            self.assertIn("total_score", payload["research"]["hotspots"][0])
            payload = flow.generate_posts_for_run(payload["run_id"], indices=[0])
            self.assertTrue(payload["item_posts"][0]["hashtags"])
            self.assertEqual(len(payload["item_covers"]), 1)
            self.assertEqual(payload["item_covers"][0]["source_index"], 0)
            payload = flow.generate_cover_prompts_for_run(payload["run_id"], index=0, image_size="1024*1024")
            self.assertTrue(payload["item_covers"][0]["prompt_options"])
            self.assertIn("文字", payload["item_covers"][0]["prompt"])
            self.assertIn(
                "不构成医疗或投资建议",
                (run_dir / "xiaohongshu_post.md").read_text(encoding="utf-8"),
            )


if __name__ == "__main__":
    unittest.main()
