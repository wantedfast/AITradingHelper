# 产业链逆向研究运行说明

## 开关与模型

- `STOCK_RESEARCH_ACCESS=admin|pilot|all`，默认 `admin`。
- `STOCK_RESEARCH_ROLLOUT_PERCENT=10` 仅在 `pilot` 模式生效。
- `STOCK_RESEARCH_PROVIDER=luna|doubao_deepseek|auto`。
- Luna 使用 `OPENAI_API_KEY` 与 `STOCK_RESEARCH_LUNA_MODEL`（默认 `gpt-5.6-luna`）。
- 混合引擎使用 `ARK_API_KEY`、`DEEPSEEK_API_KEY`、`STOCK_RESEARCH_DEEPSEEK_FLASH_MODEL` 和 `STOCK_RESEARCH_DEEPSEEK_PRO_MODEL`。
- `STOCK_RESEARCH_MAX_COST_CNY=2`，`STOCK_RESEARCH_TIMEOUT_SECONDS=300`。

密钥只从服务器环境变量读取，不能写入数据库、报告、日志或前端环境变量。

## 20 份盲测门槛

管理员用相同 `sample_key` 分别记录两种引擎的盲评结果：

```http
POST /api/admin/stock-research/benchmark
Authorization: Bearer <admin-token>
Content-Type: application/json

{
  "sample_key": "stock-01-huazheng",
  "provider": "luna",
  "citation_rate": 98,
  "completeness_rate": 100,
  "severe_error": false,
  "quality_score": 92,
  "cost_cny": 1.08,
  "duration_seconds": 126
}
```

`GET /api/admin/stock-research/benchmark` 返回聚合指标和当前裁决。配置 `STOCK_RESEARCH_PROVIDER=auto` 后，只有 Luna 同时满足 20 份样本、引用率、完整率、严重错误、质量差距、成本和 P95 时延门槛才会成为主引擎；否则使用 `doubao_deepseek`。

管理员测试时可在创建任务 JSON 中附加 `provider` 强制选择某一引擎，普通用户传入该字段会被忽略。

## 计费与恢复

- 会员每个自然月包含 10 份成功报告，每天最多生成 2 份；未使用额度不结转。
- 会员当月超过 10 份后，每份成功报告扣 3 次；普通用户每份成功报告扣 3 次。
- 管理员评测免扣。失败、超时和取消既不扣次数，也不占当天或当月额度。
- 创建任务时冻结本次 `billing_mode`，避免生成期间跨月或并发改变计费结果。

任务通过六角色输出、引用、三高公式、禁止投资指令和成本校验后，报告写入、使用记录、可能发生的 3 次扣费、任务完成在同一 SQLite 事务内提交。`job_id` 是扣费幂等键；重复打开或重复执行完成任务不会再次扣费。服务启动会恢复排队或运行中的任务，同一用户只能保留一个运行中任务。
