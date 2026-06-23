import os
from datetime import datetime, timezone
from uuid import uuid4

from bson import ObjectId
from bson.errors import InvalidId
from flask import current_app
from pymongo.errors import PyMongoError
from werkzeug.utils import secure_filename
import re

import app.database as database
from app.models.document import (
    create_document_document,
    document_to_dict,
    get_file_extension,
    validate_document_upload,
)
from app.services.keyword_extractor import extract_keywords
from app.services.parser import (
    EmptyDocumentError,
    MissingFileError,
    ParserError,
    UnsupportedFileTypeError,
    extract_text,
)
from app.services.preprocessor import clean_document_text
from app.services.preprocessor import sent_tokenize, preprocess_for_nlp
from app.services.retrieval import chunk_text
from app.services.summarizer import generate_summary


class DocumentError(Exception):
    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _upload_folder():
    configured_folder = current_app.config.get("UPLOAD_FOLDER")
    if configured_folder:
        return configured_folder

    return os.path.abspath(
        os.path.join(current_app.root_path, "..", "..", "uploads")
    )


def _object_id(value):
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        raise DocumentError("document not found", status_code=404)


def _file_size(file):
    position = file.stream.tell()
    file.stream.seek(0, os.SEEK_END)
    size = file.stream.tell()
    file.stream.seek(position)
    return size


def _stored_filename(original_filename):
    extension = get_file_extension(original_filename)
    return f"{uuid4().hex}.{extension}"


def _build_chunks(text_content):
    return [
        {
            "chunk_id": index,
            "text": chunk,
            "word_count": len(chunk.split()),
        }
        for index, chunk in enumerate(chunk_text(text_content), start=1)
    ]


def _process_document(filepath, original_filename):
    try:
        raw_text = extract_text(filepath, filename=original_filename)
        print("parser ok")
        # Only light, lossless document cleaning happens before storage —
        # text_content and chunks must preserve the original wording.
        text_content = clean_document_text(raw_text)
        print("clean ok")
        chunks = _build_chunks(text_content)
        print("chunks ok")
        sentences = sent_tokenize(text_content)
        print("sentences ok")
        keywords = extract_keywords(text_content, sentences=sentences)
        print("keywords ok")
        summary = generate_summary(text_content, sentences=sentences)
        print("summary ok")
        # NLP-only normalization (tokenize/lowercase/lemmatize) is used
        # solely to compute word_count; its output is never stored.
        word_count = len(re.findall(r"\b\w+\b", text_content))
    except EmptyDocumentError as exc:
        raise DocumentError("no extractable text found") from exc
    except UnsupportedFileTypeError as exc:
        raise DocumentError("file type is not supported") from exc
    except MissingFileError as exc:
        raise DocumentError(
            "uploaded file could not be processed",
            status_code=500,
        ) from exc
    except ValueError as exc:
        raise DocumentError("document could not be processed") from exc
    except RuntimeError as exc:
        raise DocumentError(
            "document processing service unavailable",
            status_code=500,
        ) from exc
    except ParserError as exc:
        raise DocumentError("document could not be processed") from exc

    return {
        "text_content": text_content,
        "chunks": chunks,
        "keywords": keywords,
        "summary": summary,
        "word_count": word_count,
        "status": "processed",
        "processed": True,
        "processed_at": datetime.now(timezone.utc),
    }


def upload_document(user_id, file, title=None, tags=None):
    errors = validate_document_upload(file)
    if errors:
        raise DocumentError(errors[0])

    original_filename = secure_filename(file.filename)
    stored_filename = _stored_filename(original_filename)
    upload_folder = _upload_folder()
    os.makedirs(upload_folder, exist_ok=True)

    filepath = os.path.join(upload_folder, stored_filename)
    file_size = _file_size(file)
    max_file_size = current_app.config.get("MAX_CONTENT_LENGTH")
    if max_file_size and file_size > max_file_size:
        raise DocumentError("file exceeds maximum allowed size", status_code=413)

    file.save(filepath)

    try:
        processed_fields = _process_document(filepath, original_filename)
    except DocumentError:
        if os.path.exists(filepath):
            os.remove(filepath)
        raise
    except Exception as exc:
        if os.path.exists(filepath):
            os.remove(filepath)
        raise DocumentError(
            "document could not be processed",
            status_code=500,
        ) from exc

    document_title = (
        str(title).strip()
        if title and str(title).strip()
        else os.path.splitext(original_filename)[0]
    )

    document = create_document_document(
        title=document_title,
        original_filename=original_filename,
        filename=stored_filename,
        filepath=filepath,
        uploaded_by=user_id,
        file_size=file_size,
        content_type=file.content_type,
        tags=tags,
    )
    document.update(processed_fields)

    try:
        result = database.db.documents.insert_one(document)
    except PyMongoError as exc:
        if os.path.exists(filepath):
            os.remove(filepath)
        raise DocumentError(
            "document could not be saved",
            status_code=500,
        ) from exc

    document["_id"] = result.inserted_id
    return document_to_dict(document)


def list_documents(user_id):
    try:
        documents = database.db.documents.find(
            {
                "uploaded_by": ObjectId(user_id),
                "status": "processed",
            }
        ).sort("uploaded_at", -1)
    except PyMongoError as exc:
        raise DocumentError(
            "documents could not be loaded",
            status_code=500,
        ) from exc

    return [
        document_to_dict(
            document,
            include_filepath=False,
            include_content=False,
        )
        for document in documents
    ]


def get_document(user_id, document_id):
    try:
        document = database.db.documents.find_one({
            "_id": _object_id(document_id),
            "uploaded_by": ObjectId(user_id),
        })
    except PyMongoError as exc:
        raise DocumentError(
            "document could not be loaded",
            status_code=500,
        ) from exc

    if not document:
        raise DocumentError("document not found", status_code=404)

    return document_to_dict(document)


def get_document_summary(user_id, document_id):
    try:
        document = database.db.documents.find_one({
            "_id": _object_id(document_id),
            "processed": True,
        })
    except PyMongoError as exc:
        raise DocumentError(
            "document could not be loaded",
            status_code=500,
        ) from exc

    if not document:
        raise DocumentError("document not found", status_code=404)

    return {
        "id": str(document["_id"]),
        "summary": document.get("summary", ""),
        "keywords": document.get("keywords", []),
    }


def delete_document(user_id, document_id):
    try:
        document = database.db.documents.find_one({
            "_id": _object_id(document_id),
            "uploaded_by": ObjectId(user_id),
        })
    except PyMongoError as exc:
        raise DocumentError(
            "document could not be loaded",
            status_code=500,
        ) from exc

    if not document:
        raise DocumentError("document not found", status_code=404)

    filepath = document.get("filepath")
    if filepath and os.path.exists(filepath):
        os.remove(filepath)

    try:
        database.db.documents.delete_one({
            "_id": document["_id"],
            "uploaded_by": ObjectId(user_id),
        })
    except PyMongoError as exc:
        raise DocumentError(
            "document could not be deleted",
            status_code=500,
        ) from exc

    return {"message": "document deleted successfully"}