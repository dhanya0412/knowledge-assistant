from bson import ObjectId
from pymongo.errors import PyMongoError

import app.database as database
from app.services.retrieval import Chunk, rank_chunks


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

    ranked_chunks = _rank_chunks(normalized_query, documents, normalized_limit)
    ranked_document_ids = {
        ObjectId(chunk.document_id)
        for chunk, _score in ranked_chunks
        if ObjectId.is_valid(chunk.document_id)
    }
    ranked_documents = [
        document
        for document in documents
        if document["_id"] in ranked_document_ids
    ]
    uploaders = _fetch_uploaders(ranked_documents)
    documents_by_id = {
        str(document["_id"]): document
        for document in documents
    }

    return {
        "query": normalized_query,
        "count": len(ranked_chunks),
        "success": True,
        "data": [
            _chunk_result_to_data(chunk, score)
            for chunk, score in ranked_chunks
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
    try:
        return list(database.db.documents.find(
            {
                "processed": True,
                "$or": [
                    {"status": "processed"},
                    {"status": {"$exists": False}},
                ],
                "text_content": {"$exists": True, "$ne": ""},
            },
            {
                "title": 1,
                "filename": 1,
                "original_filename": 1,
                "keywords": 1,
                "uploaded_by": 1,
                "uploaded_at": 1,
                "text_content": 1,
                "chunks": 1,
            },
        ))
    except PyMongoError as exc:
        raise SearchError(
            "documents could not be loaded",
            status_code=500,
        ) from exc


def _rank_chunks(query, documents, limit):
    try:
        return rank_chunks(query, _chunks_from_stored_documents(documents), limit)
    except RuntimeError as exc:
        message = str(exc)
        status_code = 500
        if message not in {"search failed", "search service unavailable"}:
            message = "search failed"
        raise SearchError(message, status_code=status_code) from exc


def _chunks_from_stored_documents(documents):
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


def _fetch_uploaders(ranked_documents):
    uploader_ids = {
        document.get("uploaded_by")
        for document in ranked_documents
        if isinstance(document.get("uploaded_by"), ObjectId)
    }
    if not uploader_ids:
        return {}

    try:
        users = database.db.users.find(
            {"_id": {"$in": list(uploader_ids)}},
            {"name": 1, "email": 1},
        )
    except PyMongoError as exc:
        raise SearchError(
            "users could not be loaded",
            status_code=500,
        ) from exc

    return {
        user["_id"]: user.get("name") or user.get("email")
        for user in users
    }


def _result_to_dict(document, chunk, score, uploaders):
    if not document:
        return _chunk_result_to_data(chunk, score)

    uploaded_by = document.get("uploaded_by")
    uploaded_at = document.get("uploaded_at")

    return {
        "id": str(document["_id"]),
        "document_id": str(document["_id"]),
        "title": document.get("title", ""),
        "filename": chunk.filename,
        "matched_chunk": chunk.text,
        "chunk_id": chunk.chunk_id,
        "keywords": document.get("keywords", []),
        "uploaded_by": str(uploaded_by),
        "uploaded_by_name": uploaders.get(uploaded_by),
        "uploaded_at": uploaded_at.isoformat() if uploaded_at else None,
        "score": round(score, 4),
        "relevance_score": round(score, 4),
    }


def _chunk_result_to_data(chunk, score):
    return {
        "document_id": chunk.document_id,
        "filename": chunk.filename,
        "matched_chunk": chunk.text,
        "chunk_id": chunk.chunk_id,
        "relevance_score": round(score, 4),
    }


def _empty_response(query):
    return {
        "query": query,
        "count": 0,
        "success": True,
        "data": [],
    }
