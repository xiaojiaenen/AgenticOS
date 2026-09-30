"""知识库检索分词模块。

提供两套分词策略，供检索链路按后端选择：

- ``tokenize``：jieba 词级分词（中文按词，英文/数字按 token），
  用于 MySQL FULLTEXT ngram 查询构造与 Python BM25 评分。
  jieba 惰性加载——首次调用才 import 并初始化词典，避免拖慢应用导入。
- ``bigram_tokenize``：旧版逐字 bigram 分词（保留原检索逻辑，
  兼容 SQLite FTS5 unicode61 的二元切分习惯，亦用于 A/B 召回对比）。

两者的公共约定：
- 输入统一转小写；
- 剥除标点/符号；
- 中文 token 只保留长度 >= 2（单字停用词与虚词无检索价值）；
- 英文/数字 token 全保留（英文单词、型号、数字串都是有效检索词）。
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# 与旧检索逻辑一致的中日韩范围（U+4E00-U+9FFF）
_CJK_RE = re.compile(r"[一-鿿]")
# 标点/符号（保留 \w 单词字符与 CJK）
_PUNCT_RE = re.compile(r"[^\w\s一-鿿]", re.UNICODE)
# 判断 token 是否含有效单词字符（字母/数字/下划线）
_WORD_RE = re.compile(r"\w", re.UNICODE)

_jieba = None


def _ensure_jieba():
    """惰性加载 jieba（首次调用才初始化词典）。"""
    global _jieba
    if _jieba is None:
        import jieba

        jieba.setLogLevel(logging.WARNING)  # 静默首次加载的词典日志
        _jieba = jieba
    return _jieba


def tokenize(text: str) -> list[str]:
    """jieba 词级分词（推荐路径）。

    中文按词典切词（保留长度 >= 2 的词），英文/数字按连续 token 保留，
    过滤标点与单字中文停用残片。jieba 首次调用时惰性加载。
    """
    jieba = _ensure_jieba()
    lowered = (text or "").lower()
    tokens: list[str] = []
    for raw in jieba.lcut(lowered):
        tok = raw.strip()
        if not tok:
            continue
        if _CJK_RE.search(tok):
            # 中文（或中英混合）词：整体保留长度 >= 2 的
            if len(tok) >= 2:
                tokens.append(tok)
            # 单字中文：丢弃（单字虚词/标点残片，检索价值低）
        else:
            # 英文/数字 token：剥除标点后保留（如 "mysql"、"v2"、"2024"）
            cleaned = _PUNCT_RE.sub("", tok)
            if cleaned and _WORD_RE.search(cleaned):
                tokens.append(cleaned)
    return tokens


def bigram_tokenize(text: str) -> list[str]:
    """旧版 bigram 分词（兼容路径，保留迁移前行为）。

    中文串做逐字二元切分（长度 1 时保留单字），非中文按空白分词。
    与迁移前 ``KnowledgeRetrieval._tokenize`` 逐字等价，
    用于 SQLite fallback 与新旧召回对比。
    """
    lowered = (text or "").lower()
    lowered = _PUNCT_RE.sub(" ", lowered)
    tokens: list[str] = []
    for part in lowered.split():
        if _CJK_RE.search(part):
            for i in range(len(part) - 1):
                tokens.append(part[i : i + 2])
            if len(part) == 1:
                tokens.append(part)
        else:
            tokens.append(part)
    return tokens
