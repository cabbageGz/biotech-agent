from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import date
from typing import Any


@dataclass
class DailyBrief:
    objective: str
    audience: str
    content_angle: str
    research_focus: list[str]
    source_policy: list[str]
    quality_bar: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CEOAgent:
    """Decides the daily editorial brief for the biotech intelligence workflow."""

    def create_daily_brief(
        self,
        target_date: date,
        topic_hint: str = "",
        audience: str = "关注生物医药、创新药、投融资和产业趋势的小红书读者",
    ) -> DailyBrief:
        topic = topic_hint.strip() or "今日生物医药热点"
        return DailyBrief(
            objective=f"生成 {target_date.isoformat()} 的《小红书生物医药热点》",
            audience=audience,
            content_angle=(
                f"围绕“{topic}”，优先选择有产业意义、临床进展、监管变化、交易合作或资本市场信号的新闻。"
            ),
            research_focus=[
                "创新药临床与监管里程碑",
                "Biotech/Pharma 交易、授权合作与融资",
                "AI 制药、细胞/基因治疗、抗体药物、ADC 等技术趋势",
                "大型药企管线调整、商业化进展与行业风向",
            ],
            source_policy=[
                "优先使用可追溯的公开来源，并保留链接",
                "同一事件多源重复时合并处理",
                "避免把单一公司宣传稿写成确定性行业结论",
            ],
            quality_bar=[
                "每条热点要说明为什么重要",
                "结论要克制，区分事实、推断和待观察点",
                "小红书文案要可读、可发布，但不夸大医疗疗效或投资收益",
            ],
        )

    def render_markdown(self, brief: DailyBrief) -> str:
        sections = [
            f"# {brief.objective}",
            f"目标读者：{brief.audience}",
            f"内容角度：{brief.content_angle}",
            "## 研究重点",
            *[f"- {item}" for item in brief.research_focus],
            "## 来源策略",
            *[f"- {item}" for item in brief.source_policy],
            "## 质量标准",
            *[f"- {item}" for item in brief.quality_bar],
        ]
        return "\n".join(sections) + "\n"
