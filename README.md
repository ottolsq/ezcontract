# 法衡 AI · 企业多智能体工作台（Demo）

> 品牌定位：**法衡 AI** —— 企业多智能体工作台。当前交付合同双智能体（起草 / 审查），后续扩展履约提醒、会议纪要、员工管理、工作内容管理等智能体。

客户演示用智能合同模块：**合同起草**（关键词→AI 生成模板→编辑→导出 Word）+ **合同审查**（上传合同→AI 按规则库审查→风险清单→采纳/修改/不采纳→导出修改后合同与审核报告）。

## 架构（Demo 简化版）

```
faheng-web (Vue3 + Element Plus + Pinia, :58068)
    │ /api 代理
faheng-api (FastAPI, :58069)
    │ OpenAI 兼容接口
LLM 网关 (aihub.ssturing.com, deepseek-v4-flash)
```

- **不使用 RAG / Dify / 数据库**：26 条审核规则（`rules/erp_rules.md`）全量注入审查 prompt
- 内存 session 存储：**重启后端即丢失**，demo 需在单次会话内完成
- 风险分由代码确定性计算（high×15 + medium×7，上限 100）

## 启动

```bash
# 后端（终端 1）
cd faheng-api
pip install -r requirements.txt      # 首次
python run.py                        # http://localhost:58069, Swagger: /docs

# 生成测试合同（首次，用于"载入测试合同"按钮）
python scripts/make_sample_docx.py

# 前端（终端 2）
cd faheng-web
npm install                          # 首次
npm run dev                          # http://localhost:58068
```

## 配置（faheng-api/.env）

```bash
LLM_BASE_URL=https://aihub.ssturing.com/v1   # 注意必须含 /v1
LLM_API_KEY=sk-xxx
LLM_MODEL=deepseek-v4-flash
```

> 网关模型带思维链（reasoning_content 占 token），max_tokens 已调大（审查 12K / 起草 16K），勿调小。

## Docker 部署（单容器交付）

多阶段构建（根目录 [Dockerfile](Dockerfile)）：`node:20-alpine` 构建前端 → `python:3.11-slim` 安装后端依赖并拷入业务代码与前端产物，**单个 uvicorn 进程同时 serve 前端静态页面与 API**（同源，端口 58069）。

```bash
# 构建（仓库根目录执行）
docker build -t faheng:latest .

# 运行（.env 按"配置"章节准备，放在当前目录）
docker run -d --name faheng --restart unless-stopped \
  -p 58069:58069 --env-file .env faheng:latest

# 探活
curl http://127.0.0.1:58069/api/health
```

离线交付（目标服务器不走镜像仓库）：

```bash
docker save -o faheng-latest.tar faheng:latest
scp -P <ssh端口> faheng-latest.tar user@<服务器>:~/
# 登录目标服务器后：
docker load -i faheng-latest.tar
# 准备 .env（tar 不含密钥，必须在服务器上另备）后 docker run，命令同上
```

镜像要点：

- `.env` 不进镜像（`.dockerignore` 已排除），运行时 `--env-file` 注入
- 合同文件**零落盘**：上传/导出全程内存，服务器磁盘不残留用户合同
- 非 root 用户运行；HEALTHCHECK 复用 `/api/health`
- `--proxy-headers`：前置 Nginx / Cloudflare Tunnel 时 Swagger 重定向 scheme 正确
- 本地 dev 双进程形态不受影响：`web_dist/` 不存在时后端不挂载静态路由

## 演示流程

**审查**：/review → 载入测试合同（20 条款，全部命中规则库）→ 开始 AI 审查（约 1-2 分钟）→ 三栏工作台（风险清单 | 合同正文高亮 + 原 docx 段落样式还原 | 法务意见）→ 逐项 采纳/修改/不采纳 → 审核报告 → 导出修改后合同（被替换条款黄色高亮，版式保留）

**起草**：/draft → 关键词（如"ERP软件采购 私有云部署 三年订阅"）→ 生成（1-2 分钟）→ 单栏 TipTap WYSIWYG 编辑器（A4 纸预览 + 工具栏：B/I/H1/H2/P/列表/表格/对齐/撤销重做）→ 对话式修订 → 导出 Word（前端 HTML → 后端 HTML→docx 保真转换，版式与页面所见一致）

## 目录要点

| 路径 | 说明 |
|---|---|
| `faheng-api/rules/erp_rules.md` | 审核规则库（26 条，改这个文件即换规则） |
| `faheng-api/app/parser/clause_splitter.py` | 中文合同"第X条"切分（导出回填锚点） |
| `faheng-api/app/llm/client.py` | LLM 结构化输出（清洗/重试/截断抢救） |
| `faheng-api/app/services/docx_export.py` | 导出三路径：docx 就地替换 / PDF 重建 / HTML→docx 保真转换（前端 WYSIWYG 导出） |
| `faheng-api/scripts/make_sample_docx.py` | 生成埋坑测试合同（输出到项目根，构建期嵌入镜像） |
| `faheng-web/src/stores/review.js` | 审查工作台状态机（五视图 + 决策乐观更新） |
| `Dockerfile` / `.dockerignore` | 单容器多阶段构建（根目录） |

## 已知限制（Demo 定位）

- 后端重启丢失会话数据（无持久化）
- PDF 上传导出时为重新排版的 Word（无法保留原版式，页面有提示）
- 单进程：并发审查会共享内存 session dict

## 后续智能体规划

| 智能体 | 说明 |
|---|---|
| 合同起草 ✅ | 已交付 |
| 合同审查 ✅ | 已交付 |
| 履约提醒 | LLM 提取合同履约节点 → 定时扫描 → 到期推送 |
| 会议纪要 | ASR 转文字 → LLM 结构化纪要 |
| 员工 / 工作内容管理 | CRUD + LLM 辅助字段 |
