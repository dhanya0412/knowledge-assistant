from flask import Blueprint, jsonify
import app.database as database

health_bp = Blueprint(
    "health",
    __name__
)


@health_bp.route("/health", methods=["GET"])
def health():

    try:
        database.client.admin.command("ping")

        return jsonify({
            "status": "healthy",
            "database": "connected"
        }), 200

    except Exception as e:
        return jsonify({
            "status": "unhealthy",
            "database": "disconnected",
            "error": str(e)
        }), 500