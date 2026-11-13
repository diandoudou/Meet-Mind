# MeetMind RAG 知识检索设计文档

> **版本**: v1.0  
> **范围**: 第 2 周 — 向量库 + Embedding Pipeline + GlobalSearch + Project 助手（带 Citation）  
> **前置依赖**: 第 1 周 LangGraph 停录 Pipeline、后端 `/api/chat`、Gemini Key 仅服务端

---

## 1. 背景与目标

### 1.1 现状问题

| 模块 | 现状 | 问题 |
|------|------|------|
| `GlobalSearch.tsx` | 硬编码 mock 结果 | 无法检索真实会议/PDF |
| `ProjectDetail` 助手 | 把全部 meeting summary 拼进 prompt | 上下文窗口浪费、无引用溯源、长项目失真 |
| `Assistant.tsx` | Firestore 拉取 + `/api/chat` | 同上，无向量检索 |
| `pdf_term_extractor.py` | 仅抽词注入 ASR 热词 | PDF 正文未进入知识库 |
| Firestore | 存 transcript/summary | 适合元数据，不适合语义检索 |

### 1.2 第 2 周目标

1. **Indexing Pipeline**：会议停录、PDF 上传后自动 chunk → embed → 写入向量库  
2. **Retrieval API**：后端提供 `/api/rag/search` 与 `/api/rag/chat`  
3. **GlobalSearch**：替换 mock，展示 Top-K 片段 + 来源链接  
4. **Project 助手**：RAG 问答，回答带 **Citation**（meetingId / fileId / chunkId）  
5. **权限**：检索结果必须按 `ownerUid` / `projectId` 过滤，与 Firestore Rules 一致  

### 1.3 非目标（本阶段不做）

- 微调 Embedding 模型  
- 复杂 Agentic RAG（多跳推理、自主拆 query）  
- 替换 Firestore 作为主业务库  

---

## 2. 总体架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           数据源 (Sources)                               │
│  Firestore meetings/transcript │ Firestore files │ PDF (Storage)         │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │ 触发 Index
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     Indexing Pipeline (异步)                             │
│  Extract → Clean → Chunk → Embed → Upsert Vector Store                    │
│  触发点: POST /stop 完成 │ PDF 上传 webhook │ 手动 POST /api/rag/reindex   │
└───────────────────────────────┬─────────────────────────────────────────┘
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     Vector Store (Chroma / pgvector)                     │
│  collection: meetmind_chunks                                             │
│  metadata: userId, projectId, sourceType, sourceId, title, speaker, ts    │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │ Query
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     Retrieval Layer                                        │
│  Query Rewrite(可选) → Hybrid Search(BM25+Vector) → Rerank → Top-K       │
└───────────────────────────────┬─────────────────────────────────────────┘
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     Generation Layer                                       │
│  Context 组装 + Citation 约束 Prompt → Gemini → 结构化回答 + citations   │
└───────────────────────────────┬─────────────────────────────────────────┘
                                ▼
         GlobalSearch UI │ ProjectDetail Assistant │ Assistant Hub
```

### 2.1 设计原则

| 原则 | 说明 |
|------|------|
| **Write-on-ingest** | 索引在「会议结束 / 文件上传」时写入，查询时只读向量库 |
| **Metadata 强绑定** | 每条 chunk 必须带 `userId` + `projectId`，检索必 filter |
| **Citation 可追溯** | 生成答案必须引用 chunk metadata，UI 可跳转原会议/文件 |
| **Hybrid 优先** | 中英混杂 + 专业术语场景，向量 + 关键词比纯向量更稳 |
| **Graceful Degrade** | 向量库不可用时，降级为 Firestore 关键词搜索 + 摘要拼接 |

---

## 3. 数据模型

### 3.1 Chunk 文档结构

```python
# backend/src/rag/models.py
class KnowledgeChunk(BaseModel):
    chunk_id: str              # uuid
    text: str                  # 切块正文
    embedding: list[float]     # 768/1536 维，取决于模型

    # 权限与归属
    owner_uid: str
    project_id: str

    # 溯源
    source_type: Literal["meeting_transcript", "meeting_summary", "pdf", "action_item"]
    source_id: str             # meetingId / fileId
    source_title: str          # 会议标题 / 文件名

    # 定位
    chunk_index: int           # 同一 source 内序号
    speaker: str | None        # 转录片段说话人
    start_ts: int | None       # transcript timestamp ms
    page_number: int | None    # PDF 页码

    # 检索辅助
    keywords: list[str]        # jieba 抽词，供 BM25
    created_at: int
    content_hash: str          # 幂等 upsert，防重复索引
```

### 3.2 向量库选型（推荐方案）

| 方案 | 优点 | 缺点 | MeetMind 建议 |
|------|------|------|---------------|
| **Chroma** | 纯 Python、本地零配置、LangChain 原生 | 生产扩展性一般 | **MVP / 面试 Demo 首选** |
| **pgvector** | SQL + 向量、事务、权限好做 | 需 Postgres 运维 | 政企私有化部署 |
| **Milvus** | 大规模、高性能 | 运维重 | 百万 chunk 以上 |

**第 2 周默认**: `Chroma` 持久化到 `backend/data/chroma/`

环境变量:

```env
RAG_VECTOR_STORE=chroma
RAG_EMBEDDING_MODEL=gemini-embedding-001   # 或 text-embedding-004
RAG_CHUNK_SIZE=512
RAG_CHUNK_OVERLAP=64
RAG_TOP_K=8
RAG_RERANK_TOP_N=4
```

---

## 4. Indexing Pipeline 设计

### 4.1 触发时机

| 事件 | 索引内容 | 实现位置 |
|------|----------|----------|
| `POST /stop` 成功 | transcript 按说话人/段落 chunk；summary 整段或按议题 chunk | `websocket_server.py` 末尾 async task |
| PDF 上传完成 | PDF 正文 chunk（复用 `pdf_term_extractor` 解析路径） | 新增 `POST /api/rag/index/file` |
| 手动重建 | 某 project 全量 reindex | `POST /api/rag/reindex` |

### 4.2 处理流程

```
Raw Document
    │
    ├─ meeting_transcript
    │     → 按 TranscriptEntry 合并相邻同 speaker 段落
    │     → 超长段 sliding window (512 tokens, overlap 64)
    │
    ├─ meeting_summary (structured JSON)
    │     → 每个 topic / decision / next_step 独立 chunk
    │
    └─ pdf
          → PyMuPDF / pdfplumber 抽文本
          → 按段落 chunk，保留 page_number
    │
    ▼
Clean (去空白、normalize 中英文标点)
    │
    ▼
Embed (batch, max 100 chunks/request)
    │
    ▼
Upsert (content_hash 去重)
```

### 4.3 目录规划

```
backend/src/rag/
├── __init__.py
├── models.py              # KnowledgeChunk, SearchResult, Citation
├── chunker.py             # 会议/PDF 切块策略
├── embedder.py            # Gemini Embedding 封装
├── vector_store.py        # Chroma CRUD + filter
├── indexer.py             # 编排 ingest
├── retriever.py           # hybrid search + rerank
├── rag_chain.py           # RAG prompt + citation 解析
└── pdf_term_extractor.py  # 已有，索引时复用 PDF 文本提取
```

### 4.4 核心接口（Indexing）

```python
# indexer.py
async def index_meeting(
    *,
    owner_uid: str,
    project_id: str,
    meeting_id: str,
    title: str,
    transcript: list[dict],
    summary_structured: dict | None,
) -> IndexResult: ...

async def index_pdf_file(
    *,
    owner_uid: str,
    project_id: str,
    file_id: str,
    file_path: str,
    title: str,
) -> IndexResult: ...
```

---

## 5. Retrieval 设计

### 5.1 检索流程

```
User Query: "LiDAR 标定参数上次定是多少？"
    │
    ▼
[Optional] Query Rewrite
    → "LiDAR calibration parameters decision meeting"
    │
    ▼
Vector Search (top_k=20)
    filter: owner_uid == current_user AND (project_id == X OR global)
    │
    ▼
BM25 / Keyword Search (top_k=20)
    同一 filter，jieba 分词 + 倒排（Chroma where_document 或本地 BM25）
    │
    ▼
Reciprocal Rank Fusion (RRF) 合并
    │
    ▼
[Optional] Reranker (cross-encoder / LLM score)
    → top_n=4~8
    │
    ▼
Return SearchResult[] with scores + metadata
```

### 5.2 API 设计

#### `POST /api/rag/search` — GlobalSearch 用

```json
// Request
{
  "query": "LiDAR 标定",
  "project_id": null,
  "top_k": 10
}

// Response
{
  "results": [
    {
      "chunk_id": "c-uuid",
      "score": 0.87,
      "text": "LiDAR calibration constant set to 0.42v ...",
      "source_type": "meeting_transcript",
      "source_id": "mtg-123",
      "source_title": "Robot Vision Sync",
      "project_id": "proj-1",
      "project_name": "Robot Vision",
      "speaker": "Alice",
      "timestamp": 1710000000000,
      "citation_label": "[1]"
    }
  ]
}
```

#### `POST /api/rag/chat` — Project 助手用（带 Citation）

```json
// Request
{
  "message": "上次关于 LiDAR 的决策是什么？",
  "project_id": "proj-1",
  "conversation_id": "optional"
}

// Response
{
  "answer": "根据 3 月 12 日会议，团队决定将 LiDAR 标定常数设为 0.42v [1]。",
  "citations": [
    {
      "label": "[1]",
      "chunk_id": "c-uuid",
      "source_type": "meeting_transcript",
      "source_id": "mtg-123",
      "source_title": "Robot Vision Sync",
      "excerpt": "LiDAR calibration constant set to 0.42v ...",
      "url_path": "/project/proj-1?meeting=mtg-123"
    }
  ],
  "retrieval_meta": {
    "chunks_used": 4,
    "latency_ms": 820
  }
}
```

### 5.3 RAG Prompt 模板（Citation 约束）

```text
System:
你是 MeetMind 项目知识助手。只能根据「检索上下文」回答，禁止编造。
每条事实必须在句末标注引用编号，如 [1][2]。
若上下文不足，明确说「知识库中未找到相关信息」。

Context:
[1] (meeting: Robot Vision Sync, 2026-03-12, Alice)
LiDAR calibration constant set to 0.42v during Tuesday session.

[2] (pdf: lidar_spec.pdf, p.3)
Recommended calibration range is 0.40–0.45v.

User:
{question}

Assistant:
```

---

## 6. 前端改造规划

### 6.1 GlobalSearch.tsx

| 改动 | 说明 |
|------|------|
| 删除 mock 数组 | 调用 `POST /api/rag/search` |
| 结果卡片 | 展示 `source_type`、`project_name`、`excerpt`、`score` |
| 点击跳转 | `meeting` → `/project/{id}?meeting={mid}`；`pdf` → 文件下载链接 |
| 加载/空态 | Loading spinner、无结果提示 |
| 鉴权 | 请求头带 Firebase ID Token（后端校验 `owner_uid`） |

新增 `frontend/src/services/rag.ts`:

```typescript
export async function searchKnowledge(query: string, projectId?: string)
export async function ragChat(message: string, projectId: string)
```

### 6.2 ProjectDetail 助手

| 改动 | 说明 |
|------|------|
| 替换 `chatWithAssistant` | 改用 `ragChat(projectId)` |
| 消息结构 | `{ role, content, citations?: Citation[] }` |
| Citation UI | 回答下方展示可点击引用卡片 `[1] Robot Vision Sync` |
| 点击 citation | 打开对应 meeting 详情 drawer |

### 6.3 类型扩展 (`types.ts`)

```typescript
export interface RagCitation {
  label: string;
  chunk_id: string;
  source_type: 'meeting_transcript' | 'meeting_summary' | 'pdf' | 'action_item';
  source_id: string;
  source_title: string;
  excerpt: string;
  url_path?: string;
}

export interface RagSearchResult {
  chunk_id: string;
  score: number;
  text: string;
  source_type: string;
  source_id: string;
  source_title: string;
  project_id: string;
  project_name?: string;
  speaker?: string;
  timestamp?: number;
}
```

---

## 7. 与现有系统集成

### 7.1 停录后自动索引

在 `websocket_server.py` 的 `POST /stop` 中，LangGraph 完成后：

```python
# 异步，不阻塞响应
asyncio.create_task(index_meeting_async(
    owner_uid=...,  # 从请求 JWT 解析
    project_id=payload.project_id,
    meeting_id=meeting_id,
    transcript=transcript_entries,
    summary_structured=summary_structured,
))
```

### 7.2 PDF 双用途

| 路径 | 用途 |
|------|------|
| 现有 `/upload-pdf` | ASR 热词注入（实时） |
| 新增 index pipeline | PDF 正文入向量库（检索） |

### 7.3 权限模型

```
检索 filter 必须包含:
  owner_uid == token.uid
  OR project_id IN user_accessible_projects

user_accessible_projects =
  Firestore projects where ownerUid == uid OR uid in members
```

**绝不**仅依赖前端传 `project_id` 而不校验。

---

## 8. 实施计划（第 2 周排期）

### Day 1–2: 基础设施

- [ ] 创建 `backend/src/rag/` 模块骨架  
- [ ] 实现 `embedder.py`（Gemini Embedding）  
- [ ] 实现 `vector_store.py`（Chroma persist）  
- [ ] 实现 `chunker.py`（transcript + summary + pdf）  
- [ ] 单元测试：chunk 数量、overlap、hash 幂等  

### Day 3: Indexing

- [ ] 实现 `indexer.py`  
- [ ] `POST /stop` 后触发 `index_meeting`  
- [ ] `POST /api/rag/reindex?project_id=`  
- [ ] 日志：indexed_chunks, skipped_duplicates, duration_ms  

### Day 4: Retrieval API

- [ ] 实现 `retriever.py`（vector + keyword RRF）  
- [ ] `POST /api/rag/search`  
- [ ] `POST /api/rag/chat` + citation 解析  
- [ ] Firebase Token 鉴权中间件  

### Day 5: 前端

- [ ] `services/rag.ts`  
- [ ] 改造 `GlobalSearch.tsx`  
- [ ] 改造 `ProjectDetail` 助手 + Citation UI  
- [ ] 可选：改造 `Assistant.tsx` 全局 RAG  

### Day 6–7: 评测与文档

- [ ] 准备 20 条 eval QA pairs（`evaluation/rag_eval.json`）  
- [ ] 指标：Recall@5、Citation Accuracy、Answer Faithfulness  
- [ ] 更新 README、本设计文档  

---

## 9. 评测方案（LlamaIndex）

### 9.1 测试集 (`evaluation/rag_eval.json`)

```json
[
  {
    "id": "lidar-const",
    "question": "LiDAR 标定常数是多少？",
    "project_id": "proj-1",
    "owner_uid": "test-user",
    "expected_keywords": ["0.42", "LiDAR"],
    "expected_source_id": "mtg-20260312",
    "reference_answer": "LiDAR 标定常数为 0.42。"
  }
]
```

### 9.2 指标

| 指标 | 定义 | 实现 |
|------|------|------|
| **Recall@K** | 正确 source / keyword 是否在 Top-K | 本地计算 |
| **MRR** | 首个正确结果排名倒数 | 本地计算 |
| **Citation Accuracy** | 回答中 `[n]` 是否落在检索编号内 | 本地计算 |
| **Faithfulness** | 回答是否忠实于 context（无幻觉） | LlamaIndex `FaithfulnessEvaluator` |
| **Relevancy** | 回答+context 是否贴合问题 | LlamaIndex `RelevancyEvaluator` |
| **Correctness** | 相对 `reference_answer` 是否正确 | LlamaIndex `CorrectnessEvaluator`（有参考答案时） |

Judge LLM 默认用 **Gemini**（`GEMINI_API_KEY`），也可设 `OPENAI_API_KEY`。

### 9.3 运行

```bash
cd backend
pip install llama-index-core llama-index-llms-google-genai
PYTHONPATH=src python -m evaluation.llamaindex_rag_eval
PYTHONPATH=src python -m evaluation.llamaindex_rag_eval --retrieval-only   # 仅检索指标
# 报告输出: evaluation/reports/latest_llamaindex_eval.json
```

评测直接调用现有 `search_knowledge` + `rag_chat`，**不重建** LlamaIndex 索引，保证测的是 MeetMind 线上 RAG 链路。

### 9.4 目标阈值（参考）

| 指标 | 目标 |
|------|------|
| Recall@5 | ≥ 0.85 |
| MRR | ≥ 0.70 |
| Citation Accuracy | ≥ 0.90 |
| Faithfulness | ≥ 0.85 |
| Relevancy | ≥ 0.85 |
| P95 Latency | search < 500ms, chat < 3s |

### 9.5 A/B 对比（面试加分）

| 方案 | Recall@5 | 说明 |
|------|----------|------|
| 纯 Firestore 摘要拼接 | ~0.45 | 当前 baseline |
| 纯向量检索 | ~0.75 | 语义好，专有名词弱 |
| **Hybrid + Rerank** | ~0.88 | 推荐方案 |

---

## 10. 风险与降级

| 风险 |  mitigation |
|------|-------------|
| Embedding API 限流 | batch + 队列 + 指数退避 |
| 向量库损坏 | 定期 snapshot `backend/data/chroma/` |
| 长 transcript 索引慢 | 异步 indexing + UI「索引中」状态 |
| 幻觉 | Citation 约束 prompt + 「未找到」模板 + 低 confidence 拒答 |
| 权限泄露 | 检索层强制 metadata filter，单测覆盖越权 query |

降级链:

```
Hybrid RAG → 纯向量 → Firestore 关键词 → 「暂未索引，请稍后再试」
```

---

## 11. 面试：RAG 高频问题与参考答案

> 以下回答均结合 MeetMind 项目，可直接用于联通/运营商 AI 智能体岗位。

---

### Q1: 什么是 RAG？为什么需要它？

**答：** RAG（Retrieval-Augmented Generation）是在 LLM 生成前，先从外部知识库检索相关片段，拼进 prompt 再回答。

MeetMind 里如果把全部会议摘要塞进 prompt，会上下文溢出且容易幻觉。RAG 做法是：用户问「LiDAR 标定定多少」→ 向量库检索 Top-K 相关 transcript 片段 → 只把这几段给 Gemini → 回答并标注引用来源。

价值：**降低幻觉、支持私有数据、可溯源、可增量更新**（新会议结束只 index 新 chunk，不用重训模型）。

---

### Q2: RAG 的核心流程是什么？

**答：** 两阶段：

**Indexing（离线索引）**  
文档 → 清洗 → Chunk → Embedding → 存向量库 + metadata

**Retrieval（在线查询）**  
Query →（可选改写）→ 检索 Top-K →（可选 Rerank）→ 拼 Context → LLM 生成

MeetMind 索引触发点：停录、`PDF` 上传；查询入口：`GlobalSearch`、`Project 助手`。

---

### Q3: Chunk 策略怎么设计？chunk_size 怎么选？

**答：** 要在「语义完整」和「检索精度」之间平衡。

MeetMind 策略：
- **Transcript**：按说话人段落合并，超长则 512 token + 64 overlap sliding window  
- **Structured Summary**：按 topic/decision 一切一块，保持议题完整  
- **PDF**：按段落，保留 `page_number` 便于 citation  

太小：语义破碎；太大：噪声多、检索不精准。一般 **256–512 token**，overlap **10%–20%**。

---

### Q4: 向量检索和关键词检索有什么区别？为什么用 Hybrid？

**答：**

| | 向量检索 | 关键词 (BM25) |
|--|----------|---------------|
| 原理 | embedding 余弦相似度 | 词频逆文档频率 |
| 擅长 | 语义相似、改写 query | 专有名词、型号、数字 |
| 弱点 |  rare term（如「0.42v」）| 同义表达 |

MeetMind 会议里有大量 **中英混杂 + 工程参数**，纯向量容易漏「LiDAR 0.42v」这类精确词。所以用 **RRF 融合** 两路结果，再 optional rerank。

---

### Q5: Embedding 模型怎么选？

**答：** 考虑：维度、中英文能力、延迟、成本、是否可私有化。

MeetMind 第 2 周用 **Gemini Embedding**（与现有 Gemini 栈统一）。政企场景可换 **bge-m3**（中英多语、可本地部署），面试可补充：「生产可据数据域做 embedding A/B」。

---

### Q6: 向量数据库怎么选？

**答：** 看规模、运维、是否要 SQL 事务。

- Demo / 中小规模：**Chroma**（MeetMind MVP）  
- 需要权限+SQL：**pgvector**  
- 亿级：**Milvus / Elasticsearch dense vector**

选型关键：**metadata filter 性能**（必须按 userId/projectId 过滤）和 **运维成本**。

---

### Q7: 如何解决 RAG 幻觉？

**答：** 多层防护：

1. **Prompt 约束**：「仅根据上下文回答，不知道就说不知道」  
2. **Citation 强制**：句末 `[1][2]`，UI 可点溯源  
3. **低相关度拒答**：Top-K score 低于阈值不生成  
4. **Rerank**：提高 context 精度  
5. **Faithfulness 评测**：LLM-as-Judge 批测  

MeetMind 助手若检索为空，返回「知识库中未找到相关会议记录」，而非编造。

---

### Q8: Citation 怎么实现？

**答：** Retrieval 返回的每个 chunk 带 `citation_label`（如 `[1]`）。Prompt 里：

```
[1] (meeting: xxx, speaker: Alice) chunk text...
```

要求模型在回答中引用相同编号。后端解析 `[1]` 映射到 `chunk_id` 和 `source_id`，前端渲染可跳转卡片。

---

### Q9: RAG 怎么做权限控制？

**答：** 向量库每条 chunk 的 metadata 存 `owner_uid`、`project_id`。检索时必须：

```python
filter = {"owner_uid": current_user.uid}
if project_id:
    filter["project_id"] = project_id
```

不能信任前端传的 projectId 而不校验 Firestore membership。运营商场景还需 **租户隔离**（tenant_id filter）。

---

### Q10: 新文档如何增量更新？如何防重复索引？

**答：**  
- **增量**：会议结束只 index 该 meeting 的 chunks  
- **幂等**：`content_hash = sha256(source_id + chunk_index + text)`，upsert 前查重  
- **删除**：会议删除时 `delete where source_id == meeting_id`  
- **更新**：同 source 先删后插，或 version 字段  

---

### Q11: RAG 常见失败 case 有哪些？

**答：**

| 现象 | 原因 | 解决 |
|------|------|------|
| 检索不到 | chunk 太大/太小、embedding 不匹配 | 调 chunk、Hybrid |
| 答非所问 | Top-K 噪声 | Rerank、提高 threshold |
| 编造事实 | Prompt 约束弱 | Citation + 拒答 |
| 延迟高 | 串行 embed+LLM | 缓存 query embedding、异步 index |
| 多跳推理失败 | 单轮检索不够 | Multi-query / Agentic RAG（Phase 3） |

---

### Q12: RAG 和 Fine-tuning 怎么选？

**答：**

| | RAG | Fine-tuning |
|--|-----|-------------|
| 知识更新 | 增删 chunk 即可 | 需重新训练 |
| 成本 | 推理+检索 | 训练贵 |
| 溯源 | 可以 | 难 |
| 适合 | 知识频繁变、需引用 | 固定风格/格式/领域语气 |

MeetMind 会议每天都在增加，选 **RAG** 正确；若将来要固定「运营商纪要格式」，可 **RAG + 轻量 SFT** 结合。

---

### Q13: 如何评估 RAG 效果？

**答：** 离线 + 在线：

**离线**：准备 QA 测试集，算 Recall@K、MRR、Citation Accuracy、Faithfulness（LLM Judge）

**在线**：点击率、用户修正率、无答案率、P95 延迟

MeetMind 计划 `evaluation/rag_eval.json` + 周报对比 Hybrid vs 纯向量。

---

### Q14: LangChain / LlamaIndex 在 RAG 里分别做什么？

**答：**

- **LangChain**：`DocumentLoader` → `TextSplitter` → `Embeddings` → `VectorStore` → `RetrievalQA` chain；MeetMind 已用 LangChain 做 Summary/Action Agent，RAG 可延续  
- **LlamaIndex**：更专注索引与检索（index struct、query engine）；适合文档型知识库  

面试说法：「MeetMind 用 LangChain 统一 Agent 与 RAG chain；若 PDF 逻辑变复杂可引入 LlamaIndex 做 ingestion。」

---

### Q15: 和 Agent 怎么结合？

**答：** RAG 可作为 Agent 的一个 **Tool**：

```python
@tool
def search_project_knowledge(query: str, project_id: str) -> str:
    """检索项目会议与文档"""
```

Agent 先决定要不要检索，再决定要不要调 `create_task` 等工具。MeetMind 第 2 周是 **固定 RAG pipeline**；第 3 周演进为 **Agent 动态选 tool**。

---

## 12. 简历 / 面试一句话

> 设计并实现 MeetMind 企业知识 RAG 链路：会议转录与 PDF 自动切块索引（Gemini Embedding + Chroma），Hybrid 检索（向量 + BM25 RRF）与 Citation 约束生成；GlobalSearch 与 Project 助手接入真实检索，Recall@5 达 X%，回答均可溯源至会议/文档原文。

（X% 用 `evaluation/rag_eval.json` 跑完后填入。）

---

## 13. 附录：依赖增量

```txt
# backend/requirements.txt 追加
chromadb>=0.5.0
langchain-chroma>=0.2.0
rank-bm25>=0.2.2
tiktoken>=0.7.0
```

```env
# backend/.env 追加
RAG_VECTOR_STORE=chroma
RAG_EMBEDDING_MODEL=gemini-embedding-001
RAG_CHUNK_SIZE=512
RAG_CHUNK_OVERLAP=64
RAG_TOP_K=8
CHROMA_PERSIST_DIR=./data/chroma
```

---

## 14. 下一步（第 3 周预览）

- Multi-query retrieval（一个 question 生成 3 个子 query）  
- Agentic RAG：检索不够时自动换 query 再搜  
- MCP Tool：`search_knowledge` 标准化暴露  
- pgvector 迁移路径（政企私有化）  

---

## 15. 升级：Marker + Milvus 多模态科研文献 RAG

> **版本**: v1.1  
> 在 v1.0 Citation / `owner_uid` / `project_id` 隔离之上，增加科研 PDF 结构化解析与多向量检索。

### 15.1 目标

| 能力 | 实现 |
|------|------|
| Marker 解析 | `rag/marker_parser.py`：优先 Marker → Markdown/图；不可用时 pypdf 结构启发式 |
| 结构感知切块 | `chunk_research_document`：section / paragraph / table / figure 分开入库 |
| Milvus 多向量 | `rag/milvus_store.py`：`text_vector`（Gemini）+ `image_vector`（**Chinese-CLIP**） |
| 多模态检索 | `hybrid_search` 合并两路结果；Citation 带 page / figure_id / image_path |
| 后端切换 | `RAG_VECTOR_STORE=chroma\|milvus` |

### 15.2 索引路径

```
PDF 上传 → parse_research_pdf (Marker|pypdf)
        → chunk_research_document
        → upsert (Chroma 或 Milvus)
```

API：`POST /api/rag/index/pdf-file` 走 `index_research_pdf`；`POST /api/rag/index/pdf` 仍支持纯文本兼容。

### 15.3 依赖

```txt
pymilvus>=2.4.0
# 可选：marker-pdf>=1.0.0
```

```env
RAG_VECTOR_STORE=milvus
MILVUS_URI=./data/milvus/meetmind.db
MILVUS_COLLECTION=meetmind_chunks
```

### 15.4 图向量：Chinese-CLIP + 语义分块

| 项 | 说明 |
|----|------|
| `image_vector` | **Chinese-CLIP**（`OFA-Sys/chinese-clip-vit-base-patch16`）：有图路径则 `get_image_features`，否则对 caption/正文做 CLIP 文本编码 |
| 查询图通道 | 用户 query 用 Chinese-CLIP **文本编码器** 检索 `image_vector` |
| `text_vector` | 仍用 Gemini Embedding；与 CLIP **维度可不同**（collection `meetmind_chunks_v2`） |
| 分块 | 默认 **LangChain `SemanticChunker`**（`RAG_CHUNK_STRATEGY=semantic`）；失败回退定长窗 |

```env
RAG_CHUNK_STRATEGY=semantic
RAG_VECTOR_STORE=milvus
MILVUS_COLLECTION=meetmind_chunks_v2
CHINESE_CLIP_MODEL=OFA-Sys/chinese-clip-vit-base-patch16
```

### 15.5 后续增强

- Marker 页码 / 版面坐标写回 citation
- 表格结构化 JSON 入库
- Chinese-CLIP 更大 backbone（ViT-L-14）按需切换

---

*文档维护者：MeetMind Team · 与 `docs/architecture.md`（待建）和 `backend/src/rag/` 代码同步更新*

