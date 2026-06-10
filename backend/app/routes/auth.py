from flask import Blueprint, jsonify, request
from flask_jwt_extended import create_access_token

from app.models.user import user_to_dict
from app.services.auth_service import AuthError, login_user, register_user
from app.middleware.auth_middleware import token_required

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/register", methods=["POST"])
def register():
    data = request.get_json(silent=True) or {}

    try:
        user = register_user(
            email=data.get("email"),
            password=data.get("password"),
            name=data.get("name"),
        )
    except AuthError as exc:
        return jsonify({"error": exc.message}), exc.status_code

    return jsonify({"message": "user registered successfully", "user": user}), 201


@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}

    try:
        user = login_user(
            email=data.get("email"),
            password=data.get("password"),
        )
    except AuthError as exc:
        return jsonify({"error": exc.message}), exc.status_code

    token = create_access_token(identity=str(user["_id"]))

    return jsonify({
        "token": token,
        "user": user_to_dict(user),
    }), 200

# TODO: Remove after JWT testing

# @auth_bp.route("/protected", methods=["GET"])
# @token_required
# def protected():
#     return jsonify({
#         "message": "authenticated"
#     }), 200