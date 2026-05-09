# MeetingAssistant · 会议助手

<div align="center">

**An AI-powered real-time meeting assistant with speech recognition, text analysis, task extraction, and automatic summarization.**

**基于 AI 的实时会议助手，支持语音识别、文本分析、任务提取与自动总结。**

![Python](https://img.shields.io/badge/Python-3.8+-blue?logo=python)
![LangChain](https://img.shields.io/badge/LangChain-Framework-green)
![Gemini](https://img.shields.io/badge/Gemini-API-orange?logo=google)
![DashScope](https://img.shields.io/badge/DashScope-ASR%20%2F%20LLM-purple)
![SQLite](https://img.shields.io/badge/SQLite-Local%20DB-lightgrey?logo=sqlite)

</div>

---

## English

### Overview

MeetingAssistant is an AI-powered real-time meeting assistant built for **academic conferences, lab group meetings, and team knowledge management**. It tackles three pain points that are common in research and cross-disciplinary settings:

| Pain Point | How MeetingAssistant Solves It |
|------------|--------------------------------|
| 🌐 **Multilingual barrier** | Chinese/English mixed ASR with PDF hotword injection ensures domain terms and names are accurately captured, so no attendee gets left behind |
| 📋 **Untracked action items** | Automatic entity extraction turns spoken commitments into structured tasks in SQLite with assignees and deadlines — nothing slips through |
| 🔁 **No systematic follow-up** | Wake-word command execution and periodic incremental summaries enable real-time progress checks and accountability throughout the meeting |

In short: it listens, transcribes, extracts key information, generates summaries, and manages tasks — all in one place, with zero manual effort.

### Features

| # | Feature | Description |
|---|---------|-------------|
| 1 | **Real-time Speech Recognition** | Powered by DashScope ASR; supports Chinese/English mixed input, custom hotwords, 16 kHz microphone capture |
| 2 | **Meeting Record Storage** | Stores every utterance, auto-labels speakers (A, B, C…), multi-speaker support |
| 3 | **Meeting Summary Generation** | Two modes — *comprehensive* (topics, decisions, action items) and *concise* (≤ 200 words); powered by Gemini API |
| 4 | **Keyword Extraction** | Local Jieba (TF-IDF / TextRank, zero cost) **or** DashScope LLM (smarter); configurable count + weights |
| 5 | **Entity Extraction** | Identifies names, tasks, and deadlines from dialogue; rule-based first, LLM fallback |
| 6 | **Task Management** | Auto-extracts tasks, stores in SQLite, supports query/update/delete by assignee, status, and due date |
| 7 | **Command Execution** | Wake-word activation (default: `小费同学`), custom commands, async execution with real-time feedback |
| 8 | **GUI** | Multi-panel Tkinter interface: live transcription, full chat history, command results, one-click summary & task extraction |

### Architecture & Agent Collaboration Workflow

#### Overall Data Flow

```
Microphone Audio Stream
        │
        ▼
┌──────────────────────────┐
│  SpeechRecognitionAgent  │  ← DashScope ASR (16kHz)
│  + PDF Hotword Injection │  ← pdf_term_extractor.py
└────────────┬─────────────┘
             │ Transcribed text (per sentence)
             ▼
┌────────────────────────────┐
│        CoreAgent           │  ← Central dispatcher, event-driven
└──┬──────────┬──────────┬───┘
   │          │          │
   ▼          ▼          ▼
[Record]  [Analyze]  [Command Detection]
```

#### Phase 1 — Speech Input

```
SpeechRecognitionAgent
  ├── Capture microphone audio (PyAudio, 16kHz)
  ├── Inject PDF hotwords (improves domain-term accuracy)
  ├── Call DashScope ASR
  └── → Push transcribed text to CoreAgent
```

#### Phase 2 — CoreAgent Dispatch (Parallel)

```
CoreAgent receives new sentence
  ├──→ MeetingRecordAgent       # Immediately store, label speaker A/B/C
  ├──→ CommandExecutionAgent    # Detect wake-word 「小费同学」
  └──→ Counter +1; every 5 sentences trigger TextAnalysisAgent
```

#### Phase 3 — Text Analysis (every 5 sentences)

```
TextAnalysisAgent
  ├── Keyword extraction
  │     ├── Primary:  local Jieba TF-IDF / TextRank (zero cost)
  │     └── Fallback: DashScope LLM deepseek-r1
  ├── Incremental summary → Gemini gemini-2.5-flash
  └──→ Push results via WebSocket → Frontend display
```

#### Phase 4 — Entity Extraction & Task Management (async)

```
EntityExtractionAgent
  ├── Rule-based matching (regex): names, times, task keywords
  ├── Quality check: if rules insufficient → DashScope LLM fallback
  └──→ TaskManagerAgent
            ├── Parse (assignee, task, deadline)
            ├── Write to SQLite tasks.db
            └── Support full CRUD queries
```

#### Phase 5 — Command Execution (wake-word triggered)

```
CommandExecutionAgent
  ├── Detect 「小费同学 + command」
  ├── Async call DashScope LLM deepseek-r1 for intent parsing
  ├── Execute action (query tasks / generate summary / …)
  └──→ Real-time feedback to GUI / WebSocket
```

#### Frontend–Backend Communication

```
Python Backend                     React + Vite (Node.js) Frontend
─────────────────                  ────────────────────────────────
CoreAgent
  └── websocket_server.py  ←────→  WebSocket Client
        (FastAPI + uvicorn)          ├── Live transcription panel
                                     ├── Keyword display
                                     ├── Summary panel
                                     └── Task list
```

#### Concurrency Model

| Agent | Mode | Trigger |
|-------|------|---------|
| SpeechRecognitionAgent | Dedicated thread, continuous | App start |
| MeetingRecordAgent | Synchronous call | Every sentence |
| CommandExecutionAgent | Async thread | Wake-word detected |
| TextAnalysisAgent | Async thread | Every 5 sentences |
| EntityExtractionAgent | Async thread | Every 5 sentences |
| TaskManagerAgent | Synchronous call | After entity extraction |
| WebSocket push | Event-driven | Any Agent produces output |

> **Core design principle:** The speech recognition thread is never blocked; all time-consuming LLM calls are fully async, guaranteeing a 100 ms UI refresh rate.

### Orchestration Pattern

The project adopts a **Hub-and-Spoke (Orchestrator-Worker)** pattern as its primary agent orchestration strategy, with a local **Pipeline** for downstream task handling.

```
          ┌─────────────┐
          │  CoreAgent  │  ← Single dispatcher (Hub)
          └──────┬─────┘
    ┌──────┬───┬──────┬─────────┐
    ▼      ▼      ▼       ▼         ▼
 Speech  Rec.  Text   Command  Entity
 Recog.        Anal.  Exec.    Extract
                                  │  (Pipeline)
                              ┌───▼───────┐
                              │TaskManager│
                              └───────────┘
```

| Pattern | Scope | Description |
|---------|-------|-------------|
| **Hub-and-Spoke** | Global | `CoreAgent` is the sole dispatcher; all Workers report only to the Hub with no lateral communication |
| **Pipeline** | Local | `EntityExtractionAgent` → `TaskManagerAgent` forms a sequential chain; the former's output is the latter's input |

**Why this pattern?**
- **Low latency:** Hub dispatches Agents in parallel immediately — no chain waiting
- **Clear responsibility:** Each Worker does exactly one job; CoreAgent owns all timing and concurrency logic
- **Easy to extend:** Registering a new Agent requires only a hook in CoreAgent, with zero impact on existing Workers

### API Overview

| Function | API | Model | Cost |
|----------|-----|-------|------|
| Speech Recognition | DashScope ASR | — | 💰💰 |
| Command Execution | DashScope LLM | deepseek-r1 | 💰 |
| Keyword Extraction | DashScope LLM | deepseek-r1 | 💰 |
| **Meeting Summary** | **Gemini API** | **gemini-2.5-flash** | **💰** |
| Entity Extraction (fallback) | DashScope LLM | deepseek-r1 | 💰 |
| Task Management | SQLite (local) | — | 🆓 |

### Quick Start

#### Prerequisites

- Python 3.8+
- `portaudio` (for PyAudio microphone access)

```bash
# macOS
brew install portaudio
```

#### Installation

```bash
git clone <repo-url>
cd MeetingAssistant
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

#### Environment Variables

Create a `.env` file in the project root:

```env
# Required
DASHSCOPE_API_KEY=your_dashscope_key
DASHSCOPE_ASR_MODEL_NAME=your_asr_model_name
GEMINI_API_KEY=your_gemini_key

# Optional (defaults shown)
DASHSCOPE_LLM_MODEL_NAME=deepseek-r1
DASHSCOPE_LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
GEMINI_MODEL_NAME=gemini-2.5-flash
WAKE_UP_KEYWORD=小费同学
```

#### Run

```bash
python src/main.py
```

### Project Structure

```
MeetingAssistant/
├── src/
│   ├── agents/
│   │   ├── core_agent.py                  # Coordinator
│   │   ├── speech_recognition_agent.py    # ASR
│   │   ├── text_analysis_agent.py         # Summary & keywords
│   │   ├── meeting_record_agent.py        # Record storage
│   │   ├── entity_extraction_agent.py     # Name / task / time
│   │   ├── command_execution_agent.py     # Wake-word commands
│   │   └── task_manager_agent.py          # Task CRUD
│   ├── rag/
│   │   └── pdf_term_extractor.py          # PDF hotword extraction
│   ├── websocket_server.py                # WebSocket bridge
│   └── main.py                            # Entry point
├── data/
│   ├── tasks.db                           # SQLite task database
│   └── uploaded_pdfs/                     # PDF hotword source files
└── FEATURES_SUMMARY.md
```

### Performance

| Metric | Value |
|--------|-------|
| Speech recognition latency | < 1 s |
| Text analysis cycle | 5 s |
| Command processing | 2 – 5 s (LLM dependent) |
| UI update frequency | Real-time (100 ms) |

### Tech Stack

#### Backend

| Layer | Technology | Role |
|-------|-----------|------|
| Language | Python 3.8+ | Core runtime |
| Web Framework | FastAPI + uvicorn | WebSocket server & REST API |
| Data Validation | Pydantic | Config & message schema |
| Speech Recognition | DashScope ASR (16kHz) | Real-time audio transcription |
| LLM — Summary | Google Gemini `gemini-2.5-flash` | Meeting summary generation |
| LLM — Reasoning | DashScope `deepseek-r1` | Keywords / entity / command intent |
| Keyword Extraction | Jieba (TF-IDF / TextRank) | Local, zero-cost keyword extraction |
| Database | SQLite | Task persistence (CRUD) |
| AI Orchestration | LangChain | Prompt management & LLM chain |
| Audio Capture | PyAudio | Microphone stream (16kHz, mono) |

#### Frontend

| Layer | Technology | Role |
|-------|-----------|------|
| UI Framework | React 19 | Component-based UI |
| Build Tool | Vite 6 | Dev server & production bundler |
| Language | TypeScript | Type-safe frontend code |
| Styling | Tailwind CSS v4 | Utility-first CSS |
| Routing | React Router v7 | SPA multi-page navigation |
| Backend-as-a-Service | Firebase (Firestore + Auth) | Cloud data storage & authentication |
| AI Client | `@google/genai` | Gemini API calls from frontend |
| Animation | Motion (Framer Motion) | UI transition effects |
| Icons | Lucide React | Icon library |
| Real-time Comms | WebSocket | Live data push from Python backend |

---

## 中文

### 项目概述

MeetingAssistant 是面向**学术会议、课题组组会与团队知识沉淀**场景设计的 AI 实时会议助手。它针对以下三大痛点而生：

| 痛点 | MeetingAssistant 的解决方式 |
|------|-----------------------------|
| 🌐 **多语言跟不上** | 中英文混合 ASR + PDF 专业热词注入，确保术语、人名精准识别，每位参会者都不掉队 |
| 📋 **任务无人跟踪** | 自动实体提取将口头承诺转为结构化任务，写入 SQLite，绑定负责人与截止时间，承诺落地有据可查 |
| 🔁 **缺乏系统性督促** | 唤醒词指令执行 + 每 5 句增量总结，会议进行中即可实时检查进展，会后催促追踪有迹可循 |

一句话：**听、写、提、总、管** 全流程自动化，零手动干预，让会议效率从记录环节开始质变。

### 功能特性

| # | 功能 | 说明 |
|---|------|------|
| 1 | **实时语音识别** | 基于 DashScope ASR，支持中英文混合、自定义热词、16 kHz 麦克风采集 |
| 2 | **会议记录存储** | 实时保存所有发言，自动标注发言人（A、B、C…），支持多人会议 |
| 3 | **会议总结生成** | 两种模式——*详细*（议题、决策、行动项）与*简洁*（200 字以内），由 Gemini API 驱动 |
| 4 | **关键词提取** | 本地 Jieba（TF-IDF / TextRank，零成本）**或** DashScope LLM（更智能），可配置数量与权重 |
| 5 | **实体提取** | 从对话中识别人名、任务、时间；规则匹配优先，LLM 兜底 |
| 6 | **任务管理** | 自动提取任务并存入 SQLite，支持按负责人、状态、截止时间查询/更新/删除 |
| 7 | **指令执行** | 唤醒词激活（默认：`小费同学`），自定义指令，异步执行并实时反馈 |
| 8 | **图形界面** | 多面板 Tkinter 界面：实时转写、完整对话记录、指令结果、一键生成总结与任务分配 |

### 架构设计与 Agent 协作工作流

#### 整体数据流

```
麦克风音频流
     │
     ▼
┌─────────────────────────┐
│ SpeechRecognitionAgent  │  ← DashScope ASR (16kHz)
│  + PDF 热词注入          │  ← pdf_term_extractor.py
└──────────┬──────────────┘
           │ 转写文本（每句）
           ▼
┌──────────────────────────┐
│       CoreAgent          │  ← 总调度，事件驱动
└──┬──────────┬─────────┬──┘
   │          │         │
   ▼          ▼         ▼
[记录]     [分析]    [指令检测]
```

#### 阶段一：语音输入

```
SpeechRecognitionAgent
  ├── 采集麦克风音频（PyAudio，16kHz）
  ├── 注入 PDF 热词（提升专业术语识别率）
  ├── 调用 DashScope ASR
  └── → 推送转写文本至 CoreAgent
```

#### 阶段二：CoreAgent 分发（并行）

```
CoreAgent 收到新句子
  ├──→ MeetingRecordAgent       # 立即存储，标注说话人 A/B/C
  ├──→ CommandExecutionAgent    # 检测唤醒词「小费同学」
  └──→ 计数器 +1，每 5 句触发 TextAnalysisAgent
```

#### 阶段三：文本分析（每 5 句触发）

```
TextAnalysisAgent
  ├── 关键词提取
  │     ├── 优先：本地 Jieba TF-IDF / TextRank（零成本）
  │     └── 备选：DashScope LLM deepseek-r1
  ├── 阶段性摘要生成 → Gemini gemini-2.5-flash
  └──→ 结果推送 WebSocket → 前端展示
```

#### 阶段四：实体提取与任务管理（异步）

```
EntityExtractionAgent
  ├── 规则匹配（正则）：人名、时间、任务关键词
  ├── 质量评估：规则结果不足 → 调用 DashScope LLM 兜底
  └──→ TaskManagerAgent
            ├── 解析（人名、任务、截止时间）
            ├── 写入 SQLite tasks.db
            └── 支持完整 CRUD 查询
```

#### 阶段五：指令执行（唤醒词触发）

```
CommandExecutionAgent
  ├── 检测到「小费同学 + 指令」
  ├── 异步调用 DashScope LLM deepseek-r1 解析意图
  ├── 执行对应动作（查任务 / 生成总结 / …）
  └──→ 结果实时反馈至 GUI / WebSocket
```

#### 前后端通信

```
Python 后端                        React + Vite (Node.js) 前端
─────────────────                  ─────────────────────────
CoreAgent
  └── websocket_server.py  ←────→  WebSocket Client
        (FastAPI + uvicorn)          ├── 实时转写面板
                                     ├── 关键词展示
                                     ├── 总结面板
                                     └── 任务列表
```

#### 并发模型

| Agent | 运行方式 | 触发条件 |
|-------|---------|----------|
| SpeechRecognitionAgent | 独立线程，持续运行 | 程序启动 |
| MeetingRecordAgent | 同步调用 | 每句话 |
| CommandExecutionAgent | 异步线程 | 唤醒词检测到 |
| TextAnalysisAgent | 异步线程 | 每 5 句 |
| EntityExtractionAgent | 异步线程 | 每 5 句 |
| TaskManagerAgent | 同步调用 | 实体提取完成后 |
| WebSocket 推送 | 事件驱动 | 任意 Agent 产出结果 |

> **核心设计原则**：语音识别线程永不阻塞，耗时的 LLM 调用全部异步化，保证 UI 100ms 刷新频率。

### 编排模式

本项目采用 **Hub-and-Spoke（中心调度 / Orchestrator-Worker）** 作为主体 Agent 编排策略，下游任务处理层局部采用 **Pipeline 顺序串行**。

```
          ┌─────────────┐
          │  CoreAgent  │  ← 唯一调度中心（Hub）
          └──────┬─────┘
    ┌──────┬───┬──────┬─────────┐
    ▼      ▼      ▼       ▼         ▼
 语音   记录  文本   指令     实体
 识别         分析   执行     提取
                                  │  （Pipeline）
                              ┌───▼──────┐
                              │ 任务管理 │
                              └──────────┘
```

| 模式 | 作用范围 | 说明 |
|------|---------|------|
| **Hub-and-Spoke** | 全局 | `CoreAgent` 是唯一分发器，所有 Worker 仅向 Hub 汇报，各 Worker 之间无横向通信 |
| **Pipeline** | 局部 | `EntityExtractionAgent` → `TaskManagerAgent` 形成顺序串行，前者输出即后者输入 |

**为什么选择这个模式？**
- **低延迟**：Hub 立即并行派发，无需等待上游链式传递
- **职责清晰**：每个 Worker 只做一件事， CoreAgent 控制全部时序与并发策略
- **易于扩展**：新增 Agent 只需在 CoreAgent 注册一个钉子，不影响其他 Worker

### API 分配

| 功能 | API | 模型 | 成本 |
|------|-----|------|------|
| 语音识别 | DashScope ASR | — | 💰💰 |
| 指令执行 | DashScope LLM | deepseek-r1 | 💰 |
| 关键词提取 | DashScope LLM | deepseek-r1 | 💰 |
| **会议总结** | **Gemini API** | **gemini-2.5-flash** | **💰** |
| 实体提取（兜底） | DashScope LLM | deepseek-r1 | 💰 |
| 任务管理 | SQLite（本地） | — | 🆓 |

### 快速开始

#### 环境要求

- Python 3.8+
- `portaudio`（PyAudio 麦克风支持）

```bash
# macOS
brew install portaudio
```

#### 安装

```bash
git clone <repo-url>
cd MeetingAssistant
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

#### 环境变量

在项目根目录创建 `.env` 文件：

```env
# 必填
DASHSCOPE_API_KEY=你的_dashscope_密钥
DASHSCOPE_ASR_MODEL_NAME=语音识别模型名称
GEMINI_API_KEY=你的_gemini_密钥

# 可选（括号内为默认值）
DASHSCOPE_LLM_MODEL_NAME=deepseek-r1
DASHSCOPE_LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
GEMINI_MODEL_NAME=gemini-2.5-flash
WAKE_UP_KEYWORD=小费同学
```

#### 运行

```bash
python src/main.py
```

### 项目结构

```
MeetingAssistant/
├── src/
│   ├── agents/
│   │   ├── core_agent.py                  # 核心协调 Agent
│   │   ├── speech_recognition_agent.py    # 语音识别
│   │   ├── text_analysis_agent.py         # 总结与关键词
│   │   ├── meeting_record_agent.py        # 会议记录存储
│   │   ├── entity_extraction_agent.py     # 人名/任务/时间提取
│   │   ├── command_execution_agent.py     # 唤醒词指令
│   │   └── task_manager_agent.py          # 任务增删改查
│   ├── rag/
│   │   └── pdf_term_extractor.py          # PDF 热词提取
│   ├── websocket_server.py                # WebSocket 桥接
│   └── main.py                            # 程序入口
├── data/
│   ├── tasks.db                           # SQLite 任务数据库
│   └── uploaded_pdfs/                     # PDF 热词来源文件
└── FEATURES_SUMMARY.md
```

### 性能指标

| 指标 | 数值 |
|------|------|
| 语音识别延迟 | < 1 秒 |
| 文本分析周期 | 5 秒 |
| 指令处理时间 | 2 – 5 秒（依 LLM 响应） |
| UI 更新频率 | 实时（100 ms） |

### 技术栈

#### 后端

| 层次 | 技术 | 责任 |
|------|------|------|
| 语言 | Python 3.8+ | 核心运行时 |
| Web 框架 | FastAPI + uvicorn | WebSocket 服务器 & REST API |
| 数据校验 | Pydantic | 配置与消息结构化 |
| 语音识别 | DashScope ASR（16kHz） | 实时音频转写 |
| LLM — 总结 | Google Gemini `gemini-2.5-flash` | 会议总结生成 |
| LLM — 推理 | DashScope `deepseek-r1` | 关键词 / 实体 / 指令意图解析 |
| 关键词提取 | Jieba（TF-IDF / TextRank） | 本地零成本提取 |
| 数据库 | SQLite | 任务持久化（CRUD） |
| AI 编排 | LangChain | Prompt 管理与 LLM 链式调用 |
| 音频采集 | PyAudio | 麦克风流（16kHz，单声道） |

#### 前端

| 层次 | 技术 | 责任 |
|------|------|------|
| UI 框架 | React 19 | 组件化界面 |
| 构建工具 | Vite 6 | 开发服务器 & 生产打包 |
| 语言 | TypeScript | 类型安全的前端代码 |
| 样式 | Tailwind CSS v4 | 工具类 CSS |
| 路由 | React Router v7 | SPA 多页导航 |
| 后端服务 | Firebase（Firestore + Auth） | 云端数据存储与身份认证 |
| AI 客户端 | `@google/genai` | 前端直调 Gemini API |
| 动画 | Motion（Framer Motion） | UI 过渡动画 |
| 图标 | Lucide React | 图标库 |
| 实时通信 | WebSocket | Python 后端实时推送 |

---

## Author / 作者

**张典 (ZHANG Dian)**

---
