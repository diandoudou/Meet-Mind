"""
MeetingAssistant WebSocket Server
为 MeetMind Web 提供实时语音转录接口

Endpoints:
  WS   ws://localhost:8765/ws       - 实时接收转录消息
  POST http://localhost:8765/start  - 开始录音
  POST http://localhost:8765/stop   - 停止录音，返回总结和转录记录
  GET  http://localhost:8765/status - 获取当前状态
"""

import os
import sys
import asyncio
import json
import shutil
import tempfile
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional, Set, List
from contextlib import asynccontextmanager

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from dotenv import load_dotenv
_backend_env = os.path.join(os.path.dirname(__file__), '..', '.env')
_root_env = os.path.join(os.path.dirname(__file__), '..', '..', '.env')
load_dotenv(_backend_env)
load_dotenv(_root_env)

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn

# ──────────────────────────── Pydantic Models ────────────────────────────

class StatusResponse(BaseModel):
    running: bool
    clients: int

class StartResponse(BaseModel):
    status: str

class TranscriptEntry(BaseModel):
    speaker: str
    text: str
    timestamp: str
    language: str

class StopResponse(BaseModel):
    status: str
    summary: str
    transcript: list[TranscriptEntry]

class TermItem(BaseModel):
    word: str
    type: str

class UploadPdfResponse(BaseModel):
    status: str
    filename: str
    terms: list[TermItem]
    injected_to_asr: bool
    message: str

class PdfRecord(BaseModel):
    filename: str
    terms: list[TermItem]
    keyword_count: int
    injected_to_asr: bool

class UploadedPdfsResponse(BaseModel):
    pdfs: list[PdfRecord]

class ClearPdfsResponse(BaseModel):
    status: str

from agents.core_agent import CoreAgent
from agents.entity_extraction_agent import EntityExtractionAgent
from rag.pdf_term_extractor import extract_terms_from_pdf, terms_to_keywords

# ──────────────────────────── Global State ────────────────────────────

connected_clients: Set[WebSocket] = set()
core_agent: Optional[CoreAgent] = None
main_loop = None
_entity_extractor = EntityExtractionAgent(use_llm_fallback=False)

# 已上传 PDF 的记录: [{filename, terms: [(word, type)]}]
_uploaded_pdfs: List[dict] = []

# PDF 临时存储目录
_PDF_UPLOAD_DIR = Path(__file__).parent.parent / "data" / "uploaded_pdfs"
_PDF_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# ──────────────────────────── Broadcast ────────────────────────────

def broadcast_sync(message: dict):
    """从同步线程向所有 WebSocket 客户端广播消息"""
    if main_loop and connected_clients:
        asyncio.run_coroutine_threadsafe(_broadcast(message), main_loop)

async def _broadcast(message: dict):
    disconnected = set()
    for ws in list(connected_clients):
        try:
            await ws.send_text(json.dumps(message, ensure_ascii=False))
        except Exception:
            disconnected.add(ws)
    connected_clients.difference_update(disconnected)

# ──────────────────────────── App Lifecycle ────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    global main_loop
    main_loop = asyncio.get_event_loop()
    print("✅ MeetingAssistant WebSocket Server 已启动")
    print("   WS:   ws://localhost:8765/ws")
    print("   HTTP: http://localhost:8765")
    yield
    if core_agent and core_agent.is_running:
        core_agent.stop()

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ──────────────────────────── WebSocket Endpoint ────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connected_clients.add(websocket)
    print(f"[WS] 客户端已连接，当前连接数: {len(connected_clients)}")
    try:
        # 发送欢迎消息
        await websocket.send_text(json.dumps({
            "type": "connected",
            "message": "MeetingAssistant 已连接，等待开始录音..."
        }))
        # 保持连接
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        connected_clients.discard(websocket)
        print(f"[WS] 客户端断开，当前连接数: {len(connected_clients)}")

# ──────────────────────────── HTTP Endpoints ────────────────────────────

@app.get("/status", response_model=StatusResponse)
async def get_status():
    return {
        "running": core_agent.is_running if core_agent else False,
        "clients": len(connected_clients)
    }

@app.post("/start", response_model=StartResponse)
async def start_recording():
    global core_agent

    if core_agent and core_agent.is_running:
        return {"status": "already_running"}

    required_env = ["DASHSCOPE_API_KEY"]
    missing = [key for key in required_env if not os.getenv(key)]
    if missing:
        msg = f"缺少后端环境变量: {', '.join(missing)}。请在 backend/.env 中配置后重试。"
        broadcast_sync({"type": "error", "message": msg})
        raise HTTPException(status_code=400, detail=msg)

    try:
        core_agent = CoreAgent()
    except Exception as e:
        msg = f"初始化录音代理失败: {str(e)}"
        broadcast_sync({"type": "error", "message": msg})
        raise HTTPException(status_code=500, detail=msg)

    agent = core_agent  # local non-None reference for closures

    # ── 回调：检测到新说话人时通知前端（用于姓名确认）──
    def on_speaker_detected(speaker_id: str, detected_name: Optional[str]):
        msg = {
            "type": "speaker_detected",
            "speaker_id": speaker_id,
            "detected_name": detected_name,  # 可能是 None 或从"我是XXX"提取的名字
            "timestamp": datetime.now().isoformat()
        }
        broadcast_sync(msg)
        print(f"[新说话人] {speaker_id} - 检测到名字: {detected_name}")

    # ── 回调：每句话说完时广播到前端 ──
    def on_speech_complete(text: str):
        print(f"[DEBUG on_speech_complete] 收到文本: {text[:100]}...")
        
        # 从 meeting_record_agent 获取最新发言人标签和真实姓名
        records = agent.meeting_record_agent.records
        print(f"[DEBUG] records 总数: {len(records)}")
        
        if not records:
            speaker_label = "A"
            speaker_name = "Speaker A"
        else:
            # 获取最后一条记录（刚刚添加的）
            last_record = records[-1]
            speaker_label = last_record["speaker_label"]
            speaker_name = agent.meeting_record_agent.get_speaker_display_name(speaker_label)
            print(f"[DEBUG] 最后一条记录: {speaker_label} - {last_record['text'][:60]}...")

        # 广播转录条目（使用真实姓名）
        msg = {
            "type": "transcript",
            "speaker": speaker_name,
            "text": text,  # 直接使用传入的 text，不要从 records 重复读取
            "timestamp": datetime.now().isoformat(),
            "language": "mixed"
        }
        print(f"[DEBUG] 即将广播: {speaker_name}: {text[:60]}...")
        broadcast_sync(msg)
        print(f"[转录] {speaker_name}: {text[:60]}...")

        # 2. 实体提取（每句话完成后）
        try:
            # 用全部历史文本做提取，结果更准
            full_text = agent.meeting_record_agent.get_plain_transcript()
            result = _entity_extractor.extract_all(full_text)
            broadcast_sync({
                "type": "entity_update",
                "persons": result.get("persons", []),
                "tasks": result.get("tasks", []),
                "timestamp": datetime.now().isoformat()
            })
        except Exception as e:
            print(f"[实体提取错误] {e}")

        # 3. 每累计 5 句话生成一次阶段性摘要
        total = len(records)
        if total > 0 and total % 5 == 0:
            def _gen_summary():
                try:
                    summary = agent.meeting_record_agent.generate_summary()
                    broadcast_sync({
                        "type": "summary_update",
                        "summary": summary,
                        "timestamp": datetime.now().isoformat()
                    })
                except Exception as e:
                    print(f"[摘要错误] {e}")
            threading.Thread(target=_gen_summary, daemon=True).start()

    # ── 回调：实时识别中间结果（字符级更新）──
    def on_text_update(new_text: str, full_text: str):
        msg = {
            "type": "interim",
            "text": new_text,
            "timestamp": datetime.now().isoformat()
        }
        broadcast_sync(msg)

    core_agent.set_speech_complete_callback(on_speech_complete)
    core_agent.set_text_update_callback(on_text_update)
    core_agent.on_speaker_detected_callback = on_speaker_detected  # 设置新说话人检测回调

    # 在后台线程启动（speech_recognition_agent 会阻塞）
    def run_agent():
        try:
            agent.start()
        except Exception as e:
            broadcast_sync({
                "type": "error",
                "message": f"启动失败: {str(e)}"
            })
            print(f"[Error] Agent 启动失败: {e}")

    threading.Thread(target=run_agent, daemon=True).start()

    # 广播状态消息
    broadcast_sync({"type": "status", "message": "录音已开始，开始说话..."})
    return {"status": "started"}


@app.post("/stop", response_model=StopResponse)
async def stop_recording():
    global core_agent

    if not core_agent or not core_agent.is_running:
        return {"status": "not_running", "summary": "", "transcript": []}

    core_agent.stop()

    # 获取完整转录记录（使用真实姓名）
    records = core_agent.meeting_record_agent.records
    transcript_entries = [
        {
            "speaker": core_agent.meeting_record_agent.get_speaker_display_name(r['speaker_label']),
            "text": r["text"],
            "timestamp": r["timestamp"],
            "language": "mixed"
        }
        for r in records
    ]

    # 生成 AI 总结
    summary = ""
    try:
        summary = core_agent.meeting_record_agent.generate_summary()
    except Exception as e:
        summary = f"总结生成失败: {e}"
        print(f"[Error] 总结生成失败: {e}")

    broadcast_sync({"type": "status", "message": "录音已停止，正在处理..."})

    return {
        "status": "stopped",
        "summary": summary,
        "transcript": transcript_entries
    }


# ──────────────────────────── PDF Upload ────────────────────────────

@app.post("/upload-pdf", response_model=UploadPdfResponse)
async def upload_pdf(file: UploadFile = File(...)):
    """
    上传 PDF 文件，提取专有名词并注入 ASR 热词表
    支持在录音开始前或录音过程中上传
    """
    filename = file.filename or "upload.pdf"
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="只支持 PDF 文件")

    # 保存文件到临时目录
    save_path = _PDF_UPLOAD_DIR / filename
    with open(save_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    # 提取专有名词
    try:
        terms = extract_terms_from_pdf(str(save_path))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF 解析失败: {e}")

    keywords = terms_to_keywords(terms)

    # 注入到 ASR 热词表（如果 agent 已初始化）
    injected = False
    if core_agent and core_agent.speech_recognition_agent:
        core_agent.speech_recognition_agent.add_keywords(keywords)
        injected = True
        print(f"🔥 热词已注入 ASR: {keywords[:10]}...")

    # 记录上传状态
    _uploaded_pdfs.append({
        "filename": filename,
        "terms": [{"word": t[0], "type": t[1]} for t in terms],
        "keyword_count": len(keywords),
        "injected_to_asr": injected,
    })

    # 广播到前端
    broadcast_sync({
        "type": "pdf_uploaded",
        "filename": filename,
        "terms": [{"word": t[0], "type": t[1]} for t in terms[:20]],
        "total": len(terms),
    })

    return {
        "status": "success",
        "filename": filename,
        "terms": [{"word": t[0], "type": t[1]} for t in terms],
        "injected_to_asr": injected,
        "message": f"提取到 {len(terms)} 个专有名词，{'已注入 ASR 热词表' if injected else '将在下次录音时生效'}"
    }


@app.get("/uploaded-pdfs", response_model=UploadedPdfsResponse)
async def get_uploaded_pdfs():
    """获取已上传 PDF 列表及提取的词条"""
    return {"pdfs": _uploaded_pdfs}


@app.delete("/uploaded-pdfs", response_model=ClearPdfsResponse)
async def clear_uploaded_pdfs():
    """清除所有上传的 PDF 记录（不删除热词，热词留到会议结束）"""
    _uploaded_pdfs.clear()
    # 清除保存的文件
    for f in _PDF_UPLOAD_DIR.glob("*.pdf"):
        f.unlink(missing_ok=True)
    return {"status": "cleared"}


# ──────────────────────────── Entry Point ────────────────────────────

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8765, log_level="info")
