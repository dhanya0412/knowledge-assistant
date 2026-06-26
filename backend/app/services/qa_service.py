import re

from pymongo.errors import PyMongoError

import app.database as database
from app.services.preprocessor import sent_tokenize
from app.services.retrieval import build_tfidf_vectorizer, rank_stored_document_chunks


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
DEFINITION_CUE_BONUS = 0.25
CHUNK_SCORE_WEIGHT = 0.15
ENTITY_REPEAT_PENALTY = 0.04
ENTITY_START_BONUS = 0.08
DEFINITION_CONTEXT_SENTENCES = 2
DEFINITION_CUE_PATTERNS = (
    r"\b{entity}\b\s+(?:is|are|refers to|means|stands for|denotes)\b",
    r"\b{entity}\b\s+\([^)]*\)\s+(?:is|are|refers to|means|stands for|denotes)\b",
    r"\b(?:defined as|known as|called)\s+\b{entity}\b",
)
DEFINITION_QUESTION_PATTERNS = (
    r"^what\s+(?:is|are)\s+(.+?)\??$",
    r"^define\s+(.+?)\??$",
    r"^what\s+does\s+(.+?)\s+stand\s+for\??$",
)
NON_DEFINITION_SENTENCE_PATTERNS = (
    r"\bmodules?\s+(?:are|is)\s+as\s+follows\b",
    r"\bnote\s+that\b",
    r"\bdoes\s+not\s+mean\b",
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
    for chunk, chunk_score in ranked_chunks:
        sentences = sent_tokenize(chunk.text)
        for index, sentence in enumerate(sentences):
            candidates.append({
                "sentence": sentence,
                "sentence_index": index,
                "chunk_sentences": sentences,
                "document": chunk.filename,
                "chunk_id": chunk.chunk_id,
                "chunk_score": chunk_score,
            })

    return candidates


def _rank_sentences(question, candidates):
    try:
        from sklearn.metrics.pairwise import cosine_similarity
    except ImportError as exc:
        raise QAError("question answering service unavailable", status_code=500) from exc

    corpus = [question] + [candidate["sentence"] for candidate in candidates]
    vectorizer = build_tfidf_vectorizer()

    try:
        matrix = vectorizer.fit_transform(corpus)
    except ValueError as exc:
        if "empty vocabulary" in str(exc):
            return None, 0
        raise QAError("question answering failed", status_code=500) from exc

    similarity_scores = cosine_similarity(matrix[0:1], matrix[1:]).flatten()
    definition_entity = _definition_entity(question)
    scores = [
        _answer_score(
            candidate,
            float(similarity_score),
            definition_entity,
        )
        for candidate, similarity_score in zip(candidates, similarity_scores)
    ]
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

    if _is_definition_context(question, candidate["sentence"]):
        end_index = index + 1
        if (
            index + 1 < len(sentences)
            and not _looks_like_non_definition(sentences[index + 1])
        ):
            end_index = index + DEFINITION_CONTEXT_SENTENCES

        return " ".join(sentences[index:end_index])

    return candidate["sentence"]


def _is_procedural_context(question, sentence):
    text = f"{question} {sentence}".lower()
    if any(cue in text for cue in PROCEDURAL_CUES):
        return True

    return sentence.strip().lower().startswith("step ")


def _answer_score(candidate, similarity_score, definition_entity):
    sentence = candidate["sentence"]
    score = similarity_score + (candidate["chunk_score"] * CHUNK_SCORE_WEIGHT)

    if not definition_entity:
        return score

    if _sentence_defines_entity(sentence, definition_entity):
        score += DEFINITION_CUE_BONUS
        if _starts_with_entity(sentence, definition_entity):
            score += ENTITY_START_BONUS
    elif _looks_like_non_definition(sentence):
        score -= DEFINITION_CUE_BONUS

    entity_mentions = len(re.findall(
        rf"\b{re.escape(definition_entity)}\b",
        sentence.lower(),
    ))
    if entity_mentions > 1 and not _sentence_defines_entity(sentence, definition_entity):
        score -= (entity_mentions - 1) * ENTITY_REPEAT_PENALTY

    return max(score, 0)


def _definition_entity(question):
    normalized_question = re.sub(r"\s+", " ", question.strip().lower())
    for pattern in DEFINITION_QUESTION_PATTERNS:
        match = re.match(pattern, normalized_question)
        if match:
            entity = match.group(1).strip(" .?!:;\"'")
            return entity or None

    return None


def _is_definition_context(question, sentence):
    entity = _definition_entity(question)
    return bool(entity and _sentence_defines_entity(sentence, entity))


def _sentence_defines_entity(sentence, entity):
    normalized_sentence = sentence.lower()
    escaped_entity = re.escape(entity)
    return any(
        re.search(pattern.format(entity=escaped_entity), normalized_sentence)
        for pattern in DEFINITION_CUE_PATTERNS
    )


def _starts_with_entity(sentence, entity):
    return sentence.strip().lower().startswith(entity)


def _looks_like_non_definition(sentence):
    normalized_sentence = sentence.lower()
    return any(
        re.search(pattern, normalized_sentence)
        for pattern in NON_DEFINITION_SENTENCE_PATTERNS
    )


def _empty_answer(question):
    return {
        "question": question,
        "answer": None,
        "source": None,
        "confidence": 0,
    }
