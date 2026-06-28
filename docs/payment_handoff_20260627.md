# 支付与次数系统交接文档

更新时间：2026-06-27

本文档用于记录本项目近期围绕账号、次数扣减、邮件通知、支付入账做过的主要调整，并说明当前“金数据收款表单 + Webhook 回调 + 自动增加次数”的实现方案。

## 一、近期主要修改点

### 1. 本地部署与基础服务

- 已梳理本地部署方式：后端运行在 `http://127.0.0.1:8600`，前端运行在 `http://127.0.0.1:3000`。
- 本地启动脚本为 `start-local.ps1`。
- 后端健康检查接口为：

```text
GET /api/health
```

### 2. 账号体系调整

- 已取消手机号注册、手机号登录、短信验证码登录入口。
- 当前只支持邮箱注册和账号/邮箱密码登录。
- 邮箱验证码已经从“本地测试展示验证码”改为 SMTP 真实发邮件。
- `.env` 中需要配置 SMTP：

```env
EMAIL_PROVIDER=smtp
SMTP_HOST=smtp.qq.com
SMTP_PORT=465
SMTP_USER=邮箱账号
SMTP_PASSWORD=邮箱授权码
SMTP_FROM=发件邮箱
SMTP_FROM_NAME=盈航
SMTP_USE_SSL=1
```

### 3. 邀请码逻辑

- 注册页邀请码增加提示文案。
- 邀请链接进入注册页后，会自动把邀请码填入注册表单。
- 邀请奖励规则已调整为：
  - 邀请方：邀请成功增加 5 次。
  - 被邀请方：默认免费 5 次基础上，额外增加 2 次。

### 4. 报告生成扣次数逻辑

- AI 复盘报告已改为“生成成功并在前端可见后再扣次数”。
- 报告生成失败不扣次数。
- 后端生成阶段只检查用户是否有可用次数，不提前扣除。
- 前端报告页加载成功后调用 `ack` 接口确认展示，再由后端扣除一次。
- 避免用户切换页面、重新加载或生成失败时误扣次数。

相关接口：

```text
POST /api/reports/{run_id}/ack
POST /api/market-day/reports/{run_id}/ack
```

### 5. 交割单文件输入

- 已为 AI 复盘增加交易文件输入能力。
- 支持 CSV，也已扩展为支持 Excel 等多种表格格式。
- 前端提供面向用户的 CSV/表格制作说明，并采用点击弹窗形式，避免布局紊乱。

### 6. 竞价强者入口与扣次数逻辑

- 已恢复左侧导航中的“竞价强者”入口。
- 查看竞价分析前，会提示用户“查看内容会扣除 1 次”。
- 用户确认后才加载竞价内容。
- 内容成功展示后调用后端 `ack` 接口扣次数。
- 无数据、未登录、加载失败均不扣次数。

相关接口：

```text
GET /api/auction-strength
POST /api/auction-strength/ack
```

### 7. 用户次数增加邮件通知

- 邮件通知的对象是“被增加次数的用户”，不是管理员。
- 后台支持管理员手动给指定用户增加次数，这是其中一个触发场景。
- 管理员手动增加时必须填写原因。
- 用户次数增加成功后，系统会给该用户发送邮件，说明：
  - 增加了多少次
  - 增加原因
  - 当前剩余次数
- 反馈采纳、订单支付成功也复用同一套用户邮件提醒能力。

### 8. 支付能力演进

- 已先实现过支付宝当面付扫码支付的基础接口结构。
- 由于支付宝正式支付接入需要商家主体、应用、密钥、公网回调地址，当前又新增了更适合现阶段落地的金数据收款表单方案。
- 当前前端购买页已经切换为金数据收款表单方式。

## 二、当前支付接口实现方案

当前方案采用：

```text
前端购买页
-> 后端创建订单
-> 后端生成金数据表单跳转链接
-> 用户在金数据完成支付
-> 金数据 Webhook 回调后端
-> 后端校验订单和金额
-> 后端标记订单已支付
-> 后端给用户增加次数
-> 后端发送到账邮件
```

### 1. 购买页入口

前端页面：

```text
frontend/app/billing/page.tsx
```

访问地址：

```text
/billing
```

页面能力：

- 读取后端次数包。
- 用户选择次数包。
- 点击按钮后调用后端创建金数据 checkout。
- 新窗口打开金数据收款表单。
- 页面轮询订单状态。
- 支付成功后展示“次数已到账”。

### 2. 次数包配置

次数包定义在：

```text
trade_review_agent/auth_system.py
```

当前配置：

```python
CREDIT_PACKAGES = {
    "pack_10": {"plan_name": "10 次使用包", "credits": 10, "amount_cents": 990},
    "pack_50": {"plan_name": "50 次使用包", "credits": 50, "amount_cents": 3990},
    "pack_120": {"plan_name": "120 次使用包", "credits": 120, "amount_cents": 7990},
}
```

前端读取接口：

```text
GET /api/pay/packages
```

### 3. 创建金数据付款链接

接口：

```text
POST /api/pay/jinshuju/checkout
```

请求体：

```json
{
  "package_id": "pack_10"
}
```

后端处理：

1. 要求用户已登录。
2. 根据 `package_id` 创建本地订单。
3. 根据 `.env` 中配置的金数据表单地址和字段映射，拼出带参数的金数据表单链接。
4. 返回订单和跳转链接。

返回示例：

```json
{
  "order": {
    "id": 1,
    "order_no": "YT20260627123456ABCDEF",
    "plan_name": "10 次使用包",
    "credits": 10,
    "amount_cents": 990,
    "status": "pending"
  },
  "checkout_url": "https://jinshuju.net/f/xxxx?field_1=YT...",
  "provider": "jinshuju"
}
```

### 4. 金数据表单字段设计

金数据收款表单建议至少包含以下字段：

| 字段用途 | 默认字段编码 | 是否建议隐藏/只读 | 说明 |
| --- | --- | --- | --- |
| 订单号 | `field_1` | 建议隐藏或只读 | 后端生成，用于回调后匹配订单 |
| 用户邮箱 | `field_2` | 建议隐藏或只读 | 用于校验付款人和订单用户 |
| 套餐 ID | `field_3` | 建议隐藏或只读 | 如 `pack_10` |
| 用户 ID | `field_4` | 建议隐藏或只读 | 辅助排查 |
| 套餐名称 | 可选 | 可展示 | 例如“10 次使用包” |
| 金额 | 可选 | 可展示 | 实际金额以后端订单金额为准 |

注意：后端不会信任前端或金数据字段里传来的“次数”。最终增加多少次，只以后端订单里的套餐为准。

### 5. 金数据 Webhook 回调

接口：

```text
POST /api/pay/jinshuju/notify
```

建议金数据后台配置的回调地址：

```text
https://你的公网域名或公网IP/api/pay/jinshuju/notify?token=你的JINSHUJU_WEBHOOK_SECRET
```

如果暂时只有公网 IP，并且金数据允许 HTTP，可以先尝试：

```text
http://你的公网IP:8600/api/pay/jinshuju/notify?token=你的JINSHUJU_WEBHOOK_SECRET
```

生产环境更建议使用：

```text
https://你的域名/api/pay/jinshuju/notify?token=你的JINSHUJU_WEBHOOK_SECRET
```

### 6. Webhook 安全与幂等

当前后端做了以下保护：

- 支持通过 `token` 查询参数或请求头校验 `JINSHUJU_WEBHOOK_SECRET`。
- 可选校验金数据表单来源 `JINSHUJU_FORM_TOKEN`。
- 使用金数据 `form + serial_number` 生成 `provider_trade_no`。
- 同一个 `provider_trade_no` 重复回调，只返回已有订单，不重复加次数。
- 校验支付金额必须等于本地订单金额。
- 如果回调里有邮箱，会校验表单邮箱必须等于订单用户邮箱。
- 订单不存在、金额不一致、邮箱不一致均不会入账。

### 7. 支付成功后的入账逻辑

支付成功后调用：

```python
mark_order_paid_by_order_no(...)
```

该函数负责：

1. 查找本地订单。
2. 校验金额。
3. 校验支付流水是否重复。
4. 更新订单状态为 `paid`。
5. 写入 `credit_ledger`，给用户增加次数。
6. 发送邮件通知用户。

订单表关键字段：

```text
orders.status
orders.paid_at
orders.payment_provider
orders.provider_trade_no
orders.paid_amount_cents
```

次数流水表：

```text
credit_ledger
```

## 三、环境变量配置

`.env.example` 已补充金数据相关配置。

最小配置：

```env
JINSHUJU_FORM_URL=https://jinshuju.net/f/你的表单
JINSHUJU_WEBHOOK_SECRET=一串足够长的随机密钥
JINSHUJU_ORDER_FIELD=field_1
JINSHUJU_EMAIL_FIELD=field_2
JINSHUJU_PACKAGE_FIELD=field_3
JINSHUJU_USER_FIELD=field_4
```

推荐配置：

```env
JINSHUJU_FORM_TOKEN=你的金数据表单标识
```

如果不同套餐使用不同金数据表单，可以配置：

```env
JINSHUJU_FORM_URL_PACK_10=
JINSHUJU_FORM_URL_PACK_50=
JINSHUJU_FORM_URL_PACK_120=
```

## 四、公网部署注意事项

### 1. 只有公网 IP 是否可行

技术上可以尝试，但要满足：

- 后端服务监听公网可访问地址。
- 云服务器安全组开放后端端口。
- 系统防火墙开放后端端口。
- 金数据允许 HTTP 回调，或者服务器已配置 HTTPS。

如果金数据要求 HTTPS，建议购买域名并绑定公网 IP，然后用 Nginx 做 HTTPS 反向代理。

### 2. 推荐部署结构

推荐公网结构：

```text
用户浏览器
-> https://你的域名
-> Nginx
-> 前端服务 127.0.0.1:3000

金数据 Webhook
-> https://你的域名/api/pay/jinshuju/notify
-> Nginx
-> 后端服务 127.0.0.1:8600
```

### 3. 回调路径代理

如果用 Nginx，可以把：

```text
/api/
```

反向代理到：

```text
http://127.0.0.1:8600/
```

这样金数据回调地址可以写成：

```text
https://你的域名/api/pay/jinshuju/notify?token=密钥
```

## 五、测试方式

### 1. 本地基础检查

```powershell
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8600/api/health
```

预期：

```json
{"status":"ok"}
```

### 2. 单元测试

```powershell
.\.venv\Scripts\python.exe -m unittest .\tests\test_webhook_api.py
```

当前已覆盖：

- 金数据回调成功后订单变为已支付。
- 金数据重复回调不会重复增加次数。
- 金数据回调金额和本地订单金额不一致时不会入账。

### 3. 前端构建

```powershell
npm.cmd run build
```

在 `frontend` 目录执行。

### 4. 公网回调联调

部署到公网服务器后，先测试：

```text
http://公网IP:8600/api/health
```

如果能访问，再测试金数据 Webhook 地址：

```text
http://公网IP:8600/api/pay/jinshuju/notify?token=密钥
```

正式联调时，应以一笔小额真实支付或金数据后台测试推送为准。

## 六、后续建议

1. 公网部署后优先确认金数据是否允许 HTTP 回调；如果不允许，尽快上域名和 HTTPS。
2. 金数据表单里的订单号、用户邮箱、套餐 ID 建议设为隐藏或只读，减少用户误改。
3. 后台订单列表后续可以增加支付渠道、支付流水号、到账时间字段展示，方便查账。
4. 后续如果接入支付宝或微信官方支付，可以继续复用当前订单表、次数流水表和邮件通知逻辑。
5. 退款场景目前没有自动扣回次数，需要后续单独设计人工退款或退款 Webhook 流程。
