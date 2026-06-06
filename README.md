# A股交易复盘 Agent MVP

这是一个日线级交易复盘工具：读取券商导出的成交记录，使用 AKShare 拉取 A股日K与沪深300指数，计算买入/卖出后的收益、相对强弱、量能变化和最大回撤，最后输出 Markdown 复盘报告。

## 安装

```bash
pip install -r requirements.txt
```

## 成交记录字段

CSV 或 Excel 至少需要这些列：

```text
股票代码
成交日期
买卖方向
成交价格
成交数量
```

建议额外提供：

```text
股票名称
成交金额
手续费
买入理由
卖出理由
```

英文列名也支持：`code`, `name`, `trade_date`, `side`, `price`, `quantity`, `amount`, `fee`, `buy_reason`, `sell_reason`。

## 运行示例

```bash
python -m trade_review_agent.cli samples/trades_sample.csv -o outputs/review_report.md --cache-db work/trade_review_cache.sqlite
```

第一次运行会优先调用 AKShare 下载行情；如果 AKShare 远端接口失败，会自动切到腾讯财经历史 K 线接口作为兜底，并写入 SQLite 缓存。之后同一时间范围的数据会优先从缓存读取。

如果临时网络或 AKShare 远端接口不可用，可以先跑本地演示缓存：

```bash
python samples/seed_sample_cache.py
python -m trade_review_agent.cli samples/trades_sample.csv -o outputs/review_report.md --cache-db work/trade_review_cache.sqlite --offline
```

## 输出内容

每笔成交会输出：

- 成交日对齐后的日K
- 当日涨跌幅
- 相对前 5 日成交量
- 买入/卖出后 1、3、5、10 个交易日收益
- 同期沪深300收益
- 相对强弱
- 10日最大上涨和最大回撤
- 初步交易诊断与改进建议

## 可视化复盘

生成单票交互式复盘页：

```bash
python -m trade_review_agent.visual_cli C:\Users\wantedfast\Desktop\table.xls --code 600584 -o outputs/charts/600584_changdian.html --cache-db work/real_trade_review_cache.sqlite
```

生成整张交割单的所有交易轮次复盘页：

```bash
python -m trade_review_agent.visual_batch_cli C:\Users\wantedfast\Desktop\table.xls -o outputs/visual_reports --cache-db work/real_trade_review_cache.sqlite
```

批量模式会输出一个 `index.html` 目录页，并为每一轮有买入动作的交易生成独立 visual report。

页面包含：

- 交易评分卡
- 大盘环境与个股日K分析：指数、板块、量能、个股日K文字判断
- 收益曲线：持有期浮盈变化
- 产业链定位图
- 板块共振折线图：个股、半导体ETF、沪深300
- 买卖执行分析
- AI总结

## 下一步可扩展

- 账户每日资产曲线和回撤归因
- 行业/概念板块强弱
- 分钟线买卖点还原
- OpenAI API 生成更细的自然语言复盘
- LangGraph 工作流和任务队列
