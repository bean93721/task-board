import os
import sys
import json
import sqlite3
import uuid
from datetime import datetime
from flask import Flask, request, jsonify, render_template, g

# Determine paths for Vercel Serverless vs local dev
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(BASE_DIR)
DB_DIR = PARENT_DIR if os.access(PARENT_DIR, os.W_OK) else "/tmp"
DATABASE = os.path.join(DB_DIR, "tasks.db")
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")

app = Flask(__name__, template_folder=TEMPLATE_DIR)


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL")
        g.db.execute("PRAGMA foreign_keys=ON")
    return g.db


def init_db():
    with app.app_context():
        db = get_db()
        db.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                deadline TEXT NOT NULL,
                priority TEXT NOT NULL DEFAULT 'auto',
                done INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
        """)
        db.commit()


@app.teardown_appcontext
def close_db(exception):
    db = g.pop("db", None)
    if db is not None:
        db.close()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/tasks", methods=["GET"])
def get_tasks():
    db = get_db()
    rows = db.execute("SELECT * FROM tasks ORDER BY created_at DESC").fetchall()
    tasks = []
    for row in rows:
        tasks.append({
            "id": row["id"],
            "title": row["title"],
            "deadline": row["deadline"],
            "priority": row["priority"],
            "done": bool(row["done"]),
            "createdAt": row["created_at"],
        })
    return jsonify(tasks)


@app.route("/api/tasks", methods=["POST"])
def add_task():
    data = request.get_json()
    if not data or not data.get("title") or not data.get("deadline"):
        return jsonify({"error": "标题和截止日期不能为空"}), 400

    task = {
        "id": str(uuid.uuid4()),
        "title": data["title"].strip(),
        "deadline": data["deadline"],
        "priority": data.get("priority", "auto"),
        "done": False,
        "createdAt": datetime.now().isoformat(),
    }

    db = get_db()
    db.execute(
        "INSERT INTO tasks (id, title, deadline, priority, done, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (task["id"], task["title"], task["deadline"], task["priority"], int(task["done"]), task["createdAt"]),
    )
    db.commit()
    return jsonify(task), 201


@app.route("/api/tasks/<task_id>", methods=["PATCH"])
def update_task(task_id):
    db = get_db()
    row = db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if not row:
        return jsonify({"error": "任务不存在"}), 404

    data = request.get_json()
    fields = []
    values = []

    if "title" in data:
        fields.append("title = ?")
        values.append(data["title"].strip())
    if "deadline" in data:
        fields.append("deadline = ?")
        values.append(data["deadline"])
    if "priority" in data:
        fields.append("priority = ?")
        values.append(data["priority"])
    if "done" in data:
        fields.append("done = ?")
        values.append(int(data["done"]))

    if fields:
        values.append(task_id)
        db.execute(f"UPDATE tasks SET {', '.join(fields)} WHERE id = ?", values)
        db.commit()

    row = db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    return jsonify({
        "id": row["id"],
        "title": row["title"],
        "deadline": row["deadline"],
        "priority": row["priority"],
        "done": bool(row["done"]),
        "createdAt": row["created_at"],
    })


@app.route("/api/tasks/<task_id>", methods=["DELETE"])
def delete_task(task_id):
    db = get_db()
    db.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    db.commit()
    return jsonify({"ok": True})


@app.route("/api/tasks/import", methods=["POST"])
def import_tasks():
    data = request.get_json()
    if not isinstance(data, list):
        return jsonify({"error": "格式错误，需要 JSON 数组"}), 400

    replace = request.args.get("mode") == "replace"
    db = get_db()
    if replace:
        db.execute("DELETE FROM tasks")

    count = 0
    for item in data:
        if not item.get("title") or not item.get("deadline"):
            continue
        task_id = item.get("id", str(uuid.uuid4()))
        db.execute(
            "INSERT OR IGNORE INTO tasks (id, title, deadline, priority, done, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (task_id, item["title"].strip(), item["deadline"],
             item.get("priority", "auto"), int(item.get("done", False)),
             item.get("createdAt", datetime.now().isoformat())),
        )
        count += 1
    db.commit()
    return jsonify({"ok": True, "count": count})


@app.route("/api/tasks/export", methods=["GET"])
def export_tasks():
    db = get_db()
    rows = db.execute("SELECT * FROM tasks ORDER BY created_at DESC").fetchall()
    tasks = []
    for row in rows:
        tasks.append({
            "id": row["id"],
            "title": row["title"],
            "deadline": row["deadline"],
            "priority": row["priority"],
            "done": bool(row["done"]),
            "createdAt": row["created_at"],
        })
    return jsonify(tasks)


# Vercel requires WSGI app named "app"
# This is already our Flask app instance

init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
