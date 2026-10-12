from uuid import uuid4

import pytest
from bs4 import BeautifulSoup
from markdown_it import MarkdownIt
from pydantic import ValidationError

from atlasmind.api.manual_structure import structured_document
from atlasmind.api.service_manual import ManualReadRequest


def leaves(nodes):
    return [
        leaf for node in nodes for leaf in ([node] if "text" in node else leaves(node["children"]))
    ]


def test_original_markdown_structure_retains_ingestion_paragraph_anchors():
    raw = (
        "# 使用手册\n\n## 首次上架\n\n必须提交 **总部审核**。\n\n"
        "- 保存草稿\n- 提交 `审核`\n"
    ).encode()
    paragraphs = [
        " ".join(line.split())
        for line in BeautifulSoup(MarkdownIt().render(raw.decode()), "html.parser")
        .get_text("\n")
        .splitlines()
        if line.strip()
    ]
    result = structured_document(raw, "text/markdown", paragraphs)
    assert result["format"] == "markdown"
    assert {"h1", "h2", "p", "ul"}.issubset({node.get("tag") for node in result["nodes"]})
    actual = [node for node in leaves(result["nodes"]) if node["paragraph"]]
    assert [" ".join(node["text"].split()) for node in actual] == paragraphs
    assert [node["paragraph"] for node in actual] == list(range(1, len(paragraphs) + 1))


def test_unmatched_original_falls_back_without_inaccurate_anchors():
    result = structured_document(b"# replaced", "text/markdown", ["Original paragraph"])
    assert result["format"] == "text"
    assert leaves(result["nodes"]) == [{"text": "Original paragraph", "paragraph": 1}]


def test_links_and_html_never_return_active_attributes_or_script_nodes():
    raw = b"[click](https://example.test)\n\n<script>alert(1)</script>\n"
    paragraphs = [
        " ".join(line.split())
        for line in BeautifulSoup(MarkdownIt().render(raw.decode()), "html.parser")
        .get_text("\n")
        .splitlines()
        if line.strip()
    ]
    result = structured_document(raw, "text/markdown", paragraphs)
    assert "https://" not in str(result)
    assert "'tag': 'script'" not in str(result)


def test_precise_reference_cannot_bypass_verification_using_chunk_view():
    with pytest.raises(ValidationError):
        ManualReadRequest(
            document_id=uuid4(),
            version_id=uuid4(),
            chunk_id=uuid4(),
            digest="sha256:" + "a" * 64,
            paragraph_start=1,
            paragraph_end=1,
            quote_digest="sha256:" + "a" * 64,
        )
