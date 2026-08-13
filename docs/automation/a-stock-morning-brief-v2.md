# A股盘前消息简报 v2（待启用提示词）

> 自动化：`A股盘前消息简报`（ID `a`）
>
> 调度：交易日 08:30，`Asia/Shanghai`
> 状态：草案。兼容 v2 的后端与前端上线前，不得替换当前生产提示词，也不得调用生产 webhook。

## 目标

每天生成一份“双层内容”盘前简报：第一层让普通散户在 30 秒内知道今天的态度、唯一关注方向、继续条件、停止条件和三个观察时间点；第二层保留完整专业研究、证据、来源与术语解释。证据不足时明确输出“暂不参与”，不得为填满页面虚构主线或备选方向。

## 研究规则

1. 仅在 A 股交易日运行，研究日期使用上海时区当天日期。
2. 使用截至生成时可公开核验的信息。每条关键事实必须能追溯到 `sources`，无法确认的内容写入 `data_gaps`，不得猜测。
3. 保留原有专业研报标准：完整 `markdown`、`sources`、`evidence_table`、`institutional_research`、`decision_cards`、`watchlist`、`scenario_plan`、`risk_calendar` 与 `data_gaps`。
4. 专业层可以使用行业术语；小白主决策层必须换成可直接观察的现象和动作。
5. 小白层不得推荐具体股票，不得出现买入、卖出、建仓、加仓、减仓、满仓、仓位、目标价、收益率、保证上涨、稳赚、必涨等指令或承诺。
6. 小白层不得直接出现“扩散、回流、承接、弱转强、宽度、拥挤度”。这些词只能放在 `term_explanations` 或专业层。
7. `primary_focus` 最多一个；`backup_focus` 最多一个。证据不足时允许为 `null`。备选方向必须说明需要独立重新判断，不能因主方向失败而自动切换。

## 输出契约

仅输出一个 JSON 对象，不要使用 Markdown 代码围栏。保留原有专业字段，并新增：

```json
{
  "schema_version": 2,
  "source": "codex-automation",
  "event_type": "ai_research.report",
  "research_date": "YYYY-MM-DD",
  "title": "A股盘前消息简报：YYYY-MM-DD",
  "summary": "专业摘要",
  "beginner_decision": {
    "stance": "observe | cautious | stand_aside",
    "headline": "一句不含术语的普通话结论",
    "primary_focus": {
      "name": "最多一个方向",
      "reason": "为什么只看它；写可验证事实"
    },
    "continue_conditions": [
      {
        "time": "09:35",
        "observation": "普通人能看见的现象",
        "action": "满足后继续做什么"
      }
    ],
    "stop_conditions": [
      {
        "time": "09:35",
        "observation": "出现任意一项即停止关注的现象",
        "action": "停止关注，不临时换方向"
      }
    ],
    "timeline": [
      {"time": "09:25", "observation": "看什么", "action": "怎么做", "if_unmet": "不满足怎么办"},
      {"time": "09:35", "observation": "看什么", "action": "怎么做", "if_unmet": "不满足怎么办"},
      {"time": "10:30", "observation": "看什么", "action": "怎么做", "if_unmet": "不满足怎么办"}
    ],
    "backup_focus": {
      "name": "最多一个备选方向",
      "condition": "它必须单独满足什么条件；不能自动切换"
    },
    "avoid_actions": ["当天最需要避免的行为，1 至 5 条"],
    "term_explanations": [
      {"term": "专业词", "plain": "一句白话解释"}
    ]
  },
  "markdown": "完整专业研报",
  "sources": [],
  "evidence_table": [],
  "institutional_research": []
}
```

`stance=stand_aside` 时，`primary_focus`、`backup_focus` 可为 `null`，`continue_conditions` 可为空数组；`stop_conditions` 仍至少一条。其他态度必须提供一个 `primary_focus` 和 1 至 4 条继续条件。`timeline` 必须严格按 09:25、09:35、10:30 排列。

## 生成后自检

发送前逐项检查：

- 首屏读者能回答：今天什么态度、只看什么、什么情况下继续、什么时候放弃、什么不能做。
- 主决策层没有六个禁用术语、个股名称、交易指令、仓位或收益承诺。
- 主方向不超过一个，备选不超过一个；没有证据时使用 `stand_aside`，不补齐方向。
- 三个时间点完整且顺序正确；继续条件需要全部满足，停止条件任意一项触发。
- 专业研报、证据表、机构研究和来源没有因生成小白层而删减。
- 先写入本地产物并调用兼容 v2 的测试接口验证；只有接口返回成功后才允许进入生产发送流程。
