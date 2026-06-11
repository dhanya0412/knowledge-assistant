from flask import Blueprint, g, jsonify, request

from app.middleware.auth_middleware import token_required
from app.services.document_service import (
    DocumentError,
    delete_document,
    get_document,
    list_documents,
    upload_document,
)


documents_bp = Blueprint("documents", __name__)


@documents_bp.route("/upload", methods=["POST"])
@token_required
def upload():
    try:
        document = upload_document(
            user_id=g.user_id,
            file=request.files.get("file"),
            title=request.form.get("title"),
            tags=request.form.get("tags"),
        )
    except DocumentError as exc:
        return jsonify({"error": exc.message}), exc.status_code

    return jsonify({
        "message": "document uploaded successfully",
        "document": document,
    }), 201


@documents_bp.route("", methods=["GET"])
@token_required
def list_user_documents():
    try:
        documents = list_documents(g.user_id)
    except DocumentError as exc:
        return jsonify({"error": exc.message}), exc.status_code

    return jsonify({"documents": documents}), 200


@documents_bp.route("/<document_id>", methods=["GET"])
@token_required
def get_user_document(document_id):
    try:
        document = get_document(g.user_id, document_id)
    except DocumentError as exc:
        return jsonify({"error": exc.message}), exc.status_code

    return jsonify({"document": document}), 200


@documents_bp.route("/<document_id>", methods=["DELETE"])
@token_required
def delete_user_document(document_id):
    try:
        result = delete_document(g.user_id, document_id)
    except DocumentError as exc:
        return jsonify({"error": exc.message}), exc.status_code

    return jsonify(result), 200
