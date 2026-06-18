from flask import Blueprint, jsonify, request

from app.middleware.auth_middleware import token_required
from app.services.search_service import SearchError, search_documents


search_bp = Blueprint("search", __name__)


@search_bp.route("", methods=["GET"])
@token_required
def search():
    try:
        results = search_documents(
            query=request.args.get("q"),
            limit=request.args.get("limit"),
        )
    except SearchError as exc:
        return jsonify({"error": exc.message}), exc.status_code

    return jsonify(results), 200
