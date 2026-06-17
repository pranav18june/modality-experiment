import os
from flask import Flask
from .models import init_db
from pymongo.errors import ServerSelectionTimeoutError


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

    @app.errorhandler(ServerSelectionTimeoutError)
    def handle_mongo_timeout(error):
        return (
            "<h2>Database Connection Timeout</h2>"
            "<p>The application could not connect to MongoDB Atlas.</p>"
            "<p><strong>If you are on Vercel:</strong> You MUST go to your MongoDB Atlas Dashboard > Security > Network Access and click <em>Add IP Address -> Allow Access From Anywhere (0.0.0.0/0)</em>. Vercel's IP addresses change dynamically and will be blocked otherwise.</p>", 
            500
        )

    return app
