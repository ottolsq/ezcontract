# 🌌 星河 · 企业多智能体工作台（Demo）

> 品牌定位：**星河** —— 企业多智能体工作台。当前已交付四大模块：**合同起草 / 合同审查 / 履约提醒 / 人员行程**；后续扩展会议纪要、员工管理、工作内容管理等智能体。

- **合同起草**：关键词 → AI 生成模板 → 在线编辑 → 导出 Word
- **合同审查**：上传合同 → AI 按规则库审查 → 风险清单 → 采纳/修改/不采纳 → 导出修改后合同与审核报告
- **履约提醒**：上传合同 → AI 提取付款日、交付日等履约节点 → 到期前一天站内提醒
- **人员行程**：语音录入 → ASR 转写 + LLM 解析 → 人工确认 → 日历管理

## 架构（Demo 简化版）

```
faheng-web (Vue3 + Element Plus + Pinia, :58068)
    │ /api 代理
faheng-api (FastAPI, :58069)
    ├── OpenAI 兼容接口 ──→ LLM 网关（任意 OpenAI 兼容服务，模型需支持结构化输出）
    ├── /audio/transcriptions ──→ SiliconFlow ASR（SenseVoiceSmall，行程语音转写）
    └── SQLite（data/compliance.db，履约 + 行程持久化）
```

- 合同审查/起草**不使用 RAG / Dify**：26 条审核规则（`rules/erp_rules.md`）全量注入审查 prompt；会话存内存，**重启后端即丢失**，demo 需在单次会话内完成
- 履约提醒 / 人员行程**已 SQLite 持久化**：`faheng-api/data/compliance.db`（首次运行自动建表，`.gitignore` 已忽略 `data/`）
- 风险分由前端确定性派生（liveScore）：剩余未消除风险 high×15 + medium×7，上限 100；采纳/修改即时消除并减分，驳回不减
- 履约日期由后端确定性计算：LLM 只抽「锚点 + 偏移 + 周期」结构，具体日期与周期展开全部本地重算（周期实例从基准重算，无漂移）

## 启动

```bash
# 后端（终端 1）
cd faheng-api
git submodule update --init --recursive  # 首次：拉取 contract-copilot.skill 知识库
pip install -r requirements.txt      # 首次
python run.py                        # http://localhost:58069, Swagger: /docs

# 前端（终端 2）
cd faheng-web
npm install                          # 首次
npm run dev                          # http://localhost:58068
```

> 「载入测试合同」按钮（审查 / 履约两模块口径一致）读取项目根目录 `exmple/房屋租赁合同 (1).docx`，请自行放置；未放置时按钮报 404 提示。
> 首次访问 `http://localhost:58068` 会跳转 `/login`，用 `.env` 中的演示账号 + 页面验证码登录。

## 配置（项目根目录 .env，前后端共用同一文件）

```bash
LLM_BASE_URL=<OpenAI 兼容网关地址>   # 注意必须含 /v1
LLM_API_KEY=sk-xxx
LLM_MODEL=<模型名>

# 语音识别（人员行程语音录入）：SiliconFlow SenseVoiceSmall
# https://siliconflow.cn 注册获取 API Key（有免费额度）；BASE_URL / MODEL 一般无需修改
ASR_BASE_URL=https://api.siliconflow.cn/v1
ASR_MODEL=FunAudioLLM/SenseVoiceSmall
ASR_API_KEY=sk-xxx

# 前端 dev 代理目标（仅 Vite dev server 使用；Docker/生产同源部署不走代理）
VITE_API_TARGET=http://127.0.0.1:58069

# 演示账号（登录页账号密码 + 验证码，改这里并重启后端即生效）
DEMO_USERNAME=admin
DEMO_PASSWORD=xxx
AUTH_TOKEN_TTL=86400
```

> 若模型带思维链（reasoning_content 占 token），max_tokens 需给足（当前审查 12K / 起草 16K / 履约 6K / 行程 4K），勿调小。

## Docker 部署（单容器交付）

多阶段构建（根目录 [Dockerfile](Dockerfile)）：`node:20-alpine` 构建前端 → `python:3.11-slim` 安装后端依赖并拷入业务代码与前端产物，**单个 uvicorn 进程同时 serve 前端静态页面与 API**（同源，端口 58069）。

```bash
# 构建（仓库根目录执行；首次需先初始化 submodule）
git submodule update --init --recursive
docker build -t faheng:latest .

# 运行（.env 按"配置"章节准备，放在当前目录）
docker run -d --name faheng --restart unless-stopped \
  -p 58069:58069 --env-file .env \
  -v faheng-data:/app/data \
  faheng:latest

# 探活
curl http://127.0.0.1:58069/api/health
```

> `-v` 挂载 `/app/data` 持久化 SQLite（履约 + 行程数据）；不挂则容器重建即丢失。

> 构建时若缺少 submodule 内容（`faheng-api/skills/` 为空目录），`skill_refs.py` 会静默降级返回空参考，审查仍可运行但不会获得 skill 知识注入。建议 CI / 发布流程显式 `git submodule update --init`。

### HTTPS（自签名证书，解决浏览器麦克风不可用）

公网 IP + HTTP 部署时，浏览器判定为非安全上下文，麦克风（getUserMedia）等 API 被硬性禁用——语音录入只能走"系统录音器上传"兜底。挂载自签名证书开启 HTTPS 后即可浏览器直接录音。

```bash
# 1. 服务器上生成证书（IP 换成实际公网 IP；有效期 395 天，到期重跑+重启容器）。
#    用镜像自带 openssl，宿主机无需安装任何工具；-u 0 必须（脚本会自动把属主
#    修正为容器运行用户 faheng/1000，宿主机无需手工 chown）
mkdir -p tls
sudo docker run --rm -v $(pwd)/tls:/tls -u 0 faheng:latest \
    /bin/bash /app/scripts/gen_cert.sh <公网IP>

# 2. 原部署命令追加证书挂载与两个环境变量（其余不变）
sudo docker run -d --name faheng --restart unless-stopped \
  -p 58069:58069 --env-file .env \
  -v $(pwd)/tls:/tls:ro -e TLS_CERT=/tls/cert.pem -e TLS_KEY=/tls/cert.key \
  faheng:latest
```

切换须知：

- 访问地址改用 `https://<公网IP>:58069`（uvicorn 不做 http→https 跳转，旧 http 书签直接失效）
- 首次访问有浏览器红色警告：Chrome/Edge/安卓点"高级→继续前往"，之后记住例外；**iOS Safari 无法绕过自签证书**（需安装描述文件并手动信任，普通用户不友好），iPhone 用户仍走录音文件上传兜底
- 云厂商安全组需放行 58069 端口（与 HTTP 相同端口，无需新增）
- 不设置 `TLS_CERT`/`TLS_KEY` 则完全保持纯 HTTP 模式，本地 dev 与旧部署不受影响

镜像要点：

- `.env` 不进镜像（`.dockerignore` 已排除），运行时 `--env-file` 注入
- 合同文件**零落盘**：上传/导出全程内存，服务器磁盘不残留用户合同原件（履约模块仅存提取出的节点结构化数据）
- 非 root 用户运行；HEALTHCHECK 复用 `/api/health`
- `--proxy-headers`：前置 Nginx / Cloudflare Tunnel 时 Swagger 重定向 scheme 正确
- SPA history 路由兜底：`/review`、`/draft`、`/compliance`、`/itinerary` 等业务路径刷新/直达回 `index.html`（`/api/*` 不受影响）——公网部署刷新不再 404
- 本地 dev 双进程形态不受影响：`web_dist/` 不存在时后端不挂载静态路由

## 功能流程

**审查**：/login 登录 → /review → 上传合同或载入测试合同 → 开始 AI 审查（约 1-2 分钟）→ 三栏工作台（风险清单 | 合同正文高亮 + 原 docx 段落样式还原 | 法务意见）→ 逐项 采纳/修改/不采纳（选中条款红/橙警示框，采纳/修改后变绿框，不跳转；风险指向 X.Y 子项时按编号精确定位替换段落，保留原编号与字体样式）→ 审核报告 → 导出修改后合同（被替换段落黄色高亮，版式保留）

**起草**：/draft → 关键词（如"ERP软件采购 私有云部署 三年订阅"）→ 生成（1-2 分钟）→ 单栏 TipTap WYSIWYG 编辑器（A4 纸预览 + 工具栏：B/I/H1/H2/P/列表/表格/对齐/撤销重做）→ 对话式修订 → 导出 Word（前端 HTML → 后端 HTML→docx 保真转换，版式与页面所见一致）

**履约提醒**：/compliance → 上传 .docx → 本地条款切分 + 候选预筛 → 后台 LLM 提取履约节点（付款日、交付日等，进度条轮询；周期义务自动展开前 4 期）→ 节点表格（按 待办/逾期/已完成 筛选，支持标记完成/恢复、修正截止日）→ 顶栏铃铛站内通知（到期前一天/当天提醒、逾期天数汇总，进入页面时惰性检查，每节点每类仅一条）

**人员行程**：/itinerary → 人员下拉管理（新增/删除，自动配色；删除级联删行程）→ 悬浮麦克风录音（HTTP 非安全上下文自动降级为系统录音器上传）→ 后端 ASR 转写 → LLM 解析为结构化行程草稿（一段语音可拆多人员/多日期）→ 确认弹窗逐条核对编辑（人员/日期/时间段/事项/类型/地点/摘要/对接人/物料/备注）→ 入库 → 月历视图 + 当日详情抽屉（查看/编辑/删除）

## 目录要点

| 路径 | 说明 |
|---|---|
| `faheng-api/rules/erp_rules.md` | 审核规则库（26 条，改这个文件即换规则） |
| `faheng-api/skills/contract-copilot.skill/` | 合同审查 skill（git submodule，升级审查 Prompt 的知识库） |
| `faheng-api/app/routers/` | 业务路由（auth / review / draft / compliance / itinerary / notifications） |
| `faheng-api/app/parser/clause_splitter.py` | 中文合同"第X条"切分 + 条款内 X.Y 子项扫描（导出回填锚点） |
| `faheng-api/app/llm/client.py` | LLM 结构化输出（清洗/重试/截断抢救） |
| `faheng-api/app/llm/prompts.py` | 审查 / 履约 / 行程解析 Prompt 构造（审查注入 skill 框架 + ERP 规则库 + 12 类合同专项参考） |
| `faheng-api/app/llm/asr.py` | SiliconFlow 语音转写客户端（行程录音 → 文本，含未配置指引） |
| `faheng-api/app/services/skill_refs.py` | skill 参考加载器（带缓存，按合同类型解析 references/contract-types/） |
| `faheng-api/app/services/compliance_service.py` | 履约编排：上传解析 → 后台提取 → 节点物化 → 通知惰性检查 |
| `faheng-api/app/services/compliance_dates.py` | 履约日期确定性计算（锚点+偏移、周期展开无漂移） |
| `faheng-api/app/services/itinerary_service.py` | 人员行程业务层（人员/行程 CRUD、语音解析编排） |
| `faheng-api/app/services/docx_export.py` | 导出三路径：docx 就地替换（支持按子项编号精确替换段落）/ PDF 重建 / HTML→docx 保真转换（前端 WYSIWYG 导出） |
| `faheng-api/data/compliance.db` | SQLite：履约 + 行程持久化（首次运行自动建表） |
| `faheng-web/src/stores/review.js` | 审查工作台状态机（五视图 + 决策乐观更新 + liveScore 风险分派生） |
| `faheng-web/src/stores/review-diff.js` | 前端段落级替换工具（子项编号/Jaccard 相似度锚定，保留 run 级样式） |
| `faheng-web/src/stores/compliance.js` / `itinerary.js` | 履约 / 行程前端状态 |
| `faheng-web/src/components/compliance/`、`itinerary/` | 履约（上传/提取进度/合同卡片/节点表格）与行程（人员选择/月历/语音按钮/确认弹窗/当日抽屉）组件 |
| `Dockerfile` / `.dockerignore` | 单容器多阶段构建（根目录） |

## 已知限制（Demo 定位）

- 审查/起草会话为内存存储：后端重启即丢失（demo 需在单次会话内完成）；履约/行程数据已 SQLite 持久化
- 登录 token 白名单在内存：后端重启后需重新登录（单账号，无用户表）
- Docker 容器重建丢 `data/compliance.db`（默认未挂卷，按需 `-v` 持久化）
- Docker 镜像不含 `exmple/`（`.dockerignore` 排除）：容器内「载入测试合同」按钮不可用，需上传真实合同
- PDF 上传导出时为重新排版的 Word（无法保留原版式，页面有提示）
- 单进程：并发审查会共享内存 session dict
- 行程语音录入依赖外网 ASR（SiliconFlow）：未配置 `ASR_API_KEY` 时该入口报 503 并给出配置指引

## 后续智能体规划

| 智能体 | 说明 |
|---|---|
| 合同起草 ✅ | 已交付 |
| 合同审查 ✅ | 已交付 |
| 履约提醒 ✅ | 已交付（LLM 提取节点 + 确定性日期计算 + 站内通知） |
| 人员行程 ✅ | 已交付（ASR + LLM 解析 + 日历 + 人工确认） |
| 会议纪要 | ASR 转文字 → LLM 结构化纪要 |
| 员工 / 工作内容管理 | CRUD + LLM 辅助字段 |
