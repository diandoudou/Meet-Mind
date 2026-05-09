"""
会议记录Agent - 负责存储和管理会议对话记录
支持多发言人标记和会议总结生成
"""
import os
from typing import List, Dict, Any, Optional
from datetime import datetime
from dotenv import load_dotenv

# LangChain导入
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

load_dotenv()


class MeetingRecordAgent:
    """
    会议记录Agent,负责:
    1. 存储所有对话记录
    2. 自动标记发言人(A,B,C,D等)
    3. 使用Gemini API生成会议总结(总结功能保留使用Gemini)
    """
    
    def __init__(self):
        """初始化会议记录Agent"""
        self.records: List[Dict[str, Any]] = []  # 存储所有会议记录
        self.speaker_counter = 0  # 发言人计数器
        self.speaker_labels = {}  # speaker_id -> 字母标签 (A, B, C...)
        self.speaker_names: Dict[str, str] = {}  # 字母标签 -> 真实姓名
        self.meeting_start_time = datetime.now()  # 会议开始时间
        
        # 初始化Gemini API - 仅用于总结
        self.gemini_api_key = os.getenv("GEMINI_API_KEY")
        self.gemini_model_name = os.getenv("GEMINI_MODEL_NAME", "gemini-2.5-flash")
        
        self.llm = None
        if self.gemini_api_key:
            try:
                self.llm = ChatGoogleGenerativeAI(
                    model=self.gemini_model_name,
                    google_api_key=self.gemini_api_key,
                    temperature=0.7
                )
                print(f"[MeetingRecordAgent] 使用 Gemini模型进行总结: {self.gemini_model_name}")
            except Exception as e:
                print(f"[MeetingRecordAgent] 初始化LLM失败: {e}")

    def _extract_speaker_introduction(self, record: dict) -> Optional[str]:
        """
        从发言中提取说话人自我介绍
        
        Args:
            record: 发言记录
            
        Returns:
            提取的姓名，如果没有则返回None
        """
        import re
        
        # 只在会议前60秒内检测自我介绍
        elapsed_seconds = (datetime.now() - self.meeting_start_time).total_seconds()
        if elapsed_seconds > 60:
            return None
        
        text = record["text"]
        speaker_label = record["speaker_label"]
        
        # 扩展的自我介绍模式（支持中英文，允许数字字母组合）
        patterns = [
            r'我是\s*([^，。！？,.\s]{1,20})',
            r'我叫\s*([^，。！？,.\s]{1,20})',
            r'我的名字是\s*([^，。！？,.\s]{1,20})',
            r'我名字叫\s*([^，。！？,.\s]{1,20})',
            r'大家好[，,]?\s*我是\s*([^，。！？,.\s]{1,20})',
            r'你好[，,]?\s*我是\s*([^，。！？,.\s]{1,20})',
            r'I\s+am\s+([A-Za-z0-9]{1,20})',
            r"I'm\s+([A-Za-z0-9]{1,20})",
            r'My\s+name\s+is\s+([A-Za-z0-9]{1,20})',
            r'This\s+is\s+([A-Za-z0-9]{1,20})',
        ]
        
        print(f"[DEBUG] 检查自我介绍 ({elapsed_seconds:.1f}s) - {speaker_label}: {text[:50]}...")
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                name = match.group(1).strip()
                # 允许各种名称格式，包括speaker1, Ella, 张明等
                if name:
                    if speaker_label not in self.speaker_names:
                        self.speaker_names[speaker_label] = name
                        print(f"[MeetingRecordAgent] ✓ 识别到说话人: {speaker_label} -> {name} (匹配模式: {pattern})")
                        return name
                    else:
                        print(f"[MeetingRecordAgent] ⚠️ 说话人 {speaker_label} 已有名称: {self.speaker_names[speaker_label]}")
        
        print(f"[MeetingRecordAgent] 未匹配到自我介绍: {text[:80]}...")
        return None

    def add_speech(self, text: str, speaker_id: Optional[str] = None) -> str:
        """
        添加一条发言记录

        Args:
            text: 发言内容
            speaker_id: 发言人ID（可选，不指定则自动分配）

        Returns:
            发言人标签(A, B, C...)
        """
        if not text.strip():
            return ""

        if speaker_id is None:
            speaker_label = chr(65 + self.speaker_counter)  # A, B, C, D...
            self.speaker_counter += 1
            speaker_id = f"speaker_{self.speaker_counter}"
            self.speaker_labels[speaker_id] = speaker_label
        elif speaker_id not in self.speaker_labels:
            speaker_label = chr(65 + len(self.speaker_labels))
            self.speaker_labels[speaker_id] = speaker_label
        else:
            speaker_label = self.speaker_labels[speaker_id]

        # 添加记录
        record = {
            "speaker_id": speaker_id,
            "speaker_label": speaker_label,
            "text": text.strip(),
            "timestamp": datetime.now().isoformat()
        }
        self.records.append(record)
        
        # 尝试提取说话人姓名
        self._extract_speaker_introduction(record)

        return speaker_label
    
    def get_formatted_transcript(self) -> str:
        """
        获取格式化的会议记录文本
        
        Returns:
            格式化的会议记录(带发言人标签)
        """
        if not self.records:
            return "暂无会议记录"
        
        lines = []
        for record in self.records:
            speaker_label = record["speaker_label"]
            text = record["text"]
            lines.append(f"{speaker_label}: {text}")
        
        return "\n".join(lines)
    
    def get_plain_transcript(self) -> str:
        """
        获取纯文本会议记录(不带发言人标签)
        
        Returns:
            纯文本会议记录
        """
        if not self.records:
            return "暂无会议记录"
        
        return " ".join([record["text"] for record in self.records])
    
    def get_speaker_display_name(self, speaker_label: str) -> str:
        """
        获取说话人的显示名称（如果已通过自我介绍识别到真实姓名则返回真实姓名，否则返回标签）

        Args:
            speaker_label: 说话人字母标签 (A, B, C...)

        Returns:
            显示名称，如 "Alice" 或 "Speaker A"
        """
        if speaker_label in self.speaker_names:
            return self.speaker_names[speaker_label]
        return f"Speaker {speaker_label}"

    def generate_summary(self) -> str:
        """
        使用Gemini API生成会议总结
        
        Returns:
            会议总结文本
        """
        if not self.records:
            return "暂无会议内容,无法生成总结"
        
        if not self.llm:
            return "错误:Gemini API未初始化,无法生成总结"
        
        # 获取格式化的会议记录
        transcript = self.get_formatted_transcript()
        
        # 构建提示词
        prompt_template = """请根据以下会议记录生成一份完整的会议总结.

会议记录:
{transcript}

请按以下格式生成总结:

1. 会议概要(2-3句话概括会议主题和目的)
2. 主要讨论内容(列出3-5个核心讨论点)
3. 重要决议或行动项(如果有)
4. 关键信息(时间,预算,负责人等重要信息)

请保持简洁明了,重点突出:
"""
        
        try:
            # 调用Gemini API
            chat_prompt = ChatPromptTemplate.from_template(prompt_template)
            chain = chat_prompt | self.llm | StrOutputParser()
            summary = chain.invoke({"transcript": transcript})
            
            return summary
        except Exception as e:
            error_msg = f"生成总结时出错: {str(e)}"
            print(f"[MeetingRecordAgent] {error_msg}")
            return error_msg
    
    def clear_records(self):
        """清空所有会议记录"""
        self.records = []
        self.speaker_counter = 0
        self.speaker_labels = {}
        self.speaker_names = {}
        self.meeting_start_time = datetime.now()
        print("[MeetingRecordAgent] 会议记录已清空")
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        获取会议统计信息
        
        Returns:
            包含统计信息的字典
        """
        if not self.records:
            return {
                "total_speeches": 0,
                "total_speakers": 0,
                "total_words": 0
            }
        
        total_words = sum(len(record["text"]) for record in self.records)
        
        return {
            "total_speeches": len(self.records),
            "total_speakers": len(self.speaker_labels),
            "total_words": total_words,
            "speakers": list(self.speaker_labels.values())
        }
