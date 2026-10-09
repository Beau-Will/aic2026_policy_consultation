"""测试共享夹具：临时语料库 + 示例政策原文。"""

from __future__ import annotations

import pathlib
import sys

import pytest

# 让 tests 在未 pip install 时也能直接使用 src 布局
_SRC = pathlib.Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

SAMPLE_POLICY = """示例市人民政府办公室关于印发《示例市支持小微企业创业补贴实施办法》的通知
示政办发〔2024〕12号
2024年3月1日

第一章 总则

第一条 为支持小微企业发展，制定本办法。
第二条 本办法适用于在本市依法登记注册、正常经营满6个月的小微企业。

第二章 申报

第三条 申请创业补贴的，应当提交下列材料：
（一）营业执照复印件；
（二）近6个月社保缴纳证明。
第四条 申报时间为每年4月1日至4月30日，逾期不再受理。
"""

SAMPLE_NOTICE = """XX市人力资源和社会保障局关于做好2024年度创业补贴申报工作的通知
X人社发〔2024〕7号
2024年3月5日

一、申报对象
在本市登记注册并正常经营满6个月的小微企业、个体工商户。

二、申报时间
申报期为2024年4月1日至4月30日，逾期不再受理。

三、申报材料
（一）营业执照复印件；
（二）近6个月社保缴纳证明。
"""


@pytest.fixture
def corpus_env(tmp_path, monkeypatch):
    """把语料库指向临时文件，并在测试后重置进程级句柄。"""
    db = tmp_path / "corpus.db"
    monkeypatch.setenv("POLICY_CORPUS_DB", str(db))
    from policy_agent.corpus.store import reset_store

    reset_store()
    yield db
    reset_store()


@pytest.fixture
def sample_md(tmp_path) -> pathlib.Path:
    path = tmp_path / "sample_policy.md"
    path.write_text(SAMPLE_POLICY, encoding="utf-8")
    return path


@pytest.fixture
def populated_store(corpus_env, sample_md):
    from policy_agent.corpus.importer import build_document
    from policy_agent.corpus.store import get_store

    store = get_store()
    store.add_document(build_document(sample_md))
    return store
