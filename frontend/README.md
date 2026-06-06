# V2 Frontend

这是交易复盘 Agent 的下一版前端骨架，目标是替代 Streamlit 的展示层，但不影响当前线上 Streamlit 服务。

## 技术栈

- Next.js
- Tailwind CSS
- lucide-react
- ECharts / react-force-graph-2d 预留给行情图和产业链图

## 本地运行

```bash
npm install
npm run dev
```

默认地址：

```text
http://127.0.0.1:3000
```

## 后续接入

前端页面已经预留这些模块：

- 上传交割单
- 交易评分卡
- 板块共振柱状图
- 产业链定位节点图
- 盯盘预案列表

下一步需要新增 FastAPI 接口：

```text
POST /api/reports
GET  /api/reports/{id}
GET  /api/alerts
POST /api/alerts
POST /api/video-reports
```

其中 `/api/video-reports` 可以接 HyperFrames，生成视频版复盘报告。
