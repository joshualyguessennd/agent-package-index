from flask import Flask, jsonify
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker

from app.api.example import bp as example_bp
from app.api.packages import bp as packages_bp
from app.config import Config


def create_app(config: type | None = None) -> Flask:
    app = Flask(__name__)

    cfg = config or Config
    app.config["SECRET_KEY"] = cfg.SECRET_KEY
    app.config["DATABASE_URL"] = cfg.DATABASE_URL

    # SQLAlchemy setup (no Flask-SQLAlchemy)
    engine = create_engine(cfg.DATABASE_URL, echo=getattr(cfg, "SQLALCHEMY_ECHO", False))
    session_factory = sessionmaker(bind=engine)
    db_session = scoped_session(session_factory)

    app.config["db_session"] = db_session
    app.config["engine"] = engine

    @app.teardown_appcontext
    def shutdown_session(exception: BaseException | None = None) -> None:
        db_session.remove()

    # Health check
    @app.route("/health")
    def health():
        return jsonify(status="ok")

    # Register blueprints
    app.register_blueprint(example_bp, url_prefix="/api/examples")
    app.register_blueprint(packages_bp, url_prefix="/api/packages")

    return app
