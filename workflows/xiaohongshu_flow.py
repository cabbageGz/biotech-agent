from __future__ import annotations

from dataclasses import asdict
from datetime import date
from pathlib import Path
import re
from typing import Any

from agents.ceo_agent import CEOAgent
from agents.content_agent import ContentAgent
from agents.research_agent import ResearchAgent
from tools.image import CoverImage, WanxiangClient
from tools.xhs import XiaohongshuReferenceExtractor
from workflows.storage import RunStorage


DEFAULT_XHS_REFERENCE_URL = "http://xhslink.com/o/EW8pABb9aG"
IMAGE_SIZE_LABELS = {
    "1024*1024": "1:1 方图",
    "768*1024": "3:4 竖图",
    "1024*768": "4:3 横图",
    "720*1280": "9:16 竖屏",
    "1280*720": "16:9 横屏",
}


class XiaohongshuDailyFlow:
    def __init__(self, storage: RunStorage | None = None) -> None:
        self.storage = storage or RunStorage()
        self.ceo_agent = CEOAgent()
        self.research_agent = ResearchAgent()
        self.content_agent = ContentAgent()
        self.image_client = WanxiangClient()
        self.reference_extractor = XiaohongshuReferenceExtractor()

    def run(
        self,
        target_date: date | None = None,
        topic_hint: str = "",
        max_items: int = 24,
        max_hotspots: int = 6,
        reference_url: str = "",
        content_words: int = 700,
        content_instruction: str = "",
        format_reference: str = "",
        user_id: int | None = None,
        username: str = "",
    ) -> dict[str, Any]:
        target = target_date or date.today()
        run_dir = self.storage.new_run_dir()
        brief = self.ceo_agent.create_daily_brief(target_date=target, topic_hint=topic_hint)
        reference = self.reference_extractor.fetch(reference_url or DEFAULT_XHS_REFERENCE_URL)
        report = self.research_agent.collect(max_items=max_items, max_hotspots=max_hotspots)
        item_posts = self.content_agent.create_posts(
            report,
            style_reference=reference.to_dict() if reference else {},
            content_options={
                "content_words": content_words,
                "content_instruction": content_instruction,
                "format_reference": format_reference,
            },
        )
        post = item_posts[0] if item_posts else self.content_agent.create_post(report)
        cover_prompt = self._cover_prompt(post=post, report=report)
        cover = CoverImage(prompt=cover_prompt, model=self.image_client.model, size=self.image_client.size)
        files = {
            "ceo_brief.md": self.ceo_agent.render_markdown(brief),
            "research_report.md": self.research_agent.render_markdown(report),
            "xiaohongshu_post.md": self.content_agent.render_posts_markdown(item_posts),
            "cover_prompt.md": cover_prompt + "\n",
        }
        payload = {
            "target_date": target.isoformat(),
            "topic_hint": topic_hint,
            "user_id": user_id,
            "username": username,
            "content_options": {
                "content_words": content_words,
                "content_instruction": content_instruction,
                "format_reference": format_reference,
            },
            "brief": brief.to_dict(),
            "research": report.to_dict(),
            "post": post.to_dict(),
            "item_posts": [item.to_dict() for item in item_posts],
            "cover": cover.to_dict(),
            "item_covers": self._empty_item_covers(report.to_dict(), [item.to_dict() for item in item_posts]),
        }
        return self.storage.write_run(run_dir=run_dir, payload=payload, files=files)

    def generate_cover_for_run(
        self,
        run_id: str,
        index: int | None = None,
        image_size: str | None = None,
        image_instruction: str = "",
    ) -> dict[str, Any]:
        run = self.storage.read_run(run_id)
        run_dir = self.storage.root / run_id
        selected_size = self._normalize_image_size(image_size)
        if index is not None:
            return self._generate_item_cover(
                run=run,
                run_dir=run_dir,
                index=index,
                image_size=selected_size,
                image_instruction=image_instruction,
            )
        post_payload = run.get("post") or {}
        report_payload = run.get("research") or {}
        post_title = str(post_payload.get("title") or "今日生物医药热点")
        post_body = str(post_payload.get("body") or run.get("file_contents", {}).get("xiaohongshu_post.md") or "")
        keywords = self._keywords_from_report(report_payload)
        cover_prompt = self._cover_prompt_from_text(
            title=post_title,
            body=post_body,
            keywords=keywords,
            image_size=selected_size,
        )
        cover = self.image_client.generate(prompt=cover_prompt, output_path=run_dir / "cover.png", size=selected_size)
        return self.storage.update_run(
            run_id=run_id,
            updates={"cover": cover.to_dict()},
            files={"cover_prompt.md": cover_prompt + "\n"},
        )

    def _generate_item_cover(
        self,
        run: dict[str, Any],
        run_dir: Path,
        index: int,
        image_size: str,
        image_instruction: str,
    ) -> dict[str, Any]:
        item_covers = self._item_covers_from_run(run)
        if index < 0 or index >= len(item_covers):
            raise ValueError("Invalid item index")
        item = item_covers[index]
        prompt = self._item_cover_prompt(
            item=item,
            post=run.get("post") or {},
            image_size=image_size,
            image_instruction=image_instruction,
        )
        filename = f"item_cover_{index + 1}.png"
        prompt_file = f"item_cover_{index + 1}_prompt.md"
        cover = self.image_client.generate(prompt=prompt, output_path=run_dir / filename, size=image_size)
        item_covers[index] = {
            **item,
            "prompt": prompt,
            "model": cover.model,
            "size": cover.size,
            "image_url": cover.image_url,
            "local_path": cover.local_path,
            "asset": filename if cover.local_path and not cover.error else "",
            "error": cover.error,
        }
        return self.storage.update_run(
            run_id=str(run["run_id"]),
            updates={"item_covers": item_covers},
            files={prompt_file: prompt + "\n"},
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

    def _cover_prompt_from_text(
        self,
        title: str,
        body: str,
        keywords: str,
        image_size: str | None = None,
    ) -> str:
        body_excerpt = " ".join(body.split())[:260]
        size_text = IMAGE_SIZE_LABELS.get(image_size or self.image_client.size, "小红书配图")
        return (
            f"生成一张适合小红书首图的生物医药行业热点封面，{size_text}，中文信息图风格。"
            f"主标题：{title}。关键词：{keywords}。"
            f"正文主题参考：{body_excerpt}。"
            "画面需要专业、清爽、有科技感，包含抽象分子结构、药物研发数据面板、临床进展时间线元素。"
            "不要出现真实药品包装、真实患者、疗效承诺、投资收益暗示。"
            "留出清晰标题区域，适合后期叠加中文文字。"
        )

    def _empty_item_covers(
        self,
        report_payload: dict[str, Any],
        item_posts: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        posts = item_posts or []
        for index, item in enumerate(report_payload.get("hotspots", []), start=1):
            post = posts[index - 1] if index - 1 < len(posts) else {}
            result.append(
                {
                    "index": index - 1,
                    "title": str(post.get("title") or item.get("title") or f"热点 {index}"),
                    "summary": str(post.get("body") or item.get("summary") or ""),
                    "why_it_matters": str(item.get("why_it_matters") or ""),
                    "source": str(item.get("source") or ""),
                    "url": str(item.get("url") or ""),
                    "published": str(item.get("published") or ""),
                    "tags": item.get("tags") or [],
                    "prompt": "",
                    "model": self.image_client.model,
                    "size": self.image_client.size,
                    "image_url": "",
                    "local_path": "",
                    "asset": "",
                    "error": "",
                }
            )
        return result

    def _item_covers_from_run(self, run: dict[str, Any]) -> list[dict[str, Any]]:
        existing = run.get("item_covers")
        if isinstance(existing, list) and existing:
            hotspots = (run.get("research") or {}).get("hotspots") or []
            posts = run.get("item_posts") or []
            enriched = []
            for index, item in enumerate(existing):
                hotspot = hotspots[index] if index < len(hotspots) and isinstance(hotspots[index], dict) else {}
                post = posts[index] if index < len(posts) and isinstance(posts[index], dict) else {}
                enriched.append(
                    {
                        **item,
                        "title": post.get("title") or item.get("title") or str(hotspot.get("title") or ""),
                        "summary": post.get("body") or item.get("summary") or str(hotspot.get("summary") or ""),
                        "source": item.get("source") or str(hotspot.get("source") or ""),
                        "url": item.get("url") or str(hotspot.get("url") or ""),
                        "published": item.get("published") or str(hotspot.get("published") or ""),
                    }
                )
            return enriched
        return self._empty_item_covers(run.get("research") or {}, run.get("item_posts") or [])

    def _item_cover_prompt(
        self,
        item: dict[str, Any],
        post: dict[str, Any],
        image_size: str,
        image_instruction: str,
    ) -> str:
        tag_list = [str(tag) for tag in item.get("tags", [])[:3]]
        tags = "、".join(tag_list) or "生物医药热点"
        title = str(item.get("title") or "生物医药热点")
        summary = str(item.get("summary") or "")
        why = str(item.get("why_it_matters") or "")
        source = str(item.get("source") or "公开信息")
        url = str(item.get("url") or "")
        published = str(item.get("published") or "")
        post_title = str(post.get("title") or "")
        size_text = IMAGE_SIZE_LABELS.get(image_size, "小红书配图")
        style_text = f"用户图片要求：{image_instruction}。" if image_instruction.strip() else ""
        display_title = self._short_visual_title(title)
        visual_labels = "、".join(tag_list[:3]) or "行业热点"
        info_blocks = self._visual_info_blocks(title=title, summary=summary, why=why, tags=tag_list)
        visual_scene = self._visual_scene_hint(title=title, summary=summary, tags=tag_list)
        fact_context = self._compact_fact_context(
            title=title,
            summary=summary,
            why=why,
            source=source,
            published=published,
            url=url,
        )
        return (
            f"为小红书正文中的单条生物医药热点生成一张配图，{size_text}。"
            "采用少字但有信息结构的医药信息图风格，不要做长文海报，也不要做空洞装饰图。"
            f"{style_text}"
            "画面文字白名单："
            f"主标题「{display_title}」；三个重点信息块「{info_blocks[0]}」「{info_blocks[1]}」「{info_blocks[2]}」；"
            f"角标/小标签「{visual_labels}」。"
            "除此之外不要再生成任何正文、段落、数据说明、来源链接、日期、脚注或密集小字。"
            "每个信息块只放 4-8 个中文字符，整张图中文字总量控制在 45 个中文字符以内。"
            "画面结构要求：顶部短标题，中间必须有清晰视觉中心，底部或侧边放三个短信息块；"
            f"视觉中心请表达：{visual_scene}。"
            "用箭头、流程线、节点、图标、对比卡片来表达重点信息，不要只放一个分子图或纯背景。"
            "事实背景仅供理解，不要把它排版进画面："
            f"{fact_context}"
            "事实准确性要求：如果画面出现公司名、药物名、阶段、比例、会议名、金额等具体信息，"
            "只能来自白名单文字；不要自行编造数值、曲线坐标、试验结果、监管结论、疗效、安全性或投资含义。"
            "可以使用无坐标示意曲线、流程图、机制图、药物研发管线图标，但不要写具体数值。"
            "不要出现真实患者、真实药盒、疗效承诺、投资收益暗示。"
        )

    def _short_visual_title(self, title: str) -> str:
        cleaned = re.sub(r"[#｜|:：\-—]+", " ", title)
        cleaned = " ".join(cleaned.split())
        return cleaned[:18] if len(cleaned) > 18 else cleaned

    def _compact_fact_context(
        self,
        title: str,
        summary: str,
        why: str,
        source: str,
        published: str,
        url: str,
    ) -> str:
        summary_text = " ".join(summary.split())[:220]
        why_text = " ".join(why.split())[:120]
        return (
            f"标题：{title}。摘要：{summary_text}。产业意义：{why_text}。"
            f"来源：{source or '公开信息'}；发布日期：{published or '未提供'}；链接：{url or '未提供'}。"
        )

    def _visual_info_blocks(self, title: str, summary: str, why: str, tags: list[str]) -> list[str]:
        text = f"{title} {summary} {why}".lower()
        blocks: list[str] = []
        if any(word in text for word in ["ai", "anthropic", "model", "算法", "人工智能"]):
            blocks.extend(["AI模型", "药物研发", "合作升级"])
        elif any(word in text for word in ["phase 3", "3期", "iii期", "clinical", "临床"]):
            blocks.extend(["临床进展", "关键节点", "管线信号"])
        elif any(word in text for word in ["deal", "licensing", "collaboration", "合作", "交易", "授权"]):
            blocks.extend(["交易合作", "资产价值", "赛道信号"])
        elif any(word in text for word in ["asco", "cancer", "oncology", "肿瘤"]):
            blocks.extend(["肿瘤数据", "会议前瞻", "管线竞争"])
        elif tags:
            blocks.extend(tags[:3])
        while len(blocks) < 3:
            blocks.append(["行业信号", "技术路线", "后续观察"][len(blocks)])
        return [self._short_label(item) for item in blocks[:3]]

    def _visual_scene_hint(self, title: str, summary: str, tags: list[str]) -> str:
        text = f"{title} {summary} {' '.join(tags)}".lower()
        if any(word in text for word in ["ai", "anthropic", "model", "人工智能"]):
            return "左侧药企建筑或BMS文字节点，右侧AI芯片/大模型节点，中间箭头指向药物分子和研发管线"
        if any(word in text for word in ["phase 3", "3期", "clinical", "临床"]):
            return "临床试验时间线从早期研究走向关键读出，旁边有药物分子和检查点图标"
        if any(word in text for word in ["deal", "licensing", "collaboration", "合作", "交易"]):
            return "两家公司节点握手或连接，箭头流向候选药物资产和管线价值卡片"
        if any(word in text for word in ["asco", "oncology", "cancer", "肿瘤"]):
            return "会议舞台/摘要页图标连接到多个肿瘤管线节点，形成数据快照面板"
        return "中心为药物研发流程，从靶点、分子、临床节点到行业信号，形成清晰路径"

    def _short_label(self, value: str) -> str:
        cleaned = re.sub(r"[#｜|:：\-—]+", " ", value)
        cleaned = "".join(cleaned.split())
        return cleaned[:8] if len(cleaned) > 8 else cleaned

    def _normalize_image_size(self, image_size: str | None) -> str:
        if image_size in IMAGE_SIZE_LABELS:
            return str(image_size)
        return self.image_client.size


def run_once(root: Path | str = "database/runs", topic_hint: str = "") -> dict[str, Any]:
    return XiaohongshuDailyFlow(storage=RunStorage(root)).run(topic_hint=topic_hint)
