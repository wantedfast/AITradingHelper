# 产业趋势模块

## 目标

在 AITradingHelper 中新增“产业趋势”功能。用户输入产业链或个股，后端调用本地 Stock Analyze 服务，把产业链分析结果返回到网页端。

## 用户流程

1. 用户先启动 Stock Analyze：

```powershell
.\start.ps1 -StockSkill -Port 8750
```

2. 用户启动 AITradingHelper。
3. 用户打开 `/industry-trend`。
4. 用户输入产业链或个股，例如 `华海清科` 或 `AI服务器液冷产业链`。
5. 前端调用 `POST /api/industry-trend` 创建后台任务。
6. 后端检查用户次数，写入 `run_id/status_url`，后台把请求包装成 stock-reverse-engineering prompt 并发送到 `STOCK_ANALYZE_API_URL`。
7. 前端轮询 `status_url`。
8. 任务成功后后端扣除 1 次使用机会，前端展示 Stock Analyze 返回的完整正文；任务失败不扣次数。

## API

```http
POST /api/industry-trend
Content-Type: application/json
Authorization: Bearer <token>
```

```json
{
  "query": "华海清科",
  "input_type": "stock"
}
```

返回：

```json
{
  "run_id": "20260706_143000_abcdef",
  "status": "queued",
  "stage": "queued",
  "status_url": "/api/industry-trend/reports/20260706_143000_abcdef/status",
  "query": "华海清科",
  "input_type": "stock",
  "billing_status": "pending_generation"
}
```

状态接口：

```http
GET /api/industry-trend/reports/<run_id>/status
Authorization: Bearer <token>
```

成功状态包含：

```json
{
  "status": "done",
  "billing_status": "charged",
  "answer": "...",
  "user": {
    "credits": 4
  }
}
```

失败状态包含 `status=error` 和 `billing_status=not_charged`。

## 验收标准

- 侧边栏和首页能进入 `/industry-trend`。
- 页面能输入产业链或个股，并选择 `auto` / `chain` / `stock`。
- 未登录用户跳转登录。
- 后端默认调用 `http://127.0.0.1:8750/api/codex`。
- 可通过 `STOCK_ANALYZE_API_URL`、`STOCK_ANALYZE_TIMEOUT_SECONDS` 和 `STOCK_ANALYZE_TOKEN` 覆盖。
- Stock Analyze 不可用时返回清晰错误。
- 前端通过状态接口轮询结果，不挂起一个长请求等待完整报告。
- 成功生成后扣除 1 次使用机会；失败不扣次数。

## 非目标

- 不在本模块内启动 Stock Analyze 子进程。
- 不在本模块内复制 stock-reverse-engineering skill。
- 当前版本不是流式返回，完整结果生成后一次性展示。
