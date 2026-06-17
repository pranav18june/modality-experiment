import os
from flask import Flask
from .models import init_db


def create_app():
    app = Flask(__name__)

    # ── Security: refuse to start without an explicit SECRET_KEY ────────────
    secret_key = os.environ.get("SECRET_KEY")
    if not secret_key:
        raise RuntimeError(
            "SECRET_KEY environment variable is not set. "
            "Generate one with: python3 -c \"import secrets; print(secrets.token_hex(32))\""
        )
    app.secret_key = secret_key
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

    # ── Initialise MongoDB indexes (no-op if already exist) ─────────────────
    with app.app_context():
        init_db()

    from .routes import bp
    app.register_blueprint(bp)

    return app
