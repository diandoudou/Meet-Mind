"""
实体提取Agent - 从会议文本中提取人名,任务和时间
混合方案:规则匹配 + 轻量LLM
"""
import re
import os
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()


class EntityExtractionAgent:
    """
    实体提取Agent
    策略:优先使用规则匹配(0 API成本),复杂场景才用DashScope LLM
    """
    
    def __init__(self, use_llm_fallback: bool = False):
        """
        初始化实体提取Agent
        
        Args:
            use_llm_fallback: 是否在规则匹配失败时使用LLM兜底(需要额外安装langchain)
        """
        self.use_llm_fallback = use_llm_fallback
        self.llm = None
        
        # 如果启用LLM兜底,初始化DashScope LLM(延迟导入避免强制依赖)
        if use_llm_fallback:
            try:
                from langchain_openai import ChatOpenAI
                
                dashscope_api_key = os.getenv("DASHSCOPE_API_KEY")
                if dashscope_api_key:
                    dashscope_llm_model = os.getenv("DASHSCOPE_LLM_MODEL_NAME", "deepseek-r1")
                    dashscope_llm_base_url = os.getenv("DASHSCOPE_LLM_BASE_URL",
                                                      "https://dashscope.aliyuncs.com/compatible-mode/v1")
                    self.llm = ChatOpenAI(
                        model=dashscope_llm_model,
                        api_key=dashscope_api_key,
                        base_url=dashscope_llm_base_url
                    )
                    print("LLM兜底已启用 - 使用DashScope")
            except ImportError:
                print("警告: 未安装langchain,LLM兜底功能不可用,将只使用规则匹配")
        
        # 常见任务动词
        self.task_verbs = [
            '完成', '提交', '准备', '撰写', '编写', '修改', '审核', '确认',
            '联系', '安排', '协调', '跟进', '落实', '检查', '测试', '部署',
            '整理', '汇总', '分析', '评估', '优化', '改进'
        ]
        
        # 时间关键词
        self.time_keywords = [
            '今天', '明天', '后天', '本周', '下周', '本月', '下月',
            '周一', '周二', '周三', '周四', '周五', '周六', '周日',
            '早上', '上午', '中午', '下午', '晚上', '傍晚'
        ]
    
    def extract_all(self, text: str) -> Dict[str, Any]:
        """
        从文本中提取所有实体
        
        Args:
            text: 输入文本
            
        Returns:
            {
                "persons": [{"name": str, "role": str}],
                "tasks": [{"description": str, "assignee": str, "deadline": str}],
                "api_calls": int
            }
        """
        api_calls = 0
        
        # 1. 先尝试规则匹配(0 API成本)
        rule_result = self._extract_by_rules(text)
        
        # 2. 如果规则匹配效果好,直接返回
        if self._is_extraction_sufficient(rule_result):
            rule_result["api_calls"] = 0
            rule_result["method"] = "rules"
            return rule_result
        
        # 3. 规则匹配不足,使用LLM兜底
        if self.use_llm_fallback and self.llm:
            llm_result = self._extract_by_llm(text)
            api_calls = 1
            llm_result["api_calls"] = api_calls
            llm_result["method"] = "llm"
            return llm_result
        
        # 4. 无LLM兜底,返回规则结果
        rule_result["api_calls"] = 0
        rule_result["method"] = "rules"
        return rule_result
    
    def _extract_by_rules(self, text: str) -> Dict[str, Any]:
        """
        基于规则的实体提取(0 API成本)
        
        Returns:
            {
                "persons": [{"name": str, "role": str}],
                "tasks": [{"description": str, "assignee": str, "deadline": str}]
            }
        """
        persons = self._extract_persons(text)
        tasks = self._extract_tasks(text)
        
        # 匹配任务和人名
        matched_tasks = self._match_tasks_to_persons(text, persons, tasks)
        
        return {
            "persons": persons,
            "tasks": matched_tasks
        }
    
    def _extract_persons(self, text: str) -> List[Dict[str, str]]:
        """
        提取人名(规则匹配)
        
        支持的模式:
        1. "张三负责..."
        2. "由李四来..."
        3. "王五将..."
        4. "赵六需要..."
        """
        persons = []
        person_set = set()
        
        # 模式1: [人名] + [负责/处理/跟进/完成/准备等]
        pattern1 = r'([\u4e00-\u9fa5]{2,4})(?:负责|处理|跟进|完成|准备|撰写|联系|安排)'
        matches1 = re.finditer(pattern1, text)
        for match in matches1:
            name = match.group(1)
            if name not in person_set and self._is_valid_person_name(name):
                person_set.add(name)
                persons.append({
                    "name": name,
                    "role": "负责人",
                    "position": match.start()
                })
        
        # 模式2: [由/让/请] + [人名] + [来/去]
        pattern2 = r'(?:由|让|请)([\u4e00-\u9fa5]{2,4})(?:来|去|做|负责|处理)'
        matches2 = re.finditer(pattern2, text)
        for match in matches2:
            name = match.group(1)
            if name not in person_set and self._is_valid_person_name(name):
                person_set.add(name)
                persons.append({
                    "name": name,
                    "role": "执行人",
                    "position": match.start()
                })
        
        # 模式3: [@人名] 或 [人名:] (常见于即时通讯)
        pattern3 = r'[@]([\u4e00-\u9fa5]{2,4})|^([\u4e00-\u9fa5]{2,4})[::]'
        matches3 = re.finditer(pattern3, text, re.MULTILINE)
        for match in matches3:
            name = match.group(1) or match.group(2)
            if name and name not in person_set and self._is_valid_person_name(name):
                person_set.add(name)
                persons.append({
                    "name": name,
                    "role": "发言人",
                    "position": match.start()
                })
        
        return persons
    
    def _extract_tasks(self, text: str) -> List[Dict[str, str]]:
        """
        提取任务描述(规则匹配)
        
        支持的模式:
        1. [动词] + [名词短语]
        2. "需要..." / "要..."
        """
        tasks = []
        
        # 构建动词正则
        verb_pattern = '|'.join(self.task_verbs)
        
        # 模式1: [动词] + [内容] (到句子结束或标点)
        pattern1 = f'({verb_pattern})([^,.!?;\n]{{5,50}})'
        matches1 = re.finditer(pattern1, text)
        for match in matches1:
            verb = match.group(1)
            content = match.group(2).strip()
            tasks.append({
                "description": verb + content,
                "verb": verb,
                "position": match.start()
            })
        
        # 模式2: 需要/要 + [内容]
        pattern2 = r'(?:需要|要)([^,.!?;\n]{5,50})'
        matches2 = re.finditer(pattern2, text)
        for match in matches2:
            content = match.group(1).strip()
            # 避免重复
            if not any(t["description"] in content or content in t["description"] for t in tasks):
                tasks.append({
                    "description": "需要" + content,
                    "verb": "需要",
                    "position": match.start()
                })
        
        return tasks
    
    def _match_tasks_to_persons(self, text: str, persons: List[Dict], tasks: List[Dict]) -> List[Dict]:
        """
        将任务匹配给对应的人
        
        策略:基于文本位置的就近匹配
        """
        matched_tasks = []
        
        for task in tasks:
            task_pos = task["position"]
            
            # 找到任务前后最近的人名
            closest_person = None
            min_distance = float('inf')
            
            for person in persons:
                person_pos = person["position"]
                distance = abs(task_pos - person_pos)
                
                # 优先考虑任务前面的人名(在100个字符内)
                if person_pos < task_pos and distance < 100:
                    if distance < min_distance:
                        min_distance = distance
                        closest_person = person
                # 其次考虑任务后面的人名(在50个字符内)
                elif person_pos > task_pos and distance < 50:
                    if distance < min_distance:
                        min_distance = distance
                        closest_person = person
            
            # 提取时间信息
            deadline = self._extract_deadline_near_task(text, task_pos)
            
            matched_tasks.append({
                "description": task["description"],
                "assignee": closest_person["name"] if closest_person else None,
                "deadline": deadline,
                "confidence": 1.0 if closest_person else 0.5
            })
        
        return matched_tasks
    
    def _extract_deadline_near_task(self, text: str, task_pos: int) -> Optional[str]:
        """
        提取任务附近的时间信息
        
        Args:
            text: 全文
            task_pos: 任务位置
            
        Returns:
            时间字符串或None
        """
        # 在任务前后100个字符内搜索时间
        search_start = max(0, task_pos - 50)
        search_end = min(len(text), task_pos + 100)
        search_text = text[search_start:search_end]
        
        # 模式1: 具体日期
        date_patterns = [
            r'(\d{1,2}月\d{1,2}日)',
            r'(\d{4}[-/年]\d{1,2}[-/月]\d{1,2}日?)',
            r'(下?周[一二三四五六日])',
            r'(本周|下周|本月|下月)',
            r'(今天|明天|后天)'
        ]
        
        for pattern in date_patterns:
            match = re.search(pattern, search_text)
            if match:
                return match.group(1)
        
        # 模式2: 相对时间
        time_match = re.search(r'([一二三四五六七八九十\d]+天[内后]|[一二三四五六七八九十\d]+周[内后])', search_text)
        if time_match:
            return time_match.group(1)
        
        return None
    
    def _is_valid_person_name(self, name: str) -> bool:
        """
        验证是否是有效的人名
        
        排除常见的误判:
        - 单字(太短)
        - 超过4个字(太长)
        - 常见动词,名词
        """
        if len(name) < 2 or len(name) > 4:
            return False
        
        # 排除常见非人名词汇
        excluded = {
            '我们', '大家', '他们', '自己', '公司', '团队', '部门',
            '项目', '方案', '计划', '问题', '任务', '工作', '会议',
            '今天', '明天', '本周', '下周', '需要', '可以', '应该'
        }
        
        return name not in excluded
    
    def _is_extraction_sufficient(self, result: Dict) -> bool:
        """
        判断规则提取是否足够好
        
        如果提取到了人名和任务,且置信度高,就不需要LLM兜底
        """
        has_persons = len(result["persons"]) > 0
        has_tasks = len(result["tasks"]) > 0
        
        # 如果有高置信度的匹配,认为足够好
        if has_persons and has_tasks:
            high_confidence_tasks = [
                t for t in result["tasks"] 
                if t.get("confidence", 0) >= 0.8
            ]
            return len(high_confidence_tasks) > 0
        
        return False
    
    def _extract_by_llm(self, text: str) -> Dict[str, Any]:
        """
        使用LLM进行实体提取(兜底方案,1次API调用)
        
        Returns:
            {
                "persons": [{"name": str, "role": str}],
                "tasks": [{"description": str, "assignee": str, "deadline": str}]
            }
        """
        try:
            from langchain_core.prompts import ChatPromptTemplate
            from langchain_core.output_parsers import JsonOutputParser
            
            prompt = ChatPromptTemplate.from_template("""
你是一个专业的会议记录分析助手,请从以下会议文本中提取:

1. **人名**:识别所有参与者的姓名和角色
2. **任务**:识别所有待办任务及其负责人和截止时间

会议文本:
{text}

请以JSON格式返回,格式如下:
{{
  "persons": [
    {{"name": "张三", "role": "负责人"}}
  ],
  "tasks": [
    {{"description": "完成方案设计", "assignee": "张三", "deadline": "本周五"}}
  ]
}}

要求:
- 如果某个任务没有明确负责人,assignee设为null
- 如果没有截止时间,deadline设为null
- 只返回JSON,不要额外说明
""")
            
            parser = JsonOutputParser()
            chain = prompt | self.llm | parser
            
            result = chain.invoke({"text": text})
            
            # 确保返回格式正确
            if "persons" not in result:
                result["persons"] = []
            if "tasks" not in result:
                result["tasks"] = []
            
            # 添加置信度
            for task in result["tasks"]:
                task["confidence"] = 0.9  # LLM提取的默认高置信度
            
            return result
            
        except Exception as e:
            print(f"LLM提取失败: {e}")
            # 回退到规则提取
            return self._extract_by_rules(text)
    
    def extract_from_sentence(self, sentence: str) -> Dict[str, Any]:
        """
        从单个句子中提取实体(快速模式)
        
        Args:
            sentence: 单个句子
            
        Returns:
            提取结果
        """
        # 单句默认只用规则,不调用LLM
        result = self._extract_by_rules(sentence)
        result["api_calls"] = 0
        result["method"] = "rules"
        return result
