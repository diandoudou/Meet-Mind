# 会议助手功能总结

## 🎯 项目概述
一个基于 AI 的实时会议助手，支持语音识别、文本分析、任务提取和自动总结的完整系统。

---

## ✨ 核心功能实现

### 1️⃣ **实时语音识别** (SpeechRecognitionAgent)
- ✅ 基于 DashScope ASR API 的实时语音转文本
- ✅ 支持中英文混合识别
- ✅ 自定义热词表功能，增强关键词识别准确度
- ✅ PyAudio 麦克风采集，采样率 16000Hz
- ✅ 语义标点功能（可选）

### 2️⃣ **会议记录存储** (MeetingRecordAgent)
- ✅ 实时存储所有会议发言
- ✅ 自动为发言人标记标签 (A, B, C, D...)
- ✅ 支持多发言人会议记录
- ✅ 获取格式化会议记录（带发言人标签）
- ✅ 获取纯文本记录
- ✅ 会议统计信息 (发言人数、总字数等)

### 3️⃣ **会议总结生成** (TextAnalysisAgent + MeetingRecordAgent)
- ✅ **两种总结模式**：
  - 详细总结 (comprehensive)：包含讨论议题、共识、行动项、决策等
  - 简洁总结 (concise)：重点突出，200 字以内
- ✅ 使用 **Gemini API** 生成高质量总结
- ✅ 自动更新，实时反馈

### 4️⃣ **关键词提取** (TextAnalysisAgent)
- ✅ 支持两种提取方法：
  - **本地 Jieba**：TF-IDF 和 TextRank 算法，零 API 成本
  - **DashScope LLM**：智能提取，更精准
- ✅ 可配置关键词数量
- ✅ 返回关键词权重，标识重要程度

### 5️⃣ **实体提取** (EntityExtractionAgent)
- ✅ **人名提取**：自动识别会议中的参与者姓名
- ✅ **任务提取**：从对话中提取待办任务
- ✅ **时间提取**：识别截止时间、任务期限等
- ✅ **智能匹配**：将任务分配给相应负责人
- ✅ **两层策略**：
  - 第一层：规则匹配（0 API 成本，速度快）
  - 第二层：DashScope LLM 兜底（更精准）

### 6️⃣ **任务管理** (TaskManagerAgent + TaskExtractionCoordinator)
- ✅ **自动任务提取**：从会议文本中提取任务
- ✅ **任务存储**：SQLite 本地数据库
- ✅ **任务查询**：
  - 按负责人查询
  - 按状态查询 (pending/in_progress/completed/cancelled)
  - 按截止时间查询
- ✅ **任务管理**：
  - 添加、修改、删除任务
  - 更新任务状态
  - 生成逾期任务提醒
  - 批量导入导出
- ✅ **任务统计**：
  - 按负责人统计
  - 总任务数、未完成数等
  - 逾期任务统计

### 7️⃣ **指令执行** (CommandExecutionAgent)
- ✅ 支持语音/文字唤醒词激活 (默认"小费同学")
- ✅ 支持自定义指令处理
- ✅ 支持同步/异步执行
- ✅ 从会议文本中上下文理解指令
- ✅ 指令结果实时反馈

### 8️⃣ **用户界面** (GUI)
- ✅ **多区域布局**：
  - 当前语音显示区（实时识别文本）
  - 会议发言记录区（完整对话历史）
  - 指令执行结果区（命令反馈）

- ✅ **快捷功能**：
  - 📝 **生成会议总结**：一键生成会议概要
  - ✅ **生成任务分配**：自动提取人名和任务
  
- ✅ **指令输入**：
  - 手动输入指令
  - 支持回车键执行
  - 支持异步处理，不阻塞 UI

- ✅ **实时状态显示**：
  - 录音状态指示
  - 系统时间显示
  - 处理状态反馈

- ✅ **美化 UI**：
  - 中文字体支持
  - 彩色主题
  - 区域颜色区分
  - 可滚动文本区域

---

## 🏗️ 架构设计

### Agent 协作关系

```
┌─────────────────────────────────────────────────────────────┐
│                    GUI 用户界面                               │
└──────────────────────┬──────────────────────────────────────┘
                       │
        ┌──────────────▼──────────────┐
        │      CoreAgent (协调器)      │
        └──┬───────────┬───────────┬──┘
           │           │           │
    ┌──────▼─┐  ┌──────▼──┐  ┌────▼─────┐
    │语音识别│  │文本分析 │  │会议记录  │
    │Agent   │  │Agent    │  │Agent     │
    └────────┘  └─────────┘  └──────────┘
           │           │           │
    ┌──────▼───────────▼───────────▼──────┐
    │  指令执行 Agent (DashScope LLM)       │
    │  实体提取 Agent (规则+DashScope LLM) │
    │  任务协调器 (规则+SQLite)             │
    └────────────────────────────────────┘
```

### API 分配规划

| 功能 | API | 模型 | 成本 |
|------|-----|------|------|
| 语音识别 | DashScope ASR | - | 💰💰 |
| 指令执行 | DashScope LLM | deepseek-r1 | 💰 |
| 关键词提取 | DashScope LLM | deepseek-r1 | 💰 |
| **会议总结** | **Gemini API** | **gemini-2.5-flash** | **💰** |
| 实体提取(兜底) | DashScope LLM | deepseek-r1 | 💰 |
| 任务管理 | SQLite (本地) | - | 🆓 |

---

## 📊 工作流程

### 典型使用流程

1. **启动阶段**
   - 用户点击"开始记录"
   - CoreAgent 初始化各子 Agent
   - 启动实时语音识别

2. **录音阶段**
   - 麦克风采集音频
   - DashScope ASR 实时转文本
   - 文本保存到缓冲区和会议记录

3. **分析阶段**（每 5 秒自动触发）
   - 提取关键词
   - 生成简洁总结
   - 更新 UI 显示

4. **指令执行**
   - 用户说出唤醒词（如"小费同学"）
   - Agent 进入唤醒状态
   - 后续语音作为指令被收集
   - CommandExecutionAgent 处理指令
   - 结果反馈到 UI

5. **任务提取**
   - 用户点击"生成任务分配"
   - EntityExtractionAgent 提取人名和任务
   - TaskManagerAgent 存储到数据库
   - UI 显示提取结果

6. **会议总结**
   - 用户点击"生成会议总结"
   - MeetingRecordAgent 调用 Gemini API
   - 生成高质量总结
   - 显示到结果区域

---

## 🔧 可配置参数

### 环境变量

**必需：**
```
DASHSCOPE_API_KEY              # 阿里云 API 密钥
DASHSCOPE_ASR_MODEL_NAME       # 语音识别模型
GEMINI_API_KEY                 # Google Gemini API 密钥
```

**可选：**
```
DASHSCOPE_LLM_MODEL_NAME       # 默认: deepseek-r1
DASHSCOPE_LLM_BASE_URL         # 默认: https://dashscope.aliyuncs.com/compatible-mode/v1
GEMINI_MODEL_NAME              # 默认: gemini-2.5-flash
WAKE_UP_KEYWORD                # 默认: 小费同学
```

### 代码配置

```python
config = {
    'speech_model': 'qwen-url',           # 语音模型
    'sample_rate': 16000,                  # 采样率
    'channels': 1,                         # 声道数
    'block_size': 3200,                    # 缓冲区大小
    'semantic_punctuation_enabled': False, # 语义标点
    'keyword_extraction_method': 'jieba',  # jieba 或 llm
    'max_keywords': 10,                    # 关键词数量
    'analysis_interval_seconds': 5,        # 分析间隔
    'max_text_buffer_length': 10000        # 最大缓冲区
}
```

---

## 📁 项目结构

```
src/
├── agents/
│   ├── core_agent.py                     # 核心协调 Agent
│   ├── speech_recognition_agent.py       # 语音识别
│   ├── text_analysis_agent.py            # 文本分析
│   ├── meeting_record_agent.py           # 会议记录
│   ├── entity_extraction_agent.py        # 实体提取
│   ├── command_execution_agent.py        # 指令执行
│   ├── task_manager_agent.py             # 任务管理
│   ├── task_extraction_coordinator.py    # 任务协调
│   └── __init__.py
├── GUI/
│   ├── meeting_assistant_gui.py          # 主 GUI 界面
│   └── __init__.py
├── main.py                               # 程序入口
└── __init__.py

data/
└── tasks.db                              # 任务数据库
```

---

## 🚀 特色亮点

### 1. **智能双层实体提取**
- 规则匹配优先：快速且零成本
- LLM 兜底补充：精准和上下文理解
- 自动判断提取质量，择优选择

### 2. **灵活的总结方案**
- 详细模式：全面分析会议
- 简洁模式：重点突出
- 使用 Gemini 生成高质量内容

### 3. **异步处理架构**
- 长耗时操作不阻塞 UI
- 多线程协调
- 队列式结果管理

### 4. **完整的任务管理**
- 自动从语音提取任务
- 智能分配负责人
- 识别截止时间
- 数据库永久存储

### 5. **开放的指令系统**
- 支持自定义唤醒词
- 支持多种指令类型
- 上下文理解
- 异步执行反馈

---

## 📈 性能指标

- **语音识别延迟**：< 1 秒
- **文本分析周期**：5 秒
- **指令处理时间**：2-5 秒（依 LLM 响应）
- **UI 更新频率**：实时 (100ms)
- **并发处理**：支持多线程异步操作

---

## ⚙️ 技术栈

- **后端**：Python 3.8+
- **GUI**：Tkinter
- **语音**：DashScope ASR API
- **LLM**：Google Gemini API + DashScope LLM
- **NLP**：Jieba
- **数据库**：SQLite
- **框架**：LangChain
- **音频**：PyAudio

---

## 🔮 未来扩展方向

- [ ] Web 界面支持
- [ ] 会议录音存储
- [ ] 实时翻译功能
- [ ] 情感分析
- [ ] 参与者互动分析
- [ ] 移动应用
- [ ] 云端同步存储

