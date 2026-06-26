from dataclasses import dataclass
import re


DEFAULT_CHUNK_WORDS = 120
DEFAULT_CHUNK_OVERLAP = 30
TFIDF_STOP_WORDS = "english"
TFIDF_NGRAM_RANGE = (1, 2)
TFIDF_NORM = "l2"


@dataclass(frozen=True)
class Chunk:
    document_id: str
    filename: str
    text: str
    chunk_id: int


def chunk_text(text, chunk_words=DEFAULT_CHUNK_WORDS, overlap=DEFAULT_CHUNK_OVERLAP):
    paragraphs = [
        re.sub(r"\s+", " ", paragraph).strip()
        for paragraph in re.split(r"\n\s*\n+", text or "")
        if paragraph.strip()
    ]

    chunks = []
    buffer = []  # accumulated words for the chunk currently being built

    for paragraph in paragraphs:
        words = paragraph.split()

        if len(words) > chunk_words:
            # Paragraph alone exceeds the target size: flush whatever has
            # accumulated so far, then split this paragraph on its own
            # using a sliding window (same overlap behavior as before).
            if buffer:
                chunks.append(" ".join(buffer))
                buffer = []

            step = max(chunk_words - overlap, 1)
            last_window = []
            for start in range(0, len(words), step):
                window = words[start:start + chunk_words]
                if window:
                    chunks.append(" ".join(window))
                    last_window = window
                if start + chunk_words >= len(words):
                    break

            # Carry the tail of the last window forward so the next chunk
            # still overlaps with this paragraph's split, just like the
            # overlap maintained between any two consecutive chunks.
            buffer = last_window[-overlap:] if overlap > 0 else []
            continue

        # Paragraph fits within the chunk size on its own: accumulate
        # consecutive paragraphs together until the target size is hit.
        if buffer and len(buffer) + len(words) > chunk_words:
            chunks.append(" ".join(buffer))
            tail = buffer[-overlap:] if overlap > 0 else []
            buffer = tail + words
        else:
            buffer = buffer + words

    if buffer:
        chunks.append(" ".join(buffer))

    return chunks


def chunks_from_documents(documents):
    chunks = []
    for document in documents:
        document_id = str(document["_id"])
        filename = document.get("original_filename") or document.get("filename", "")
        for index, text in enumerate(chunk_text(document.get("text_content", "")), start=1):
            chunks.append(Chunk(document_id, filename, text, index))

    return chunks


def chunks_from_stored_documents(documents):
    chunks = []
    for document in documents:
        document_id = str(document["_id"])
        filename = document.get("original_filename") or document.get("filename", "")
        for stored_chunk in document.get("chunks", []):
            chunks.append(Chunk(
                document_id=document_id,
                filename=filename,
                text=stored_chunk["text"],
                chunk_id=stored_chunk["chunk_id"],
            ))

    return chunks


def rank_stored_document_chunks(query, documents, limit):
    return rank_chunks(query, chunks_from_stored_documents(documents), limit)


def rank_chunks(query, chunks, limit):
    if not chunks:
        return []

    try:
        from sklearn.metrics.pairwise import cosine_similarity
    except ImportError as exc:
        raise RuntimeError("search service unavailable") from exc

    corpus = [query] + [chunk.text for chunk in chunks]
    vectorizer = build_tfidf_vectorizer()

    try:
        matrix = vectorizer.fit_transform(corpus)
    except ValueError as exc:
        if "empty vocabulary" in str(exc):
            return []
        raise RuntimeError("search failed") from exc

    scores = cosine_similarity(matrix[0:1], matrix[1:]).flatten()
    ranked = sorted(
        zip(chunks, scores),
        key=lambda item: (-item[1], item[0].document_id, item[0].chunk_id),
    )

    return [
        (chunk, float(score))
        for chunk, score in ranked[:limit]
        if score > 0
    ]


def build_tfidf_vectorizer():
    from sklearn.feature_extraction.text import TfidfVectorizer

    return TfidfVectorizer(
        stop_words=TFIDF_STOP_WORDS,
        ngram_range=TFIDF_NGRAM_RANGE,
        norm=TFIDF_NORM,
    )
