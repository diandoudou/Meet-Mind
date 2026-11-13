# 离线说话人分离（WhisperX + pyannote）

## 流程

```
会中 DashScope 流式 ASR（低延迟 + 热词）
     + 同步缓存 PCM → 停录写出 WAV
会后 WhisperX ASR/对齐 + pyannote diarization
     → 带 SPEAKER_xx 的转写
     → 交给 LangGraph Summary ∥ Action
     →（可选）写入 RAG
```

## 安装

```bash
cd backend
pip install whisperx pyannote.audio
```

1. 在 Hugging Face 接受 `pyannote/speaker-diarization-3.1`（及依赖模型）使用条款  
2. 创建 Access Token，写入 `.env`：`HF_TOKEN=...`  
3. 确保 `.env` 中：

```env
MEETING_AUDIO_PERSIST=true
DIARIZATION_OFFLINE_ENABLED=true
WHISPERX_MODEL=base
DIARIZATION_DEVICE=cpu   # 有 GPU 可改 cuda
```

## API

- `POST /stop`：停录后自动跑离线分离（有 WAV 且启用时），响应含 `audio_path` / `diarization_engine` / `diarization_meta`
- `POST /api/diarize`：对已有 WAV 单独跑分离

```json
{ "audio_path": "backend/data/meeting_audio/meeting_xxx.wav", "language": "zh" }
```

## 降级

| 情况 | 行为 |
|------|------|
| 未装 whisperx | 跳过离线分离，沿用会中 DashScope 转写 |
| 无 `HF_TOKEN` | 仅 WhisperX 转写/对齐，无说话人标签（`whisperx-align-only`） |
| 无音频缓存 | 跳过，使用会中转写 |
| `DIARIZATION_OFFLINE_ENABLED=false` | 完全关闭离线管线 |

## 注意

- WhisperX/pyannote 为**批处理**，会后耗时随音频长度与设备变化，不适合塞进会中实时路径  
- 会中实时说话人标签与会后 `SPEAKER_xx` 编号可能不一致；最终纪要以离线结果为准（若分离成功）
