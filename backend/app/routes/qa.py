from flask import Blueprint, jsonify, request

from app.middleware.auth_middleware import token_required
from app.services.qa_service import QAError, answer_question


qa_bp = Blueprint("qa", __name__)


@qa_bp.route("", methods=["POST"])
@token_required
def ask():
    payload = request.get_json(silent=True) or {}

    try:
        answer = answer_question(payload.get("question"))
    except QAError as exc:
        return jsonify({"error": exc.message}), exc.status_code

    return jsonify({
        "success": True,
        "data": answer,
    }), 200
