# ezContract 智能合同 Demo

客户演示用智能合同系统：**合同起草**（关键词→AI 生成模板→编辑→导出 Word）+ **合同审查**（上传合同→AI 按规则库审查→风险清单→采纳/修改/不采纳→导出修改后合同与审核报告）。

## 架构（Demo 简化版）

```
ezcontract-web (Vue3 + Element Plus + Pinia, :5173)
    │ /api 代理
ezcontract-api (FastAPI, :8000)
    │ OpenAI 兼容接口
LLM 网关 (aihub.ssturing.com, deepseek-v4-flash)
```

- **不使用 RAG / Dify / 数据库**：26 条审核规则（`rules/erp_rules.md`）全量注入审查 prompt
- 内存 session 存储：**重启后端即丢失**，demo 需在单次会话内完成
- 风险分由代码确定性计算（high×15 + medium×7，上限 100）

## 启动

```bash
# 后端（终端 1）
cd ezcontract-api
pip install -r requirements.txt      # 首次
python run.py                        # http://localhost:8000, Swagger: /docs

# 生成测试合同（首次，用于"载入测试合同"按钮）
python scripts/make_sample_docx.py

# 前端（终端 2）
cd ezcontract-web
npm install                          # 首次
npm run dev                          # http://localhost:5173
```

## 配置（ezcontract-api/.env）

```bash
LLM_BASE_URL=https://aihub.ssturing.com/v1   # 注意必须含 /v1
LLM_API_KEY=sk-xxx
LLM_MODEL=deepseek-v4-flash
```

> 网关模型带思维链（reasoning_content 占 token），max_tokens 已调大（审查 12K / 起草 16K），勿调小。

## 演示流程

**审查**：/review → 载入测试合同（19 条款，全部命中规则库）→ 开始 AI 审查（约 1-2 分钟）→ 三栏工作台（风险清单 | 合同正文高亮 | 法务意见）→ 逐项 采纳/修改/不采纳 → 审核报告 → 导出修改后合同（被替换条款黄色高亮，版式保留）

**起草**：/draft → 关键词（如"ERP软件采购 私有云部署 三年订阅"）→ 生成（1-2 分钟）→ 左右分栏编辑/预览 → 对话式修订 → 导出 Word

## 目录要点

| 路径 | 说明 |
|---|---|
| `ezcontract-api/rules/erp_rules.md` | 审核规则库（26 条，改这个文件即换规则） |
| `ezcontract-api/app/parser/clause_splitter.py` | 中文合同"第X条"切分（导出回填锚点） |
| `ezcontract-api/app/llm/client.py` | LLM 结构化输出（清洗/重试/截断抢救） |
| `ezcontract-api/app/services/docx_export.py` | 导出三路径：docx 就地替换 / PDF 重建 / markdown 转换 |
| `ezcontract-api/scripts/make_sample_docx.py` | 生成埋坑测试合同 |
| `ezcontract-web/src/stores/review.js` | 审查工作台状态机（五视图 + 决策乐观更新） |

## 已知限制（Demo 定位）

- 后端重启丢失会话数据（无持久化）
- PDF 上传导出时为重新排版的 Word（无法保留原版式，页面有提示）
- 单进程：并发审查会共享内存 session dict
