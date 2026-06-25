from pymongo.errors import PyMongoError

import app.database as database
from app.services.preprocessor import sent_tokenize
from app.services.retrieval import rank_stored_document_chunks


TOP_CHUNK_LIMIT = 3
MIN_ANSWER_CONFIDENCE = 0.05
PROCEDURAL_CONTEXT_SENTENCES = 4
PROCEDURAL_CUES = (
    "step by step",
    "steps",
    "process",
    "procedure",
    "instructions",
    "how to",
    "follow these",
)


class QAError(Exception):
    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def answer_question(question):
    normalized_question = _normalize_question(question)
    documents = _fetch_searchable_documents()

    if not documents:
        return _empty_answer(normalized_question)

    ranked_chunks = _rank_chunks(normalized_question, documents)
    if not ranked_chunks:
        return _empty_answer(normalized_question)

    candidates = _candidate_sentences_from_chunks(ranked_chunks)
    if not candidates:
        return _empty_answer(normalized_question)

    best_candidate, score = _rank_sentences(normalized_question, candidates)
    if best_candidate is None or score < MIN_ANSWER_CONFIDENCE:
        return _empty_answer(normalized_question)

    return {
        "question": normalized_question,
        "answer": _answer_context(normalized_question, best_candidate),
        "source": {
            "document": best_candidate["document"],
            "chunk_id": best_candidate["chunk_id"],
        },
        "confidence": round(score, 4),
    }


def _normalize_question(question):
    if question is None or not str(question).strip():
        raise QAError("question is required")

    return str(question).strip()


def _fetch_searchable_documents():
    try:
        return list(database.db.documents.find(
            {
                "processed": True,
                "$or": [
                    {"status": "processed"},
                    {"status": {"$exists": False}},
                ],
                "text_content": {"$exists": True, "$ne": ""},
                "chunks": {"$exists": True, "$ne": []},
            },
            {
                "filename": 1,
                "original_filename": 1,
                "text_content": 1,
                "chunks": 1,
            },
        ))
    except PyMongoError as exc:
        raise QAError(
            "documents could not be loaded",
            status_code=500,
        ) from exc


def _rank_chunks(question, documents):
    try:
        return rank_stored_document_chunks(
            question,
            documents,
            TOP_CHUNK_LIMIT,
        )
    except RuntimeError as exc:
        message = str(exc)
        if message not in {"search failed", "search service unavailable"}:
            message = "question answering failed"
        raise QAError(message, status_code=500) from exc


def _candidate_sentences_from_chunks(ranked_chunks):
    candidates = []
    for chunk, _score in ranked_chunks:
        sentences = sent_tokenize(chunk.text)
        for index, sentence in enumerate(sentences):
            candidates.append({
                "sentence": sentence,
                "sentence_index": index,
                "chunk_sentences": sentences,
                "document": chunk.filename,
                "chunk_id": chunk.chunk_id,
            })

    return candidates


def _rank_sentences(question, candidates):
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity
    except ImportError as exc:
        raise QAError("question answering service unavailable", status_code=500) from exc

    corpus = [question] + [candidate["sentence"] for candidate in candidates]
    vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2))

    try:
        matrix = vectorizer.fit_transform(corpus)
    except ValueError as exc:
        if "empty vocabulary" in str(exc):
            return None, 0
        raise QAError("question answering failed", status_code=500) from exc

    scores = cosine_similarity(matrix[0:1], matrix[1:]).flatten()
    ranked = sorted(
        zip(candidates, scores),
        key=lambda item: (-item[1], item[0]["document"], item[0]["chunk_id"]),
    )

    if not ranked:
        return None, 0

    candidate, score = ranked[0]
    return candidate, float(score)


def _answer_context(question, candidate):
    sentences = candidate["chunk_sentences"]
    index = candidate["sentence_index"]

    if _is_procedural_context(question, candidate["sentence"]):
        return " ".join(
            sentences[index:index + PROCEDURAL_CONTEXT_SENTENCES]
        )

    return candidate["sentence"]


def _is_procedural_context(question, sentence):
    text = f"{question} {sentence}".lower()
    if any(cue in text for cue in PROCEDURAL_CUES):
        return True

    return sentence.strip().lower().startswith("step ")


def _empty_answer(question):
    return {
        "question": question,
        "answer": None,
        "source": None,
        "confidence": 0,
    }
