from __future__ import annotations

from agents.topic_agent.score import ScoredTopic


class TopicSelector:
    def select(self, scored_topics: list[ScoredTopic], limit: int = 3) -> list[ScoredTopic]:
        ordered = sorted(scored_topics, key=lambda item: item.total_score, reverse=True)
        selected_ids = {id(item) for item in ordered[:limit]}
        for item in scored_topics:
            item.selected = id(item) in selected_ids
        return ordered[:limit]
