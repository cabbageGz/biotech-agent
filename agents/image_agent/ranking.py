from __future__ import annotations

from agents.image_agent.generate_prompts import ImagePromptOption


class ImagePromptRanker:
    def rank(self, options: list[ImagePromptOption]) -> list[ImagePromptOption]:
        for option in options:
            score = 50
            prompt = option.prompt
            if "文字白名单" in prompt:
                score += 15
            if "不要" in prompt and "编造" in prompt:
                score += 15
            if any(word in prompt for word in ["视觉中心", "构图", "信息块"]):
                score += 10
            if len(prompt) > 1600:
                score -= 8
            option.score = max(0, min(100, score))
        return sorted(options, key=lambda item: item.sequence)
