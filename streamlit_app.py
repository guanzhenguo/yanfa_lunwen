"""实验室内部论文检索页。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

from kms.catalog import Catalog
from kms.config import load_settings
from kms.storage import create_store

st.set_page_config(
    page_title="实验室论文库",
    page_icon=":material/menu_book:",
    layout="wide",
)

OA_ALL, OA_YES, OA_NO = "全部", "仅 OA", "非 OA"
PDF_ALL, PDF_YES, PDF_NO = "全部", "已入库", "未下载"


def _oa_param(choice: str | None) -> bool | None:
    if choice == OA_YES:
        return True
    if choice == OA_NO:
        return False
    return None


def _pdf_param(choice: str | None) -> bool | None:
    if choice == PDF_YES:
        return True
    if choice == PDF_NO:
        return False
    return None


def _open_with_system(path: Path) -> None:
    if os.name == "nt":
        os.startfile(path)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        os.system(f'open "{path}"')  # noqa: S605
    else:
        os.system(f'xdg-open "{path}"')  # noqa: S605


@st.cache_data(ttl=30, max_entries=32)
def load_pdf_bytes(storage_key: str) -> bytes:
    settings = load_settings()
    store = create_store(settings)
    return store.get_bytes(storage_key)


st.title("实验室论文库")
st.caption("Springer 入库论文 · 仅实验室内部使用。交互问答见左侧「文献问答」页。")

settings = load_settings()
with st.sidebar:
    st.header("筛选")
    keyword = st.text_input("关键词", placeholder="题名、作者、摘要", key="q")
    doi = st.text_input("DOI", placeholder="10.1038/…", key="doi")
    year_from = st.number_input(
        "起始年",
        min_value=1990,
        max_value=2100,
        value=None,
        step=1,
        placeholder="不限",
        key="year_from",
    )
    year_to = st.number_input(
        "结束年",
        min_value=1990,
        max_value=2100,
        value=None,
        step=1,
        placeholder="不限",
        key="year_to",
    )
    oa_choice = st.segmented_control(
        "开放获取",
        [OA_ALL, OA_YES, OA_NO],
        default=OA_ALL,
        key="oa_filter",
    )
    pdf_choice = st.segmented_control(
        "PDF",
        [PDF_ALL, PDF_YES, PDF_NO],
        default=PDF_ALL,
        key="pdf_filter",
    )
    st.caption(f"存储：{settings.storage_backend} / {settings.minio_bucket}")
    st.caption(str(settings.catalog_path))

with Catalog(settings.catalog_path) as catalog:
    stats = catalog.stats()
    rows = catalog.search(
        q=keyword,
        doi=doi,
        year_from=int(year_from) if year_from else None,
        year_to=int(year_to) if year_to else None,
        oa=_oa_param(oa_choice),
        has_pdf=_pdf_param(pdf_choice),
        limit=200,
    )

with st.container(horizontal=True):
    st.metric("文献", stats["total"], border=True)
    st.metric("OA", stats["oa"], border=True)
    st.metric("已有 PDF", stats["with_pdf"], border=True)
    st.metric("本次命中", len(rows), border=True)

if stats["total"] == 0:
    st.info("文献库还是空的。先运行 `python parse_springer.py -q Perovskite --pages 1 --download-pdf` 入库。")
    st.stop()

if not rows:
    st.warning("没有符合条件的论文，试试放宽筛选。")
    st.stop()

table = pd.DataFrame(
    [
        {
            "id": item["id"],
            "year": item.get("year") or None,
            "title": item["title"],
            "authors": item.get("authors") or "",
            "doi": item.get("doi") or "",
            "oa": bool(item.get("open_access")),
            "has_pdf": bool(item.get("storage_key")),
            "venue": item.get("parent") or "",
        }
        for item in rows
    ]
)
table = table.set_index("id")

st.subheader("检索结果")
st.caption("点选一行查看详情和 PDF。")
event = st.dataframe(
    table,
    column_config={
        "year": st.column_config.NumberColumn("年份", format="%d"),
        "title": st.column_config.TextColumn("题名", width="large"),
        "authors": st.column_config.TextColumn("作者"),
        "doi": st.column_config.TextColumn("DOI"),
        "oa": st.column_config.CheckboxColumn("OA"),
        "has_pdf": st.column_config.CheckboxColumn("已有 PDF"),
        "venue": st.column_config.TextColumn("期刊/丛书"),
    },
    on_select="rerun",
    selection_mode="single-row",
    key="results",
    width="stretch",
)

selected_rows = event.selection.rows if event.selection else []
if not selected_rows:
    st.stop()

doc_id = int(table.index[selected_rows[0]])
with Catalog(settings.catalog_path) as catalog:
    doc = catalog.get_by_id(doc_id)

if not doc:
    st.error("这条记录已不在库中。")
    st.stop()

st.subheader(doc["title"] or "未命名文献")
st.table(
    {
        "DOI": doc.get("doi") or "—",
        "作者": doc.get("authors") or "—",
        "发表": doc.get("published") or "—",
        "来源": doc.get("parent") or "—",
        "OA": "是" if doc.get("open_access") else "否",
        "原文": doc.get("url") or "—",
    },
    border="horizontal",
    width="content",
)

if doc.get("description"):
    st.markdown("**摘要**")
    st.write(doc["description"])

storage_key = doc.get("storage_key") or ""
file_location = Path(doc.get("file_location") or "")
pdf_bytes = b""
if storage_key:
    try:
        pdf_bytes = load_pdf_bytes(storage_key)
    except FileNotFoundError:
        st.warning("库里有 PDF 记录，但对象存储中找不到文件。")
    except Exception as exc:
        st.error(f"读取 PDF 失败：{exc}")

actions = st.container(horizontal=True)
with actions:
    if pdf_bytes:
        filename = (doc.get("doi") or f"paper-{doc['id']}").replace("/", "_") + ".pdf"
        st.download_button(
            "下载 PDF",
            data=pdf_bytes,
            file_name=filename,
            mime="application/pdf",
            icon=":material/download:",
        )
    if file_location.is_file() and os.name == "nt":
        if st.button("用系统阅读器打开", icon=":material/open_in_new:"):
            _open_with_system(file_location)
    if doc.get("url"):
        st.link_button("打开 Springer 页面", doc["url"], icon=":material/link:")

if pdf_bytes:
    try:
        st.pdf(pdf_bytes, height=640)
    except Exception:
        st.caption("当前环境无法内嵌预览，请下载或用系统阅读器打开。")
else:
    st.caption("这篇还没有入库 PDF。对 OA 文献重新跑采集并加上 `--download-pdf`。")
