import os
from datetime import datetime, timezone

from bson import ObjectId


ALLOWED_EXTENSIONS = {"pdf", "docx", "txt"}


def parse_tags(tags):
    if not tags:
        return []

    return [
        tag.strip()
        for tag in str(tags).split(",")
        if tag.strip()
    ]


def get_file_extension(filename):
    return os.path.splitext(filename)[1].lower().lstrip(".")


def validate_document_upload(file):
    errors = []

    if file is None:
        errors.append("file is required")
        return errors

    if not file.filename:
        errors.append("filename is required")
        return errors

    extension = get_file_extension(file.filename)
    if extension not in ALLOWED_EXTENSIONS:
        errors.append("file type is not allowed")

    return errors


def create_document_document(
    *,
    title,
    original_filename,
    filename,
    filepath,
    uploaded_by,
    file_size,
    content_type,
    tags=None,
):
    return {
        "title": title,
        "original_filename": original_filename,
        "filename": filename,
        "filepath": filepath,
        "uploaded_by": ObjectId(uploaded_by),
        "file_size": file_size,
        "content_type": content_type,
        "uploaded_at": datetime.now(timezone.utc),
        "tags": parse_tags(tags),
        "text_content": "",
        "keywords": [],
        "summary": "",
        "processed": False,
    }


def document_to_dict(document, include_filepath=True, include_content=True):
    result = {
        "id": str(document["_id"]),
        "title": document["title"],
        "original_filename": document["original_filename"],
        "filename": document["filename"],
        "uploaded_by": str(document["uploaded_by"]),
        "file_size": document["file_size"],
        "content_type": document["content_type"],
        "uploaded_at": document["uploaded_at"].isoformat(),
        "tags": document.get("tags", []),
        "keywords": document.get("keywords", []),
        "summary": document.get("summary", ""),
        "processed": document.get("processed", False),
    }

    if include_filepath:
        result["filepath"] = document["filepath"]

    if include_content:
        result["text_content"] = document.get("text_content", "")

    return result
