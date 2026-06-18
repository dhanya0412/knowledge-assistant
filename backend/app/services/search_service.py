from bson import ObjectId

import app.database as database


DEFAULT_LIMIT = 5
MAX_LIMIT = 20


class SearchError(Exception):
    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def search_documents(query, limit=DEFAULT_LIMIT):
    normalized_query = _normalize_query(query)
    normalized_limit = _normalize_limit(limit)
    documents = _fetch_searchable_documents()

    if not documents:
        return _empty_response(normalized_query)

    ranked_documents = _rank_documents(
        normalized_query,
        documents,
        normalized_limit,
    )
    uploaders = _fetch_uploaders(ranked_documents)

    return {
        "query": normalized_query,
        "count": len(ranked_documents),
        "results": [
            _result_to_dict(document, score, uploaders)
            for document, score in ranked_documents
        ],
    }


def _normalize_query(query):
    if query is None or not str(query).strip():
        raise SearchError("search query is required")

    return str(query).strip()


def _normalize_limit(limit):
    if limit is None or limit == "":
        return DEFAULT_LIMIT

    try:
        normalized_limit = int(limit)
    except (TypeError, ValueError):
        raise SearchError("limit must be a positive integer")

    if normalized_limit <= 0:
        raise SearchError("limit must be a positive integer")

    return min(normalized_limit, MAX_LIMIT)


def _fetch_searchable_documents():
    return list(database.db.documents.find(
        {
            "processed": True,
            "text_content": {"$exists": True, "$ne": ""},
        },
        {
            "title": 1,
            "keywords": 1,
            "uploaded_by": 1,
            "uploaded_at": 1,
            "text_content": 1,
        },
    ))


def _rank_documents(query, documents, limit):
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity
    except ImportError as exc:
        raise SearchError("search service unavailable", status_code=500) from exc

    search_texts = [_build_search_text(document) for document in documents]
    vectorizer = TfidfVectorizer(
        stop_words="english",
        ngram_range=(1, 2),
        lowercase=True,
    )

    try:
        document_matrix = vectorizer.fit_transform(search_texts)
        query_vector = vectorizer.transform([query])
    except ValueError as exc:
        if "empty vocabulary" in str(exc):
            return []
        raise SearchError("search failed", status_code=500) from exc

    scores = cosine_similarity(query_vector, document_matrix).flatten()
    ranked = sorted(
        zip(documents, scores),
        key=lambda item: (-item[1], str(item[0].get("_id"))),
    )

    return [
        (document, float(score))
        for document, score in ranked[:limit]
        if score > 0
    ]


def _build_search_text(document):
    title = document.get("title", "")
    keywords = " ".join(document.get("keywords", []))
    text_content = document.get("text_content", "")

    return " ".join([
        title,
        title,
        keywords,
        keywords,
        text_content,
    ])


def _fetch_uploaders(ranked_documents):
    uploader_ids = {
        document.get("uploaded_by")
        for document, _score in ranked_documents
        if isinstance(document.get("uploaded_by"), ObjectId)
    }
    if not uploader_ids:
        return {}

    users = database.db.users.find(
        {"_id": {"$in": list(uploader_ids)}},
        {"name": 1, "email": 1},
    )

    return {
        user["_id"]: user.get("name") or user.get("email")
        for user in users
    }


def _result_to_dict(document, score, uploaders):
    uploaded_by = document.get("uploaded_by")
    uploaded_at = document.get("uploaded_at")

    return {
        "id": str(document["_id"]),
        "title": document.get("title", ""),
        "keywords": document.get("keywords", []),
        "uploaded_by": str(uploaded_by),
        "uploaded_by_name": uploaders.get(uploaded_by),
        "uploaded_at": uploaded_at.isoformat() if uploaded_at else None,
        "score": round(score, 4),
    }


def _empty_response(query):
    return {
        "query": query,
        "count": 0,
        "results": [],
    }
