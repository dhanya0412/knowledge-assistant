import os
from uuid import uuid4

from bson import ObjectId
from bson.errors import InvalidId
from flask import current_app
from werkzeug.utils import secure_filename

import app.database as database
from app.models.document import (
    create_document_document,
    document_to_dict,
    get_file_extension,
    parse_tags,
    validate_document_upload,
)


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
    file.save(filepath)

    document_title = str(title).strip() if title and str(title).strip() else os.path.splitext(original_filename)[0]

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

    result = database.db.documents.insert_one(document)
    document["_id"] = result.inserted_id
    return document_to_dict(document)


def list_documents(user_id):
    documents = database.db.documents.find(
        {"uploaded_by": ObjectId(user_id)}
    ).sort("uploaded_at", -1)

    return [
        document_to_dict(
            document,
            include_filepath=False,
            include_content=False,
        )
        for document in documents
    ]


def get_document(user_id, document_id):
    document = database.db.documents.find_one({
        "_id": _object_id(document_id),
        "uploaded_by": ObjectId(user_id),
    })

    if not document:
        raise DocumentError("document not found", status_code=404)

    return document_to_dict(document)


def delete_document(user_id, document_id):
    document = database.db.documents.find_one({
        "_id": _object_id(document_id),
        "uploaded_by": ObjectId(user_id),
    })

    if not document:
        raise DocumentError("document not found", status_code=404)

    filepath = document.get("filepath")
    if filepath and os.path.exists(filepath):
        os.remove(filepath)

    database.db.documents.delete_one({
        "_id": document["_id"],
        "uploaded_by": ObjectId(user_id),
    })

    return {"message": "document deleted successfully"}
