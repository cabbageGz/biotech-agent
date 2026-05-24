from __future__ import annotations

from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Any

from agents.ceo_agent import CEOAgent
from agents.content_agent import ContentAgent
from agents.research_agent import ResearchAgent
from tools.image import WanxiangClient
from workflows.storage import RunStorage


class XiaohongshuDailyFlow:
    def __init__(self, storage: RunStorage | None = None) -> None:
        self.storage = storage or RunStorage()
        self.ceo_agent = CEOAgent()
        self.research_agent = ResearchAgent()
        self.content_agent = ContentAgent()
        self.image_client = WanxiangClient()

    def run(
        self,
        target_date: date | None = None,
        topic_hint: str = "",
        max_items: int = 24,
        max_hotspots: int = 6,
    ) -> dict[str, Any]:
        target = target_date or date.today()
        run_dir = self.storage.new_run_dir()
        brief = self.ceo_agent.create_daily_brief(target_date=target, topic_hint=topic_hint)
        report = self.research_agent.collect(max_items=max_items, max_hotspots=max_hotspots)
        post = self.content_agent.create_post(report)
        cover_prompt = self._cover_prompt(post=post, report=report)
        cover = self.image_client.generate(prompt=cover_prompt, output_path=run_dir / "cover.png")
        files = {
            "ceo_brief.md": self.ceo_agent.render_markdown(brief),
            "research_report.md": self.research_agent.render_markdown(report),
            "xiaohongshu_post.md": self.content_agent.render_markdown(post),
            "cover_prompt.md": cover_prompt + "\n",
        }
        payload = {
            "target_date": target.isoformat(),
            "topic_hint": topic_hint,
            "brief": brief.to_dict(),
            "research": report.to_dict(),
            "post": post.to_dict(),
            "cover": cover.to_dict(),
        }
        return self.storage.write_run(run_dir=run_dir, payload=payload, files=files)

    def generate_cover_for_run(self, run_id: str) -> dict[str, Any]:
        run = self.storage.read_run(run_id)
        run_dir = self.storage.root / run_id
        post_payload = run.get("post") or {}
        report_payload = run.get("research") or {}
        post_title = str(post_payload.get("title") or "今日生物医药热点")
        post_body = str(post_payload.get("body") or run.get("file_contents", {}).get("xiaohongshu_post.md") or "")
        keywords = self._keywords_from_report(report_payload)
        cover_prompt = self._cover_prompt_from_text(title=post_title, body=post_body, keywords=keywords)
        cover = self.image_client.generate(prompt=cover_prompt, output_path=run_dir / "cover.png")
        return self.storage.update_run(
            run_id=run_id,
            updates={"cover": cover.to_dict()},
            files={"cover_prompt.md": cover_prompt + "\n"},
        )

    def _cover_prompt(self, post: Any, report: Any) -> str:
        keywords: list[str] = []
        for item in report.hotspots[:4]:
            for tag in item.tags:
                if tag not in keywords:
                    keywords.append(tag)
        title = post.title.replace("#", "").strip()
        keyword_text = "、".join(keywords[:4]) or "创新药、临床进展、交易合作"
        return (
            self._cover_prompt_from_text(title=title, body=post.body, keywords=keyword_text)
        )

    def _keywords_from_report(self, report_payload: dict[str, Any]) -> str:
        keywords: list[str] = []
        for item in report_payload.get("hotspots", [])[:4]:
            if not isinstance(item, dict):
                continue
            for tag in item.get("tags", []):
                if tag not in keywords:
                    keywords.append(str(tag))
        return "、".join(keywords[:4]) or "创新药、临床进展、交易合作"

    def _cover_prompt_from_text(self, title: str, body: str, keywords: str) -> str:
        body_excerpt = " ".join(body.split())[:260]
        return (
            "生成一张适合小红书首图的生物医药行业热点封面，1:1 方图，中文信息图风格。"
            f"主标题：{title}。关键词：{keywords}。"
            f"正文主题参考：{body_excerpt}。"
            "画面需要专业、清爽、有科技感，包含抽象分子结构、药物研发数据面板、临床进展时间线元素。"
            "不要出现真实药品包装、真实患者、疗效承诺、投资收益暗示。"
            "留出清晰标题区域，适合后期叠加中文文字。"
        )


def run_once(root: Path | str = "database/runs", topic_hint: str = "") -> dict[str, Any]:
    return XiaohongshuDailyFlow(storage=RunStorage(root)).run(topic_hint=topic_hint)
