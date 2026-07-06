# 产业趋势模块

## 目标

在 AITradingHelper 中新增“产业趋势”功能。用户输入产业链或个股，后端调用本地 Stock Analyze 服务，再把产业链分析结果返回到网页端。

## 用户流程

1. 用户先启动 Stock Analyze：

```powershell
.\start.ps1 -StockSkill -Port 8750
```

2. 用户启动 AITradingHelper。
3. 用户打开 `/industry-trend`。
4. 用户输入产业链或个股，例如 `华海清科` 或 `AI服务器液冷产业链`。
5. 前端调用 `POST /api/industry-trend`。
6. 后端把请求包装成 stock-reverse-engineering prompt，发送到 `STOCK_ANALYZE_API_URL`。
7. 前端展示 Stock Analyze 返回的完整正文。

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
  "query": "华海清科",
  "input_type": "stock",
  "answer": "...",
  "source": "stock-analyze",
  "endpoint": "http://127.0.0.1:8750/api/codex",
  "elapsed_seconds": 123.4
}
```

## 验收标准

- 侧边栏和首页能进入 `/industry-trend`。
- 页面能输入产业链或个股，并选择 `auto` / `chain` / `stock`。
- 未登录用户跳转登录。
- 后端默认调用 `http://127.0.0.1:8750/api/codex`。
- 可通过 `STOCK_ANALYZE_API_URL`、`STOCK_ANALYZE_TIMEOUT_SECONDS` 和 `STOCK_ANALYZE_TOKEN` 覆盖。
- Stock Analyze 不可用时返回清晰错误。

## 非目标

- 不在本模块内启动 Stock Analyze 子进程。
- 不在本模块内复刻 stock-reverse-engineering skill。
- 当前版本不是流式返回，完整结果生成后一次性展示。
