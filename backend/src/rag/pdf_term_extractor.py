"""
PDF 专有名词提取器
从上传的 PDF 中提取专业术语，注入到 ASR 热词表以提升识别准确率
"""
import re
from collections import Counter
from pathlib import Path
from typing import List, Tuple

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None  # type: ignore


# 常见英文单词（排除，不作为热词）
_COMMON_ENGLISH = {
    "The", "And", "For", "Are", "But", "Not", "You", "All", "Can", "Our",
    "From", "With", "This", "That", "Have", "What", "Your", "Will", "More",
    "When", "Some", "They", "Been", "Than", "Then", "Into", "Time", "Very",
    "Just", "Also", "Over", "After", "Being", "Each", "Such", "Here", "These",
    "There", "Where", "While", "How", "Who", "Which", "About", "Their", "Were",
    "Most", "Make", "Like", "Year", "Good", "Same", "Come", "Work", "Using",
    "Data", "Based", "User", "Team", "Project", "System", "Figure", "Table",
    "Section", "Chapter", "Page", "First", "Second", "Third", "Finally",
}

_COMMON_CAPS = {
    "THE", "AND", "FOR", "ARE", "BUT", "NOT", "YOU", "ALL", "CAN", "HER",
    "WAS", "ONE", "OUR", "OUT", "DAY", "GET", "USE", "HAD", "HIS", "HOW",
    "MAN", "NEW", "NOW", "OLD", "SEE", "TWO", "WAY", "WHO", "BOY", "DID",
    "ITS", "LET", "PUT", "SAY", "SHE", "TOO", "PPT", "PDF", "DOC", "URL",
    "HTTP", "HTTPS", "NULL", "TRUE", "FALSE", "NONE",
}


def extract_text_from_pdf(pdf_path: str) -> str:
    """从 PDF 文件提取全文"""
    if PdfReader is None:
        raise ImportError("请安装 pypdf: pip install pypdf")

    reader = PdfReader(pdf_path)
    full_text = ""
    for page in reader.pages:
        text = page.extract_text()
        if text:
            full_text += text + "\n"
    return full_text


def extract_terms(text: str, max_terms: int = 50) -> List[Tuple[str, str]]:
    """
    从文本中提取专有名词和技术术语

    Returns:
        List of (term, reason) 例如 [("MeetMind", "camel_case"), ("ASR", "acronym")]
    """
    terms: dict[str, str] = {}

    # ① CamelCase 词汇（如 MeetMind, ChatGPT, LangChain）
    camel = re.findall(r'\b[A-Z][a-z]+(?:[A-Z][a-z0-9]*)+\b', text)
    for w in camel:
        terms[w] = "camel_case"

    # ② 全大写缩写（如 ASR, NLP, HKUST, API）
    acronyms = re.findall(r'\b[A-Z]{2,8}\b', text)
    for w in acronyms:
        if w not in _COMMON_CAPS:
            terms[w] = "acronym"

    # ③ 大写开头、重复出现 2 次以上的词（可能是产品名、人名、机构名）
    cap_words = re.findall(r'\b[A-Z][a-z]{2,}\b', text)
    cap_counter = Counter(cap_words)
    for word, count in cap_counter.items():
        if count >= 2 and word not in _COMMON_ENGLISH and word not in terms:
            terms[word] = "proper_noun"

    # ④ 英文+数字混合词（如 GPT4, COMP2011, Gemini1.5）
    mixed = re.findall(r'\b[A-Za-z]+\d+[A-Za-z0-9]*\b', text)
    for w in mixed:
        if len(w) >= 3:
            terms[w] = "mixed_term"

    # 按类型优先级排序: camel_case > acronym > mixed_term > proper_noun
    priority = {"camel_case": 0, "acronym": 1, "mixed_term": 2, "proper_noun": 3}
    sorted_terms = sorted(terms.items(), key=lambda x: priority.get(x[1], 9))

    return sorted_terms[:max_terms]


def extract_terms_from_pdf(pdf_path: str, max_terms: int = 50) -> List[Tuple[str, str]]:
    """
    从 PDF 文件提取专有名词

    Args:
        pdf_path: PDF 文件路径
        max_terms: 最多返回的词条数

    Returns:
        List of (term, type) 元组
    """
    if not Path(pdf_path).exists():
        raise FileNotFoundError(f"PDF 不存在: {pdf_path}")

    text = extract_text_from_pdf(pdf_path)
    if not text.strip():
        return []

    terms = extract_terms(text, max_terms)
    print(f"📄 从 PDF 提取到 {len(terms)} 个专有名词")
    return terms


def terms_to_keywords(terms: List[Tuple[str, str]]) -> List[str]:
    """将 (term, type) 列表转为纯关键词列表"""
    return [t[0] for t in terms]
