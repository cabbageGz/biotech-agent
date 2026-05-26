from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from tools.image import CoverImage
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


class FakeImageClient:
    model = "fake-image"
    size = "1024*1024"

    def generate(self, prompt, output_path, size=None):
        output_path.write_bytes(b"fake")
        return CoverImage(
            prompt=prompt,
            model=self.model,
            size=size or self.size,
            image_url="https://example.com/fake.png",
            local_path=str(output_path),
        )


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
            self.assertTrue((run_dir / "ceo_decision.md").exists())
            self.assertTrue((run_dir / "research_report.md").exists())
            self.assertTrue((run_dir / "xiaohongshu_post.md").exists())
            self.assertEqual(payload["research"]["total_items"], 2)
            self.assertEqual(len(payload["research"]["source_items"]), 2)
            self.assertEqual(payload["item_posts"], [])
            self.assertIn("ceo_decision", payload)
            self.assertGreaterEqual(payload["ceo_decision"]["generate_count"], 1)
            self.assertTrue(payload["research"]["hotspots"][0]["selected"])
            self.assertIn("ceo_reason", payload["research"]["hotspots"][0])
            self.assertIn("total_score", payload["research"]["hotspots"][0])
            payload = flow.generate_posts_for_run(payload["run_id"], indices=[0])
            self.assertTrue(payload["item_posts"][0]["hashtags"])
            payload = flow.reorder_publish_for_run(payload["run_id"], order=[0])
            self.assertEqual(payload["publish_order"], [0])
            payload = flow.review_post_for_run(payload["run_id"], source_index=0)
            self.assertIn("review", payload["item_posts"][0])
            self.assertIn(payload["item_posts"][0]["review"]["publish_status"], {"pass", "revise", "block"})
            payload = flow.revise_post_for_run(payload["run_id"], source_index=0)
            self.assertIn("review", payload["item_posts"][0])
            self.assertIn("不构成医疗或投资建议", payload["item_posts"][0]["body"])
            self.assertEqual(len(payload["item_covers"]), 1)
            self.assertEqual(payload["item_covers"][0]["source_index"], 0)
            payload = flow.generate_cover_prompts_for_run(payload["run_id"], index=0, image_size="1024*1024")
            self.assertTrue(payload["item_covers"][0]["prompt_options"])
            self.assertGreaterEqual(len(payload["item_covers"][0]["prompt_options"]), 3)
            self.assertEqual(payload["item_covers"][0]["prompt_options"][0]["image_role"], "cover")
            self.assertEqual(payload["item_covers"][0]["prompt_options"][1]["image_role"], "content_card")
            self.assertGreaterEqual(payload["item_covers"][0]["image_plan"]["recommended_count"], 3)
            self.assertIn("文字", payload["item_covers"][0]["prompt"])
            self.assertIn(
                "不构成医疗或投资建议",
                (run_dir / "xiaohongshu_post.md").read_text(encoding="utf-8"),
            )

    def test_auto_publish_pipeline_generates_preview_assets(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            flow = XiaohongshuDailyFlow(storage=RunStorage(root))
            flow.research_agent.rss_reader = FakeRSSReader()
            flow.research_agent.pubmed_client = EmptyApiClient()
            flow.research_agent.clinical_trials_client = EmptyApiClient()
            flow.research_agent.fda_client = EmptyApiClient()
            flow.image_client = FakeImageClient()

            payload = flow.run_auto_publish(topic_hint="AI 制药", max_hotspots=2, publish_count=1, max_images_per_post=2)

            self.assertEqual(payload["auto_pipeline"]["generated_posts"], 1)
            self.assertGreaterEqual(payload["auto_pipeline"]["generated_images"], 2)
            self.assertEqual(len(payload["item_posts"]), 1)
            self.assertIn("review", payload["item_posts"][0])
            self.assertGreaterEqual(len(payload["item_covers"][0]["images"]), 2)


if __name__ == "__main__":
    unittest.main()
