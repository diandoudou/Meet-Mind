import os
import threading
import queue
from typing import Optional, Callable, Dict, Any, List
from datetime import datetime

from .speech_recognition_agent import SpeechRecognitionAgent
from .text_analysis_agent import TextAnalysisAgent
from .meeting_record_agent import MeetingRecordAgent

class CoreAgent:
    """
    会议助手的核心Agent,负责协调语音识别,文本分析等功能模块
    """
    
    def __init__(self, 
                 dashscope_api_key: Optional[str] = None,
                 openai_api_key: Optional[str] = None,
                 config: Optional[Dict[str, Any]] = None):
        """
        初始化CoreAgent
        
        Args:
            dashscope_api_key: DashScope API密钥
            openai_api_key: OpenAI API密钥
            config: 配置参数字典
        """
        # 设置API密钥环境变量
        if dashscope_api_key:
            os.environ['DASHSCOPE_API_KEY'] = dashscope_api_key
        
        # 合并默认配置
        self.config = self._merge_config(config or {})
        
        # 初始化语音识别Agent
        # 从环境变量获取唤醒关键词
        
        self.speech_recognition_agent = SpeechRecognitionAgent(
            sample_rate=self.config['sample_rate'],
            channels=self.config['channels'],
            block_size=self.config['block_size'],
            semantic_punctuation_enabled=self.config['semantic_punctuation_enabled'],
            on_text_callback=self._handle_recognized_text,
            on_speech_complete_callback=self._handle_speech_complete,
        )
        
        # 初始化文本分析Agent
        self.text_analysis_agent = TextAnalysisAgent(
            max_keywords=self.config['max_keywords']
        )
        
        # 初始化会议记录Agent
        self.meeting_record_agent = MeetingRecordAgent()
        
        # 状态管理
        self.is_running = False
        self.recognized_text_buffer = []  # 存储识别的文本
        self.current_speaker = None  # 当前说话人
        self.current_speaker_id = None  # 当前说话人ID
        self.last_text_update = datetime.now()
        
        # 结果队列和回调
        self.result_queue = queue.Queue()
        self.on_text_update_callback: Optional[Callable] = None
        self.on_summary_update_callback: Optional[Callable] = None
        self.on_keywords_update_callback: Optional[Callable] = None
        self.on_speech_complete_callback: Optional[Callable] = None
        self.on_command_executed_callback: Optional[Callable] = None
        self.on_speaker_detected_callback: Optional[Callable] = None
        
        # 语音检测相关
        self.last_speech_time = datetime.now()
        self.speech_timeout_seconds = 2.0  # 2秒无新语音视为语音结束
        
        # 分析线程
        self.analysis_thread = None
        self.stop_analysis_thread = False
    
    def _merge_config(self, user_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        合并默认配置和用户配置
        
        Args:
            user_config: 用户提供的配置
            
        Returns:
            合并后的配置
        """
        default_config = {
            'speech_model': os.getenv('DASHSCOPE_ASR_MODEL_NAME', 'paraformer-realtime-v2'),
            'sample_rate': 16000,
            'channels': 1,
            'block_size': 3200,
            'semantic_punctuation_enabled': False,
            'keyword_extraction_method': 'llm',
            'max_keywords': 10,
            'analysis_interval_seconds': 5,  # 分析间隔时间(秒)
            'max_text_buffer_length': 10000  # 最大文本缓冲区长度
        }
        
        merged_config = default_config.copy()
        merged_config.update(user_config)
        return merged_config
    
    def start(self):
        """
        启动会议助手
        """
        if self.is_running:
            print("会议助手已经在运行中")
            return

        self.is_running = True
        self.stop_analysis_thread = False

        # 启动分析线程
        self.analysis_thread = threading.Thread(target=self._analysis_worker)
        self.analysis_thread.daemon = True
        self.analysis_thread.start()

        print("会议助手已启动")
        print(f"语音识别模型: {self.config['speech_model']}")
        print(f"关键词提取方法: {self.config['keyword_extraction_method']}")

        # 启动语音识别
        try:
            self.speech_recognition_agent.start_recognition()
        except Exception as e:
            print(f"启动语音识别时出错: {e}")
            self.stop()
            # 重新抛出异常,让调用方(如GUI)能够捕获和处理
            raise
    
    def stop(self):
        """
        停止会议助手
        """
        if not self.is_running:
            return
        
        self.is_running = False
        self.stop_analysis_thread = True
        
        # 停止语音识别
        self.speech_recognition_agent.stop_recognition()
        
        # 等待分析线程结束
        if self.analysis_thread and self.analysis_thread.is_alive():
            self.analysis_thread.join(timeout=5)
        
        print("会议助手已停止")
    
    def _handle_recognized_text(self, text: str):
        """
        处理识别到的文本
        
        Args:
            text: 识别到的文本（ASR 返回的是累积的完整文本，不是增量）
        """
        # 更新最后语音时间
        self.last_speech_time = datetime.now()
        
        # ASR 返回的是累积文本，直接替换缓冲区（而不是 append）
        # 这样可以避免重复累积
        self.recognized_text_buffer = [text] if text.strip() else []
        
        # 更新最后更新时间
        self.last_text_update = datetime.now()
        
        # 当前文本就是最新的识别结果
        current_text = text

        # 发送到结果队列
        result = {
            'type': 'text_update',
            'text': text,
            'full_text': current_text,
            'timestamp': datetime.now().isoformat()
        }
        self.result_queue.put(result)
        
        # 调用文本更新回调
        if self.on_text_update_callback:
            self.on_text_update_callback(text, current_text)
    
    def _handle_speech_complete(self, text: str):
        """
        处理语音完成事件
        
        Args:
            text: 完成的语音文本
        """
        # 合并当前缓冲区的完整文本
        full_text = ' '.join(self.recognized_text_buffer)
        
        # 将完整的语音段落添加到会议记录Agent
        if full_text.strip():
            # 如果没有指定speaker_id,自动分配新的发言人
            speaker_label = self.meeting_record_agent.add_speech(full_text, self.current_speaker_id)
            print(f"[CoreAgent] 添加发言记录 - 发言人{speaker_label}: {full_text[:50]}...")

        # 调用语音完成回调
        if self.on_speech_complete_callback and full_text:
            self.on_speech_complete_callback(full_text)
        
        # 清空缓冲区,为新的语音做准备
        self.recognized_text_buffer = []
    
    def _analysis_worker(self):
        """
        分析线程工作函数,定期对累积的文本进行分析
        """
        import time
        
        while not self.stop_analysis_thread:
            try:
                # 检查是否有足够的文本进行分析
                if len(self.recognized_text_buffer) > 0:
                    # 检查距离上次分析的时间
                    time_since_update = (datetime.now() - self.last_text_update).total_seconds()
                    
                    # 如果距离上次更新超过指定时间,进行分析
                    if time_since_update > self.config['analysis_interval_seconds']:
                        self._perform_analysis()
                
                # 短暂睡眠避免CPU占用过高
                time.sleep(0.5)
                
            except Exception as e:
                print(f"分析线程出错: {e}")
                time.sleep(1)
    
    def _perform_analysis(self):
        """
        执行文本分析,包括关键词提取和总结生成
        """
        # 获取完整文本
        full_text = ' '.join(self.recognized_text_buffer)
        
        # 提取关键词
        keywords = self.text_analysis_agent.extract_keywords(full_text)
        
        # 生成简洁总结
        concise_summary = self.text_analysis_agent.generate_summary(full_text, "concise")
        
        # 发送到结果队列
        analysis_result = {
            'type': 'analysis_update',
            'keywords': keywords,
            'concise_summary': concise_summary,
            'timestamp': datetime.now().isoformat()
        }
        self.result_queue.put(analysis_result)
        
        # 调用回调函数
        if self.on_keywords_update_callback:
            self.on_keywords_update_callback(keywords)
        
        if self.on_summary_update_callback:
            self.on_summary_update_callback(concise_summary)
    
    def set_text_update_callback(self, callback: Callable[[str, str], None]):
        """
        设置文本更新回调函数
        
        Args:
            callback: 回调函数,接收(new_text, full_text)参数
        """
        self.on_text_update_callback = callback
    
    def set_summary_update_callback(self, callback: Callable[[str], None]):
        """
        设置总结更新回调函数
        
        Args:
            callback: 回调函数,接收summary参数
        """
        self.on_summary_update_callback = callback
    
    def set_keywords_update_callback(self, callback: Callable[[List[tuple]], None]):
        """
        设置关键词更新回调函数
        
        Args:
            callback: 回调函数,接收keywords参数
        """
        self.on_keywords_update_callback = callback
    
    def set_speech_complete_callback(self, callback: Callable[[str], None]):
        """
        设置语音完成回调函数
        
        Args:
            callback: 回调函数,接收speech_text参数
        """
        self.on_speech_complete_callback = callback
    
    def get_current_text(self) -> str:
        """
        获取当前识别的完整文本
        
        Returns:
            当前识别的完整文本
        """
        return ' '.join(self.recognized_text_buffer)
    
    def get_current_analysis(self) -> Dict[str, Any]:
        """
        获取当前的分析结果
        
        Returns:
            包含关键词和总结的分析结果
        """
        full_text = ' '.join(self.recognized_text_buffer)
        
        if not full_text.strip():
            return {
                'keywords': [],
                'comprehensive_summary': "",
                'concise_summary': ""
            }
        
        keywords = self.text_analysis_agent.extract_keywords(full_text)
        comprehensive_summary = self.text_analysis_agent.generate_summary(full_text, "comprehensive")
        concise_summary = self.text_analysis_agent.generate_summary(full_text, "concise")
        
        return {
            'keywords': keywords,
            'comprehensive_summary': comprehensive_summary,
            'concise_summary': concise_summary
        }
    
    def get_meeting_transcript(self) -> str:
        """
        获取格式化的会议记录
        
        Returns:
            带发言人标签的会议记录文本
        """
        return self.meeting_record_agent.get_formatted_transcript()
    
    def get_meeting_statistics(self) -> Dict[str, Any]:
        """
        获取会议统计信息
        
        Returns:
            统计信息字典
        """
        return self.meeting_record_agent.get_statistics()
    
    def set_current_speaker(self, speaker: str):
        """
        设置当前说话人
        
        Args:
            speaker: 说话人标识,如'A', 'B', '主持人'等
        """
        self.current_speaker = speaker
    
    def get_next_result(self, timeout: Optional[float] = None) -> Optional[Dict[str, Any]]:
        """
        获取下一个结果,用于流式处理
        
        Args:
            timeout: 超时时间(秒)
            
        Returns:
            结果字典,如果超时则返回None
        """
        try:
            return self.result_queue.get(timeout=timeout)
        except queue.Empty:
            return None