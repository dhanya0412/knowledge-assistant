import os
import re

from pymongo.errors import PyMongoError

import app.database as database
from app.services.preprocessor import sent_tokenize
from app.services.retrieval import build_tfidf_vectorizer, rank_stored_document_chunks


TOP_CHUNK_LIMIT = 8
MIN_ANSWER_CONFIDENCE = 0.05
PROCEDURAL_CONTEXT_SENTENCES = 4
NARRATIVE_SENTENCES_BEFORE = 1
NARRATIVE_SENTENCES_AFTER = 3
LIST_CONTEXT_SENTENCES = 6
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
NUMERIC_CONTENT_BONUS = 0.06
LIST_STRUCTURE_BONUS = 0.06
HEADING_BONUS = 0.04
NARRATIVE_INTRO_BONUS = 0.04
DEFINITION_CONTEXT_SENTENCES = 2
RETRIEVAL_DEBUG_ENABLED = os.getenv(
    "QA_RETRIEVAL_DEBUG",
    "true",
).lower() in {"1", "true", "yes", "on"}

QUESTION_TYPE_DEFINITION = "definition"
QUESTION_TYPE_PROCEDURAL = "procedural"
QUESTION_TYPE_LIST = "list"
QUESTION_TYPE_NUMERIC = "numeric"
QUESTION_TYPE_NARRATIVE = "narrative"
QUESTION_TYPE_GENERAL = "general"
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
NUMERIC_QUESTION_PATTERNS = (
    r"^how\s+(?:much|many)\b",
    r"^what\s+(?:was|were|is|are)\s+(?:the\s+)?(?:revenue|operating\s+income|"
    r"net\s+income|earnings(?:\s+per\s+share)?|diluted\s+earnings\s+per\s+share|"
    r"cost|price|amount|percentage|total|rate)\b",
)
LIST_QUESTION_PATTERNS = (
    r"^(?:what|which)\s+are\b",
    r"^(?:list|name)\b",
    r"^what\s+(?:products?|business\s+segments?|segments?|services?|offerings?|"
    r"features?|benefits?|risks?|factors?)\b",
)
NARRATIVE_QUESTION_PATTERNS = (
    r"^what\s+did\b",
    r"^what\s+message\s+did\b",
    r"^what\s+does\s+.+?\s+say\s+about\b",
    r"^what\s+are\s+.+?sustainability\s+goals\b",
    r"^what\s+investments?\s+(?:has|have|did)\b",
)
NUMERIC_CONTENT_PATTERN = re.compile(
    r"(?:[$\u20ac\u00a3\u00a5]\s?\d|\b\d[\d,.]*(?:\s?%)?|"
    r"\b(?:million|billion)\b)",
    re.IGNORECASE,
)
NUMBERED_OR_BULLET_PATTERN = re.compile(
    r"^\s*(?:[-*\u2022]|\(?\d+[.)])\s+",
)
KNOWN_HEADING_PATTERN = re.compile(
    r"^\s*(?:risk\s+factors|intelligent\s+cloud|"
    r"productivity\s+and\s+business\s+processes|shareholder\s+letter|"
    r"financial\s+highlights)\b",
    re.IGNORECASE,
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

    _log_retrieval_debug(normalized_question, ranked_chunks)
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
                "is_chunk_start": index == 0,
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
    question_type = _classify_question(question)
    definition_entity = _definition_entity(question)
    scores = [
        _answer_score(
            candidate,
            float(similarity_score),
            definition_entity,
            question_type,
        )
        for candidate, similarity_score in zip(candidates, similarity_scores)
    ]
    ranked = sorted(
        zip(candidates, scores),
        key=lambda item: (
            -item[1],
            item[0]["document"],
            item[0]["chunk_id"],
            item[0]["sentence_index"],
        ),
    )

    if not ranked:
        return None, 0

    candidate, score = ranked[0]
    return candidate, float(score)


def _answer_context(question, candidate):
    sentences = candidate["chunk_sentences"]
    index = candidate["sentence_index"]
    question_type = _classify_question(question)

    if question_type == QUESTION_TYPE_NARRATIVE:
        return _narrative_context(sentences, index)

    if question_type == QUESTION_TYPE_LIST:
        return _list_context(sentences, index)

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


def _answer_score(candidate, similarity_score, definition_entity, question_type):
    sentence = candidate["sentence"]
    score = similarity_score + (candidate["chunk_score"] * CHUNK_SCORE_WEIGHT)

    # These deliberately small bonuses only break close lexical matches;
    # cosine similarity remains the dominant sentence-ranking signal.
    if question_type == QUESTION_TYPE_NUMERIC and _contains_numeric_content(sentence):
        score += NUMERIC_CONTENT_BONUS
    elif question_type == QUESTION_TYPE_LIST and _has_list_structure(sentence):
        score += LIST_STRUCTURE_BONUS
    elif (
        question_type == QUESTION_TYPE_NARRATIVE
        and candidate["is_chunk_start"]
    ):
        score += NARRATIVE_INTRO_BONUS

    if _looks_like_heading(sentence):
        score += HEADING_BONUS

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


def _classify_question(question):
    normalized = re.sub(r"\s+", " ", question.strip().lower())

    if _matches_any(normalized, NUMERIC_QUESTION_PATTERNS):
        return QUESTION_TYPE_NUMERIC
    if _matches_any(normalized, NARRATIVE_QUESTION_PATTERNS):
        return QUESTION_TYPE_NARRATIVE
    if any(cue in normalized for cue in PROCEDURAL_CUES):
        return QUESTION_TYPE_PROCEDURAL
    if _matches_any(normalized, LIST_QUESTION_PATTERNS):
        return QUESTION_TYPE_LIST
    if _definition_entity(question):
        return QUESTION_TYPE_DEFINITION
    return QUESTION_TYPE_GENERAL


def _matches_any(text, patterns):
    return any(re.search(pattern, text) for pattern in patterns)


def _contains_numeric_content(sentence):
    return bool(NUMERIC_CONTENT_PATTERN.search(sentence))


def _has_list_structure(sentence):
    normalized = sentence.strip()
    return any((
        ":" in normalized,
        ";" in normalized,
        normalized.count(",") >= 2,
        bool(NUMBERED_OR_BULLET_PATTERN.search(normalized)),
    ))


def _looks_like_heading(sentence):
    normalized = sentence.strip()
    if KNOWN_HEADING_PATTERN.search(normalized):
        return True

    title = normalized.rstrip(".:;\u2013\u2014-")
    words = title.split()
    return (
        normalized.endswith((':', '\u2013', '\u2014'))
        and 1 <= len(words) <= 8
        and _looks_like_title_text(title)
    )


def _looks_like_title_text(text):
    connectors = {"and", "or", "of", "the", "to", "for", "in"}
    words = re.findall(r"[A-Za-z][A-Za-z'-]*", text)
    significant_words = [word for word in words if word.lower() not in connectors]
    return bool(significant_words) and all(
        word[0].isupper() for word in significant_words
    )


def _looks_like_list_item(sentence):
    normalized = NUMBERED_OR_BULLET_PATTERN.sub("", sentence.strip())
    title = normalized.rstrip(".:;")
    return (
        bool(NUMBERED_OR_BULLET_PATTERN.search(sentence))
        or _has_list_structure(sentence)
        or (
            1 <= len(title.split()) <= 10
            and _looks_like_title_text(title)
        )
    )


def _list_context(sentences, index):
    start = index
    # Walk back through adjacent items so ranking the second or third item can
    # still recover the complete list and its colon-terminated introduction.
    while start > 0 and index - start < LIST_CONTEXT_SENTENCES - 1:
        previous = sentences[start - 1]
        if _has_list_structure(previous):
            start -= 1
            break
        if not _looks_like_list_item(previous):
            break
        start -= 1

    selected = [sentences[start]]
    for sentence in sentences[start + 1:start + LIST_CONTEXT_SENTENCES]:
        if not _looks_like_list_item(sentence):
            break
        selected.append(sentence)

    return " ".join(selected)


def _narrative_context(sentences, index):
    start = max(index - NARRATIVE_SENTENCES_BEFORE, 0)
    selected = list(sentences[start:index + 1])
    for sentence in sentences[index + 1:index + NARRATIVE_SENTENCES_AFTER + 1]:
        if _looks_like_heading(sentence):
            break
        selected.append(sentence)

    return " ".join(selected)


def _log_retrieval_debug(question, ranked_chunks):
    if not RETRIEVAL_DEBUG_ENABLED:
        return

    lines = [f"Question:\n{question}", "Top retrieved chunks:"]
    for chunk, score in ranked_chunks:
        lines.append(
            f"Chunk {chunk.chunk_id} Score {score:.4f}\n{chunk.text}"
        )
    print("\n\n".join(lines))


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
