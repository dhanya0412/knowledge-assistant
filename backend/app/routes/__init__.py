from app.routes.auth import auth_bp
from app.routes.documents import documents_bp
from app.routes.health import health_bp
from app.routes.search import search_bp


def register_routes(app):
    app.register_blueprint(health_bp, url_prefix="/api")
    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(documents_bp, url_prefix="/api/documents")
    app.register_blueprint(search_bp, url_prefix="/api/search")
