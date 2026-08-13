"""Build the 2026-08-13 v2 E2E sample without changing the source automation output."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


BEGINNER_DECISION = {
    "stance": "cautious",
    "headline": "今天先观察 AI 硬件，但不要因为开盘热闹就急着行动。",
    "primary_focus": {
        "name": "AI 硬件",
        "reason": "隔夜产业消息偏强，但昨天 A 股已经提前上涨，今天需要确认多个相关方向能否一起保持强势。",
    },
    "continue_conditions": [
        {
            "time": "09:35",
            "observation": "光通信、半导体、供配电中至少两个方向仍在上涨，成长指数没有转弱，成交也比开盘时更活跃。",
            "action": "只保留观察，不因一两只股票上涨就下结论。",
        },
        {
            "time": "10:30",
            "observation": "早盘出现过下跌的相关方向重新上涨，而且上涨不只集中在一两只股票。",
            "action": "继续跟踪这一个方向，不临时增加新的题材。",
        },
    ],
    "stop_conditions": [
        {
            "time": "09:35",
            "observation": "只有少数股票上涨，成长指数转弱，或市场成交明显减少。",
            "action": "停止关注 AI 硬件，今天不追着热度行动。",
        },
        {
            "time": "10:30",
            "observation": "相关方向冲高后持续下跌，多个方向都没有重新走强。",
            "action": "放弃当天判断，不自动切换到备选方向。",
        },
    ],
    "timeline": [
        {
            "time": "09:25",
            "observation": "看相关方向是否普遍大幅高开，以及市场整体是否同样偏强。",
            "action": "只记录开盘状态，等待十分钟后的实际表现。",
            "if_unmet": "如果只有少数股票明显高开，先把今天的态度降为观望。",
        },
        {
            "time": "09:35",
            "observation": "看至少两个相关方向、成长指数和成交是否同时保持强势。",
            "action": "全部满足才继续观察；缺一项都不急着行动。",
            "if_unmet": "停止关注这个方向，等待 10:30 最后确认。",
        },
        {
            "time": "10:30",
            "observation": "看早盘下跌后是否重新上涨，并且上涨是否覆盖多只股票。",
            "action": "满足时只维持原判断，不新增方向。",
            "if_unmet": "当天放弃，不操作，也不自动转向备选。",
        },
    ],
    "backup_focus": {
        "name": "电网设备与储能",
        "condition": "只有它自身出现多只股票持续上涨、成交同步增加时才重新判断；主方向失败不等于它自动成立。",
    },
    "avoid_actions": [
        "看到开盘普遍上涨就追着热度行动。",
        "只凭一两只股票的表现判断整个方向。",
        "主方向不成立后，未经确认就切换到备选方向。",
    ],
    "term_explanations": [
        {"term": "扩散", "plain": "从少数股票上涨，变成同一方向里更多股票一起上涨。"},
        {"term": "回流", "plain": "资金离开一段时间后，又重新回到原来的方向。"},
        {"term": "承接", "plain": "价格下跌时仍有人愿意持续接住抛出的股票。"},
        {"term": "弱转强", "plain": "原本表现较弱，后来明显超过市场原先预期。"},
        {"term": "宽度", "plain": "上涨覆盖的股票数量，而不是只看少数领涨股。"},
        {"term": "拥挤度", "plain": "很多人已经集中在同一方向，继续追随时更容易出现大幅波动。"},
    ],
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    payload = json.loads(args.source.read_text(encoding="utf-8"))
    payload["schema_version"] = 2
    payload["beginner_decision"] = BEGINNER_DECISION
    args.destination.parent.mkdir(parents=True, exist_ok=True)
    args.destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
