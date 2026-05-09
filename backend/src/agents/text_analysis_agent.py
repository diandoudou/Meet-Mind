import os
import re
from collections import Counter
from typing import List, Dict, Any, Optional, Tuple

import jieba
import jieba.analyse
from dotenv import load_dotenv
from langchain_core.output_parsers import JsonOutputParser, StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI

# 加载环境变量
load_dotenv()


class TextAnalysisAgent:
    """
    文本分析Agent,负责从转录文本中提取关键词,生成会议总结
    """

    def __init__(self,
                 max_keywords: int = 10):
        """
        初始化文本分析Agent
        
        Args:
            max_keywords: 最大关键词数量
        """
        self.max_keywords = max_keywords
        
        # 初始化Gemini LLM (仅用于总结)
        self.gemini_llm = None
        self.gemini_api_key = os.getenv("GEMINI_API_KEY")
        if self.gemini_api_key:
            gemini_model = os.getenv("GEMINI_MODEL_NAME", "gemini-1.5-flash")
            self.gemini_llm = ChatGoogleGenerativeAI(
                model=gemini_model,
                google_api_key=self.gemini_api_key,
                temperature=0.7
            )
            print(f"✅ Gemini LLM 已加载用于会议总结: {gemini_model}")
        else:
            print("⚠️  未找到GEMINI_API_KEY环境变量,将使用本地方法生成总结")
        
        print("✅ 关键词提取: jieba (本地, 0 API成本)")

    def extract_keywords(self, text: str) -> List[Tuple[str, float]]:
        """
        从文本中提取关键词 (使用jieba, 0 API成本)
        
        Args:
            text: 输入文本
            
        Returns:
            关键词和权重的列表
        """
        return self._extract_keywords_jieba(text)

    def _extract_keywords_jieba(self, text: str) -> List[Tuple[str, float]]:
        """
        使用jieba提取关键词

        Args:
            text: 输入文本

        Returns:
            关键词和权重的列表
        """
        # 移除多余空格和特殊字符
        text = re.sub(r'\s+', ' ', text)
        text = re.sub(r'[\\n\\r]+', ' ', text)

        # 使用TF-IDF提取关键词
        keywords = jieba.analyse.extract_tags(
            text,
            topK=self.max_keywords,
            withWeight=True,
        )

        # 如果TF-IDF提取效果不佳,使用TextRank
        if len(keywords) < 3:
            keywords = jieba.analyse.textrank(
                text,
                topK=self.max_keywords,
                withWeight=True,
            )

        return keywords

    def generate_summary(self, text: str, summary_type: str = "comprehensive") -> str:
        """
        生成会议总结 - 使用Gemini API
        
        Args:
            text: 输入文本
            summary_type: 总结类型 (comprehensive: 详细总结, concise: 简洁总结)
            
        Returns:
            生成的总结文本
        """
        if self.gemini_llm:
            # 使用Gemini生成总结
            return self._generate_summary_gemini(text, summary_type)
        else:
            # 使用简单的本地方法生成总结
            return self._generate_summary_local(text)

    def _generate_summary_gemini(self, text: str, summary_type: str = "comprehensive") -> str:
        """
        使用Gemini API生成总结
        
        Args:
            text: 输入文本
            summary_type: 总结类型
            
        Returns:
            生成的总结文本
        """
        if not self.gemini_llm:
            raise ValueError("Gemini LLM未初始化,请确保GEMINI_API_KEY环境变量已设置")

        # 根据总结类型设置提示内容
        if summary_type == "comprehensive":
            summary_prompt = "请提供详细的会议总结,包括讨论的主要议题,达成的共识,提出的行动项和决策."
        else:
            summary_prompt = "请提供简洁的会议摘要,突出重点内容,控制在200字以内."

        # 构建提示
        prompt = ChatPromptTemplate.from_template("""
        你是一个专业的会议记录助手,请根据以下会议文本生成会议总结.
        
        {summary_prompt}
        
        会议文本:
        {text}
        
        请直接输出总结文本,不要添加额外的说明.
        """)

        # 设置输出解析器
        parser = StrOutputParser()

        # 构建链 - 使用Gemini LLM
        chain = prompt | self.gemini_llm | parser

        # 执行链
        try:
            return chain.invoke({
                "text": text,
                "summary_prompt": summary_prompt
            })
        except Exception as e:
            print(f"使用Gemini生成总结时出错: {e}")
            # 失败时回退到本地方法
            return self._generate_summary_local(text)

    def _generate_summary_local(self, text: str) -> str:
        """
        使用本地方法生成简单总结
        
        Args:
            text: 输入文本
            
        Returns:
            生成的简单总结文本
        """
        # 提取关键词
        keywords = self._extract_keywords_jieba(text)
        keyword_str = ", ".join([kw[0] for kw in keywords[:5]])

        # 简单统计
        sentences = re.split(r'[.!?;\n]+', text)
        sentences = [s.strip() for s in sentences if s.strip()]

        # 构建简单总结
        summary = f"会议主要讨论了关于{keyword_str}等内容.会议包含{len(sentences)}个主要观点."

        # 添加第一个和最后一个句子作为上下文
        if len(sentences) > 0:
            summary += f" 开始讨论:{sentences[0][:50]}..."
        if len(sentences) > 1:
            summary += f" 结束讨论:{sentences[-1][:50]}..."

        return summary

    def analyze_speaker_turns(self, text: str) -> Dict[str, Any]:
        """
        分析说话人轮流发言情况
        
        Args:
            text: 带说话人标记的输入文本,格式如"A: 发言内容\nB: 发言内容"
            
        Returns:
            说话人统计信息
        """
        # 简单的说话人识别模式
        speaker_pattern = r'^([A-Za-z0-9]+):'
        lines = text.strip().split('\n')

        speaker_counts = Counter()
        speaker_texts = {}

        current_speaker = None
        current_text = []

        for line in lines:
            match = re.match(speaker_pattern, line.strip())
            if match:
                # 处理前一个说话人的内容
                if current_speaker:
                    speaker_counts[current_speaker] += 1
                    if current_speaker not in speaker_texts:
                        speaker_texts[current_speaker] = []
                    speaker_texts[current_speaker].extend(current_text)

                # 开始新的说话人
                current_speaker = match.group(1)
                current_text = [line[match.end():].strip()]
            else:
                # 延续当前说话人的内容
                current_text.append(line.strip())

        # 处理最后一个说话人的内容
        if current_speaker:
            speaker_counts[current_speaker] += 1
            if current_speaker not in speaker_texts:
                speaker_texts[current_speaker] = []
            speaker_texts[current_speaker].extend(current_text)

        # 计算每个说话人的发言长度
        speaker_lengths = {}
        for speaker, texts in speaker_texts.items():
            full_text = ' '.join(texts)
            speaker_lengths[speaker] = len(full_text)

        return {
            "speaker_counts": dict(speaker_counts),
            "speaker_text_lengths": speaker_lengths,
            "total_turns": sum(speaker_counts.values())
        }

    def process_meeting_text(self, text: str) -> Dict[str, Any]:
        """
        处理完整的会议文本,返回综合分析结果
        
        Args:
            text: 会议文本
            
        Returns:
            包含关键词,总结,说话人分析等的综合结果
        """
        # 提取关键词
        keywords = self.extract_keywords(text)

        # 生成总结
        comprehensive_summary = self.generate_summary(text, "comprehensive")
        concise_summary = self.generate_summary(text, "concise")

        # 分析说话人
        speaker_analysis = self.analyze_speaker_turns(text)

        return {
            "keywords": keywords,
            "comprehensive_summary": comprehensive_summary,
            "concise_summary": concise_summary,
            "speaker_analysis": speaker_analysis,
            "raw_text": text
        }
