# AI 复盘报告交接状态

## 分支

当前工作分支：

```text
feature/watch-plan-fix
```

远程：

```text
origin https://github.com/wantedfast/AITradingHelper.git
```

## 已完成

- 前端报告页买卖点展示去重。
- 买点/卖点各自一块功能卡。
- 下次执行规则单独展示，不再重复同一句买卖点原因。
- Presenter AI 默认关闭，改成本地 mapper。
- WANG / Public Equity 支持快速 JSON-only 和详细 JSON+memo 两档。
- 前端上传页增加“快速报告 / 更详细的报告”按钮。
- Workbench 输出 research_metrics，记录耗时和 token。
- Trade Execution 与 Workbench 并行。
- WANG 与 Public Equity 并行。
- 多 TradeRound 小并发构建。
- Trade Execution 支持行情预取和 fallback。
- Trade Execution 增加 LLM 增强层。
- 旧 cache 场景下，Presenter 不再让 `待验证` 占位覆盖 memo 中的有效结论。
- Watch Agent 行情并行获取。

## 主要修改文件

```text
frontend/app/review/page.tsx
frontend/app/review/report/[id]/page.tsx
frontend/app/globals.css
trade_review_agent/visual_report.py
trade_review_agent/workbench_agents.py
trade_review_agent/workbench_composer.py
trade_review_agent/industry_agent.py
trade_review_agent/presenter_agent.py
trade_review_agent/trade_execution_chain.py
trade_review_agent/trade_execution_data.py
trade_review_agent/execution_structurer.py
trade_review_agent/watch_agent.py
trade_review_agent/validate_workbench_contracts.py
```

## 新增文档

```text
docs/trade_review_requirements.md
docs/trade_review_solution.md
docs/trade_review_handoff_status.md
```

## 已跑测试

后端合同测试：

```powershell
python -m trade_review_agent.validate_workbench_contracts
```

后端 OpenAI 错误协议测试：

```powershell
python -m trade_review_agent.validate_openai_error_contracts
```

Python 编译检查：

```powershell
python -m py_compile trade_review_agent/trade_execution_chain.py trade_review_agent/visual_report.py trade_review_agent/presenter_agent.py trade_review_agent/validate_workbench_contracts.py
```

前端 lint：

```powershell
& 'C:/Users/wantedfast/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe' 'E:/Git/AITradingHelper-feature-watch-plan-fix/frontend/node_modules/next/dist/bin/next' lint
```

前端 build：

```powershell
& 'C:/Users/wantedfast/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe' 'E:/Git/AITradingHelper-feature-watch-plan-fix/frontend/node_modules/next/dist/bin/next' build
```

diff 检查：

```powershell
git diff --check
```

备注：`git diff --check` 只有 Windows LF/CRLF warning，没有 whitespace error。

## 本地启动

```powershell
cd E:\Git\AITradingHelper-feature-watch-plan-fix
.\start-local.ps1
```

默认地址：

```text
Frontend: http://127.0.0.1:3000
Backend:  http://127.0.0.1:8600
Health:   http://127.0.0.1:8600/api/health
```

## 已知问题 / 风险

### 1. OpenAI rate limit

连续生成报告时可能在 OCR 阶段触发：

```text
code: openai_rate_limited
stage: ocr_trade_file
```

这是 OpenAI API 限流，但本地代码也应继续加强全局 OpenAI 请求队列和退避重试。

建议下一步：

- OCR 阶段加全局并发闸门。
- WANG/Public Equity/Trade Execution LLM 共用 OpenAI 请求限速器。
- 前端显示排队状态，避免重复点击。

### 2. Trade Execution LLM 会增加 token 和耗时

现在 Trade Execution LLM 默认开启：

```text
TRADE_EXECUTION_LLM_ENABLED=1
```

如果需要极快模式，可以关闭：

```powershell
$env:TRADE_EXECUTION_LLM_ENABLED="0"
```

### 3. 需要真实回归更多截图

已用本地截图做过快速/详细对比和旧 cache presenter 重组验证，但因为 OpenAI 限流，没有在最后一次改动后连续跑大量真实截图。

接手者建议至少测试：

- 通鼎互联截图
- 长城科技截图
- 单买单卖
- 一买多卖
- 只有买入无卖出
- OCR 识别失败
- OpenAI 限流错误

## 建议下一步

1. 增加 OpenAI 全局请求队列和 rate-limit 退避。
2. 给 OCR usage 也记录 token 和耗时。
3. 给 Trade Execution LLM usage 透传实际 token。
4. 用 Playwright 对 `/review` 和 `/review/report/[id]` 做视觉回归。
5. 让正式服务器先部署到 staging 或灰度环境。
6. 合并 develop/main 前再跑一次完整真实生成。

## 接手检查清单

- 拉取分支 `feature/watch-plan-fix`。
- 运行后端合同测试。
- 运行前端 lint/build。
- 本地启动 `start-local.ps1`。
- 上传一张截图生成快速报告。
- 上传同一张截图生成更详细报告。
- 检查报告首屏是否有有效结论和标签。
- 检查买卖点是否各自一张卡。
- 检查 `.timings.json` 是否包含 `trade_execution_llm_seconds`。
- 检查 `.trade_execution_llm_output.json` 是否生成。
- 检查 Workbench `research_metrics` 是否包含 token/耗时。

