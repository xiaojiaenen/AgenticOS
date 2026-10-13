"""FTS5 查询串构造测试。

背景：``build_fts5_query`` 之前是 ``" OR ".join(query.split())`` —— 用户输入里的
标点会被 FTS5 当成语法符号。用户发一条含路径的消息（``读一下 docs/ 下的...``）
就会触发 ``fts5: syntax error near "/"``，表现为这条消息的记忆检索静默失败。

这类 bug 不会抛错到用户，只表现为"搜不到"，所以必须用真实 FTS5 验证语法合法。
"""

from __future__ import annotations

import sqlite3

import pytest

from app.services.memory_bm25 import build_fts5_query


class TestBuildFts5Query:
    def test_plain_words(self):
        assert build_fts5_query("hello world") == '"hello" OR "world"'

    @pytest.mark.parametrize(
        "query",
        [
            "读一下 docs/ 目录下的调研报告",
            "看 docs/module-map.md",
            "path/to/file.py 的内容",
            "C:\\Users\\x\\config",
            "带\"引号\"的词",
            "a AND b OR c",
            "带-连字符-的词",
            "带(括号)的词",
            "带*星号*的词",
            "带:冒号:的词",
            "带~波浪~的词",
        ],
    )
    def test_punctuation_does_not_break_syntax(self, query):
        """每个词都被双引号包裹，任何标点都不可能再被当成 FTS5 语法。"""
        fts = build_fts5_query(query)
        assert fts
        for term in fts.split(" OR "):
            assert term.startswith('"') and term.endswith('"'), term

    @pytest.mark.parametrize("query", ["...", "   ", "/", "\\", "-"])
    def test_punctuation_only_yields_empty(self, query):
        """全是标点时应返回空串让调用方跳过，而不是把非法查询丢给 SQLite。"""
        assert build_fts5_query(query) == ""

    def test_caps_term_count(self):
        """超长输入不能把查询串撑爆。"""
        fts = build_fts5_query(" ".join(f"w{i}" for i in range(200)))
        assert len(fts.split(" OR ")) <= 32

    def test_real_fts5_accepts_output(self):
        """用真实的 FTS5 表验证语法合法——这是本测试存在的意义。"""
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE VIRTUAL TABLE t USING fts5(content)")
        conn.execute("INSERT INTO t VALUES ('hello world')")
        try:
            for query in [
                "读一下 docs/ 目录下的调研报告，在 docs/module-map.md 里写说明",
                "path/to/file.py",
                "a AND b OR c",
                "带\"引号\"的词",
            ]:
                fts = build_fts5_query(query)
                # 不抛异常即通过
                conn.execute("SELECT content FROM t WHERE t MATCH ?", (fts,)).fetchall()
        finally:
            conn.close()

    def test_real_fts5_still_matches_when_asked(self):
        """转义不能把检索打坏：英文词仍要能命中。"""
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE VIRTUAL TABLE t USING fts5(content)")
        conn.execute("INSERT INTO t VALUES ('deployment guide')")
        try:
            rows = conn.execute(
                "SELECT content FROM t WHERE t MATCH ?",
                (build_fts5_query("deployment"),),
            ).fetchall()
            assert len(rows) == 1
        finally:
            conn.close()
