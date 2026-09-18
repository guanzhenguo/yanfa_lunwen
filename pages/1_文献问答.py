"""Streamlit page for literature Q&A."""

from __future__ import annotations

import streamlit as st

from kms.catalog import Catalog
from kms.chat import ChatStore, collect_turn
from kms.config import load_settings
from kms.keywords import KeywordStore
from kms.kg import KnowledgeGraph

st.set_page_config(
    page_title="文献问答",
    page_icon=":material/chat:",
    layout="wide",
)

st.title("文献问答")
st.caption("先检索入库论文，再基于题名、摘要、关键词和图谱回答。交互方式对齐 Yuxi 的多轮对话。")

settings = load_settings()
if "qa_messages" not in st.session_state:
    st.session_state.qa_messages = []
if "qa_thread_id" not in st.session_state:
    st.session_state.qa_thread_id = None

cols = st.columns([1, 4])
with cols[0]:
    if st.button("新对话", width="stretch"):
        st.session_state.qa_messages = []
        st.session_state.qa_thread_id = None
        st.rerun()
    st.caption(f"模型：{settings.ai_model or '未填写'}")
    st.caption("已配置" if settings.ai_ready else "未配置 API Key，将返回检索结果")

for item in st.session_state.qa_messages:
    with st.chat_message(item["role"]):
        st.write(item["content"])
        sources = item.get("sources") or []
        if sources:
            labels = [
                f"[{src.get('index')}] {src.get('title')}"
                + (f" ({src['year']})" if src.get("year") else "")
                for src in sources
            ]
            st.caption("来源：" + "；".join(labels))

question = st.chat_input("向文献库提问，Enter 发送")
if question:
    st.session_state.qa_messages.append({"role": "user", "content": question, "sources": []})
    with Catalog(settings.catalog_path) as catalog:
        result = collect_turn(
            ChatStore(catalog),
            catalog,
            KeywordStore(catalog),
            KnowledgeGraph(catalog),
            settings,
            user_id=0,
            thread_id=st.session_state.qa_thread_id,
            question=question,
        )
    st.session_state.qa_thread_id = result.get("thread_id")
    st.session_state.qa_messages.append(
        {
            "role": "assistant",
            "content": result.get("content") or "",
            "sources": result.get("sources") or [],
        }
    )
    st.rerun()
