from flask import Blueprint, current_app, jsonify, request
from sqlalchemy import text

bp = Blueprint("examples", __name__)

LIST_SQL = text(
    "SELECT id, name, description, is_active, created_at"
    " FROM example ORDER BY id"
)

INSERT_SQL = text(
    "INSERT INTO example (name, description)"
    " VALUES (:name, :description)"
    " RETURNING id, name, description, is_active, created_at"
)


@bp.route("", methods=["GET"])
def list_examples():
    db = current_app.config["db_session"]
    rows = db.execute(LIST_SQL).fetchall()
    results = [
        {
            "id": r.id,
            "name": r.name,
            "description": r.description,
            "is_active": r.is_active,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]
    return jsonify(results)


@bp.route("", methods=["POST"])
def create_example():
    db = current_app.config["db_session"]
    data = request.get_json(force=True)
    name = data.get("name")
    description = data.get("description")
    if not name:
        return jsonify(error="name is required"), 400
    row = db.execute(
        INSERT_SQL,
        {"name": name, "description": description},
    ).fetchone()
    db.commit()
    return jsonify(
        id=row.id,
        name=row.name,
        description=row.description,
        is_active=row.is_active,
        created_at=row.created_at.isoformat() if row.created_at else None,
    ), 201
