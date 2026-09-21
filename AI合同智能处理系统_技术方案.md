# AI 合同智能处理系统 · 技术方案

## 一、项目概述

### 1.1 项目目标

构建一个覆盖商务合同**起草 → 风险审查 → 履约提醒**全生命周期的智能系统，实现：

- 用自然语言/表单快速生成标准化合同
- 基于企业规则库的 AI 自动化风险审查，输出结构化风险清单与审核报告
- 关键履约节点（付款日、交付日等）自动提取与到期提醒

### 1.2 核心原则

- **AI 负责识别、生成、语义判断**；**法务负责确认规则、处理风险、最终决策**（人机协同，AI 不替代人做决定）
- 所有 AI 输出均为"草稿/建议"，保留完整的人工采纳/修改/驳回记录
- 规则库可迭代，AI 能力随规则积累持续增强

---

## 二、整体架构设计

```
┌─────────────────────────────────────────────────────────────┐
│                        前端层（后续扩展）                      │
│         React/Vue 管理后台 + 小程序/企微消息推送              │
└─────────────────────────────────────────────────────────────┘
                              ▲ API
┌─────────────────────────────────────────────────────────────┐
│                    业务服务层（Python FastAPI）              │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐            │
│  │ 合同起草   │  │ 风险审查   │  │ 履约管理   │            │
│  │ Service    │  │ Service    │  │ Service    │            │
│  └────────────┘  └────────────┘  └────────────┘            │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐            │
│  │ 文档解析   │  │ 消息推送   │  │ 定时任务   │            │
│  │ (PDF/Word) │  │ (企微/邮件)│  │ (Celery)   │            │
│  └────────────┘  └────────────┘  └────────────┘            │
└─────────────────────────────────────────────────────────────┘
         ▲ Dify API              ▲ Dify API
┌──────────────────────┐   ┌──────────────────────────────────┐
│  Dify：合同起草 Agent │   │   Dify：合同审查 Agent           │
│  (模板变量填充 + 大模型)│   │   (RAG 检索 + 大模型综合判断)    │
└──────────────────────┘   └──────────────────────────────────┘
         ▲                         ▲
┌──────────────────────┐   ┌──────────────────────────────────┐
│  Dify 知识库：        │   │  Dify 知识库：                   │
│  合同模板库           │   │  企业审核规则库（Word/PDF导入）   │
│  条款素材库           │   │  历史合同案例库                  │
└──────────────────────┘   └──────────────────────────────────┘
         ▲                         ▲
┌─────────────────────────────────────────────────────────────┐
│                       数据存储层                             │
│     PostgreSQL（业务数据） +  Dify内置向量库（知识库）        │
└─────────────────────────────────────────────────────────────┘
```

---

## 三、技术栈明细

| 层级 | 技术选型 | 说明 |
|------|---------|------|
| 后端框架 | **Python 3.11 + FastAPI** | 异步、高性能，原生支持 OpenAPI 文档 |
| AI 引擎 | **Dify（开源版）** | 内置 RAG、Agent 编排、知识库管理、API 发布 |
| 大模型 | 通义千问 / DeepSeek / 本地部署模型 | Dify 支持多模型路由，可灵活切换 |
| 文档解析 | python-docx / PyMuPDF / pdfplumber | Word 和 PDF 的文本与结构提取 |
| 向量数据库 | Dify 内置（Weaviate/Milvus/pgvector） | 开箱即用，无需单独搭建 |
| 业务数据库 | **PostgreSQL 15+** | 存储合同、用户、审批流、履约记录 |
| ORM | **SQLAlchemy 2.0** | Python 主流 ORM |
| 定时任务 | **Celery + Redis** | 履约到期扫描、定时提醒 |
| 消息推送 | 企业微信 Webhook / 邮件（SMTP） | 履约提醒触达 |
| 部署 | **Docker Compose** | 整套服务容器化，WSL 可直接运行 |
| 鉴权 | JWT + 角色权限（RBAC） | 多角色：业务员/法务/管理员 |

---

## 四、系统模块拆解

### 4.1 合同起草模块

#### 业务流程

```
用户输入需求描述/填写表单 → FastAPI 接收 → 调用 Dify 起草 Agent API
→ Agent 检索模板库 + 填充变量 → 返回合同草稿（Markdown/HTML）
→ 用户在线编辑确认 → 保存至数据库
```

#### Dify 侧配置

- 创建一个 **Chatflow 类型应用**（合同起草 Agent）
- 挂载知识库：合同模板库（按合同类型分类：采购/销售/NDA/劳动等）
- 编排逻辑：需求理解 → 匹配模板类型 → 提取关键变量（甲方/乙方/金额/周期）→ 生成合同

#### FastAPI 侧接口

- `POST /api/contracts/draft` — 提交起草需求，返回草稿
- `POST /api/contracts/draft/{id}/revise` — 基于反馈修改草稿
- `POST /api/contracts/draft/{id}/finalize` — 确认草稿，生成正式合同文件

---

### 4.2 风险审查模块（核心）

#### 业务流程（严格对照流程图）

```
上传合同文件（Word/PDF）
    → FastAPI 接收，存储原文件
    → 文档解析：提取全文 + 按条款切分
    → 遍历每个条款：
        ├─ 调用 Dify 审查 Agent API（传入条款文本）
        ├─ Dify 侧：RAG 召回 Top K 审核规则 + 大模型综合判断
        └─ 返回：风险等级 / 命中规则 / 法务建议 / 修改条款
    → 汇总所有条款结果 → 生成风险清单
    → 法务处理：逐项 采纳/修改/不采纳
    → 生成最终审核报告
```

#### Dify 侧配置

- 创建一个 **Workflow 类型应用**（合同审查 Agent）
- 挂载知识库：企业审核规则库（从历史审核规范、法务制度、标准合同中提取）
- 工作流编排：
  1. **输入节点**：接收合同条款文本
  2. **知识检索节点**：从规则库召回 Top K 相关规则
  3. **LLM 节点**：结合条款 + 召回规则，做综合判断
  4. **输出节点**：结构化输出 JSON（风险等级、命中规则编号、建议）

#### FastAPI 侧接口

- `POST /api/contracts/review/upload` — 上传合同，触发解析
- `GET /api/contracts/review/{id}/status` — 查询审查进度
- `GET /api/contracts/review/{id}/result` — 获取风险清单
- `POST /api/contracts/review/{id}/decision` — 法务对某条风险做决策
- `GET /api/contracts/review/{id}/report` — 生成审核报告（PDF）

#### 关键数据结构

```python
# 合同审查记录
class ReviewRecord(Base):
    id = Column(UUID, primary_key=True)
    contract_id = Column(UUID, ForeignKey("contracts.id"))
    file_url = Column(String)              # 原文件路径
    status = Column(Enum("pending", "processing", "completed"))
    total_risks = Column(Integer)           # 总风险数
    high_risks = Column(Integer)            # 高风险数
    created_at = Column(DateTime)

# 单条风险项
class RiskItem(Base):
    id = Column(UUID, primary_key=True)
    review_id = Column(UUID, ForeignKey("review_records.id"))
    clause_text = Column(Text)              # 命中条款原文
    clause_location = Column(String)        # 条款位置（如第3.2条）
    risk_level = Column(Enum("high", "medium", "low"))
    matched_rules = Column(JSON)            # 命中的规则列表
    ai_suggestion = Column(Text)            # AI 修改建议
    legal_decision = Column(Enum("adopt", "modify", "reject"), nullable=True)
    legal_comment = Column(Text)            # 法务处理意见
```

---

### 4.3 履约提醒模块

#### 业务流程

```
合同生效后 → FastAPI 提取关键履约节点（付款日/交付日/验收日等）
→ 写入定时任务队列（Celery）
→ 到期前 N 天 → 自动推送提醒（企微/邮件）
→ 记录提醒状态，逾期升级提醒
```

#### Dify 侧配置

- 创建一个 **Chatflow 类型应用**（履约节点提取 Agent）
- 输入：已签署的合同全文
- 输出：JSON 格式的关键节点列表

```json
[
  {"node_type": "付款", "amount": 50000, "due_date": "2026-10-15", "party": "甲方"},
  {"node_type": "交付", "description": "首批货物交付", "due_date": "2026-11-01"}
]
```

#### FastAPI 侧接口

- `POST /api/contracts/fulfillment/extract/{contract_id}` — 提取履约节点
- `GET /api/contracts/fulfillment/{contract_id}` — 查询履约计划
- `POST /api/contracts/fulfillment/{node_id}/confirm` — 标记节点已完成

#### Celery 定时任务

```python
@celery.task
def check_fulfillment_due():
    # 每日扫描即将到期的履约节点
    today = date.today()
    due_nodes = FulfillmentNode.query.filter(
        FulfillmentNode.due_date <= today + timedelta(days=3),
        FulfillmentNode.status == "pending"
    ).all()
    for node in due_nodes:
        send_reminder(node)  # 企微/邮件推送
```

---

## 五、部署方案（Ubuntu + Docker Compose）

### 5.1 环境要求

- Ubuntu 22.04
- 内存 ≥ 8GB（Dify + 大模型 API 调用对内存要求不高，本地跑模型除外）

### 5.2 容器清单

| 容器 | 镜像 | 端口 | 说明 |
|------|------|------|------|
| dify-api | langgenius/dify-api:latest | 5001 | Dify API 服务 |
| dify-web | langgenius/dify-web:latest | 3000 | Dify Web 管理台 |
| dify-db | postgres:15 | 5432 | Dify 元数据库 |
| dify-redis | redis:7 | 6379 | 缓存+队列 |
| dify-weaviate | semitechnologies/weaviate | 8080 | 向量数据库 |
| app-api | fastapi-app:latest | 8000 | 你的 FastAPI 业务服务 |
| app-db | postgres:15 | 5433 | 业务数据库 |
| app-redis | redis:7 | 6380 | Celery 消息队列 |
| app-celery | fastapi-app:celery | — | Celery Worker |

### 5.3 部署步骤

```bash
# 2. 创建项目目录
mkdir -p ~/ai-contract && cd ~/ai-contract

# 3. 拉取 Dify 官方 Docker Compose
git clone https://github.com/langgenius/dify.git
cd dify/docker
cp .env.example .env

# 4. 启动 Dify
docker compose up -d

# 5. 回到项目根目录，创建你的 FastAPI 服务
cd ~/ai-contract
mkdir fastapi-app && cd fastapi-app
```

#### 目录结构

```
fastapi-app/
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── main.py
├── app/
│   ├── api/          # 路由
│   ├── services/     # 业务逻辑
│   ├── models/       # SQLAlchemy 模型
│   ├── schemas/      # Pydantic 校验
│   └── core/         # Dify API 客户端、Celery 配置
```

### 5.4 FastAPI Dockerfile 示例

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 5.5 Dify API 调用封装示例

```python
# app/core/dify_client.py
import httpx

class DifyClient:
    def __init__(self, api_key: str, base_url: str = "http://dify-api:5001/v1"):
        self.api_key = api_key
        self.base_url = base_url

    async def chat(self, app_id: str, inputs: dict, query: str) -> dict:
        # 调用 Dify Chatflow/Workflow API
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/chat-messages",
                json={
                    "inputs": inputs,
                    "query": query,
                    "response_mode": "blocking",
                    "user": "system",
                },
                headers={"Authorization": f"Bearer {self.api_key}"}
            )
            return response.json()
```

---

## 六、开发路线图（分期）

| 阶段 | 交付物 | 里程碑 |
|------|--------|--------|
| **Phase 1** | Dify 环境搭建 + 规则库导入 + FastAPI 基础框架 | 合同上传 → 规则召回 → 返回 JSON |
| **Phase 2** | 合同解析引擎 + 审查全流程打通 + 审核报告生成 | 上传PDF → 输出完整风险清单 |
| **Phase 3** | 合同起草 Agent + 模板管理 + 在线编辑 | 表单输入 → 生成合同草稿 |
| **Phase 4** | 履约节点提取 + Celery 定时提醒 + 企微推送 | 合同生效 → 到期自动提醒 |
| **Phase 5** | 前端管理后台 + 权限体系 + 数据统计看板 | 完整产品化 |

---

## 七、风险与挑战

| 风险点 | 应对方案 |
|--------|----------|
| 合同 PDF 格式复杂（扫描件/表格/多栏） | 优先支持文本型 PDF + Word，扫描件走 OCR（可用 PaddleOCR） |
| 大模型输出不稳定 | Dify Workflow 中加"结构化输出"校验节点，失败自动重试 |
| 规则召回不准确 | 定期用历史合同做 RAG 测试集，优化切片策略和 Embedding 模型 |
| 数据安全 | 本地部署 Dify + 私有模型；合同文件不落第三方云端 |

---

## 八、启动命令速查

```bash
# 启动 Dify
cd ~/ai-contract/dify/docker
docker compose up -d

# 启动你的 FastAPI 服务
cd ~/ai-contract/fastapi-app
docker compose up -d

# 查看服务状态
docker ps

# 访问入口
# Dify 管理台：http://localhost:3000
# FastAPI 文档：http://localhost:8000/docs
# FastAPI API：  http://localhost:8000/api/...
```

---

## 九、Demo 实施方案（已落地）

> 2026-09 更新：客户演示阶段已按"最小可用闭环"实现，架构相对原方案大幅简化。
> 代码位于 `faheng-api/`（FastAPI）与 `faheng-web/`（Vue3），详见根目录 `README.md`。

### 9.1 架构简化决策

| 原方案 | Demo 实现 | 原因 |
|--------|----------|------|
| Dify（Chatflow/Workflow + 知识库） | **直连 LLM 网关**（OpenAI 兼容接口） | 演示阶段无需编排平台，Prompt + 代码编排足够 |
| RAG 检索规则库 | **规则全量注入 Prompt** | 26 条规则 ≈ 1.5K 字，远小于上下文窗口；全量注入无漏召回、结果可复现 |
| PostgreSQL + SQLAlchemy | **内存 session** | demo 无持久化需求，重启即失可接受 |
| Celery + Redis 后台任务 | **asyncio.create_task** | 单进程 demo 足够，进度写 session 供轮询 |
| JWT + RBAC | 无鉴权 | 演示环境 |

**RAG 升级触发线**（满足任一再升级，升级只换"规则注入方式"，prompt/前端/schema 不动）：
规则库超过 ~100 条或 30K token；多合同类型挂不同规则库；法务要求规则级版本管理与审计。

### 9.2 两条核心流程

**合同起草**：关键词（+可选类型/甲乙双方/补充要求）→ LLM 生成 Markdown 合同（第X条编号、占位符、甲方立场）→ 左右分栏编辑/预览（防抖保存）→ 对话式修订（每次"当前全文+指令"整篇重生成）→ 导出 Word

**合同审查**：上传 DOCX/PDF → 按"第X条"切分条款（记录段落区间锚点）→ 分批审查（每批 ≤8 条条款，规则库全量注入 prompt，temperature=0）→ 风险清单（条款号/等级/命中规则/风险说明/影响/建议替换条款）→ 三栏工作台（风险列表 | 合同正文高亮联动 | 法务意见）→ 逐项 采纳/修改/不采纳 → 导出修改后合同（就地替换+黄色高亮，版式保留）+ 审核报告

### 9.3 从 Docspect 参考项目继承的工程经验

- LLM 结构化输出三段式：去围栏清洗 → 尾逗号修复 → **截断抢救**（救回完整元素）+ 失败重试（附错误原因）
- 风险分**由代码确定性计算**（high×15 + medium×7），不让 LLM 拍脑袋
- 网关模型带思维链：max_tokens 必须给足（审查 12K / 起草 16K）

### 9.4 审查后导出 Word 的三条路径（难点）

1. **DOCX 上传 → 原文档就地替换**：python-docx 重开原件，只动命中条款段落区间，保样式+黄色高亮，表格/签署栏原样保留
2. **PDF 上传 → 重建降级**：无法保真转 docx，用切分结果重建干净 Word（页面明示"重新排版导出"）
3. **起草 Markdown → docx 轻量转换**（标题/粗体/列表，显式设置中文字体 w:eastAsia）

---

## 十、需求备忘与后续规划

> 本节为需求备忘，记录核心目标、扩展方向与参考资料，供后续迭代参考。

### 10.1 主要需求

- 商务合同**起草**
- 商务合同**风险审查**
- 合同**履约提醒**（关键节点到期提醒）

### 10.2 后续扩展方向

- 会议纪要管理
- 员工管理
- 工作内容管理

### 10.3 关键词

`合同起草` · `审查` · `法律 AI 助手` · `语音转文字（ASR）`

### 10.4 参考资料

- 参考视频：<https://www.bilibili.com/video/BV1ihts6KEYo>
- 参考截图：

  ![image-20260920174047911](C:\Users\ottol\Desktop\images\image-20260920174047911.png)
