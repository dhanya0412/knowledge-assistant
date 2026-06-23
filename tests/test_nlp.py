import re

import pytest

from app.services.parser import (
    EmptyDocumentError,
    MissingFileError,
    UnsupportedFileTypeError,
    extract_text,
)
from app.services.keyword_extractor import extract_keywords
from app.services.preprocessor import clean_text, tokenize
from app.services.summarizer import generate_summary


def test_parser_extracts_text_from_txt_file(tmp_path):
    filepath = tmp_path / "manual.txt"
    filepath.write_text("Pump manual\nCheck pressure.", encoding="utf-8")

    text = extract_text(filepath)

    assert "Pump manual" in text
    assert "Check pressure." in text


def test_parser_raises_empty_document_for_blank_txt_file(tmp_path):
    filepath = tmp_path / "empty.txt"
    filepath.write_text("   \n\t\n", encoding="utf-8")

    with pytest.raises(EmptyDocumentError):
        extract_text(filepath)


def test_parser_rejects_missing_file(tmp_path):
    filepath = tmp_path / "missing.txt"

    with pytest.raises(MissingFileError):
        extract_text(filepath)


def test_parser_rejects_unsupported_file_type(tmp_path):
    filepath = tmp_path / "manual.exe"
    filepath.write_text("not allowed", encoding="utf-8")

    with pytest.raises(UnsupportedFileTypeError):
        extract_text(filepath)


def test_parser_extracts_text_from_docx_file(tmp_path):
    docx = pytest.importorskip("docx")

    filepath = tmp_path / "manual.docx"
    document = docx.Document()
    document.add_paragraph("Pump maintenance guide")
    document.add_paragraph("Inspect seal pressure weekly.")
    document.save(filepath)

    text = extract_text(filepath)

    assert "Pump maintenance guide" in text
    assert "Inspect seal pressure weekly." in text


def test_parser_extracts_table_text_from_docx_file(tmp_path):
    docx = pytest.importorskip("docx")

    filepath = tmp_path / "table.docx"
    document = docx.Document()
    table = document.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "Pressure"
    table.cell(0, 1).text = "120 PSI"
    document.save(filepath)

    text = extract_text(filepath)

    assert "Pressure" in text
    assert "120 PSI" in text


def test_parser_extracts_text_from_pdf_file(tmp_path):
    pytest.importorskip("pypdf")

    filepath = tmp_path / "manual.pdf"
    filepath.write_bytes(_simple_pdf_bytes("Pump PDF manual"))

    text = extract_text(filepath)

    assert "Pump PDF manual" in text


def test_preprocessor_cleans_whitespace_and_blank_lines():
    raw_text = " Pump   manual\r\n\r\n\r\nCheck\tpressure.  "

    cleaned = clean_text(raw_text)

    assert cleaned == "Pump manual Check pressure."


def test_preprocessor_returns_empty_string_for_blank_text():
    assert clean_text(" \n\t ") == ""


def test_preprocessor_tokenizes_clean_text():
    tokens = tokenize("Pump pressure is 120 PSI.")

    assert tokens == ["pump", "pressure", "is", "120", "psi"]


def test_preprocessor_tokenize_ignores_punctuation():
    tokens = tokenize("Pump, seal-pressure: OK!")

    assert tokens == ["pump", "seal", "pressure", "ok"]


def test_keyword_extractor_returns_keywords_for_normal_text():
    pytest.importorskip("sklearn")
    text = clean_text(
        "Pump maintenance requires pressure inspection. "
        "Seal pressure and pump vibration should be monitored weekly."
    )

    keywords = extract_keywords(text, top_n=5)

    assert keywords
    assert any("pump" in keyword for keyword in keywords)
    assert any("pressure" in keyword for keyword in keywords)


def test_keyword_extractor_removes_english_stop_words():
    pytest.importorskip("sklearn")
    text = clean_text(
        "The pump is in the room and the pressure is high. "
        "The seal pressure requires inspection."
    )

    keywords = extract_keywords(text, top_n=10)

    assert "the" not in keywords
    assert "and" not in keywords
    assert "is" not in keywords


def test_keyword_extractor_respects_max_keyword_limit():
    pytest.importorskip("sklearn")
    text = clean_text(
        "Pump pressure vibration seal bearing motor shaft alignment "
        "maintenance inspection lubrication temperature flow."
    )

    keywords = extract_keywords(text, top_n=3)

    assert len(keywords) <= 3


def test_keyword_extractor_returns_deterministic_output():
    pytest.importorskip("sklearn")
    text = clean_text(
        "Pump maintenance requires pressure inspection. "
        "Seal pressure and pump vibration should be monitored weekly."
    )

    first = extract_keywords(text, top_n=5)
    second = extract_keywords(text, top_n=5)

    assert first == second


def test_keyword_extractor_extracts_bigrams():
    pytest.importorskip("sklearn")
    text = clean_text(
        "Machine learning improves diagnostics. "
        "Machine learning improves maintenance predictions. "
        "Machine learning supports anomaly detection."
    )

    keywords = extract_keywords(text, top_n=5)

    assert "machine learning" in keywords


def test_keyword_extractor_rejects_empty_input():
    with pytest.raises(ValueError, match="text is required"):
        extract_keywords("   ")


def test_summarizer_generates_summary_from_multi_sentence_text():
    pytest.importorskip("sklearn")
    text = clean_text(
        "Pump maintenance should be performed weekly. "
        "The cafeteria menu changes every Friday. "
        "Seal pressure must be inspected during maintenance. "
        "Pump vibration should be monitored after startup."
    )

    summary = generate_summary(text, max_sentences=2)

    assert summary
    assert len(_split_summary_sentences(summary)) <= 2
    assert "maintenance" in summary.lower() or "pump" in summary.lower()


def test_summarizer_preserves_original_sentence_order():
    pytest.importorskip("sklearn")
    text = clean_text(
        "Pump startup begins with visual inspection. "
        "Seal pressure must be checked before operation. "
        "Vibration readings should be recorded after startup. "
        "Seal pressure must be checked after shutdown."
    )

    summary = generate_summary(text, max_sentences=2)
    selected_sentences = _split_summary_sentences(summary)
    selected_indexes = [text.find(sentence) for sentence in selected_sentences]

    assert selected_indexes == sorted(selected_indexes)


def test_summarizer_returns_short_text_unchanged():
    text = clean_text("Pump pressure must be checked.")

    summary = generate_summary(text, max_sentences=3)

    assert summary == text


def test_summarizer_rejects_empty_input():
    with pytest.raises(ValueError, match="text is required"):
        generate_summary("   ")


def _split_summary_sentences(text):
    return [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+", text)
        if sentence.strip()
    ]


def _simple_pdf_bytes(text):
    content = f"BT /F1 24 Tf 100 700 Td ({text}) Tj ET".encode("ascii")
    objects = [
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n",
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n",
        b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >> endobj\n",
        b"4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n",
        b"5 0 obj << /Length "
        + str(len(content)).encode("ascii")
        + b" >> stream\n"
        + content
        + b"\nendstream endobj\n",
    ]

    result = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objects:
        offsets.append(len(result))
        result.extend(obj)

    xref_offset = len(result)
    result.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    result.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        result.extend(f"{offset:010d} 00000 n \n".encode("ascii"))

    result.extend(
        f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n".encode("ascii")
    )
    return bytes(result)
