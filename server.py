from flask import Flask, request, jsonify
import sqlite3, base64, os
from flask_cors import CORS
from github import Github

# -------------------- GitHub Config --------------------
GITHUB_TOKEN = os.getenv("GH_TOKEN")  # Store as env or GitHub Actions secret
REPO_NAME = "LeadbaseAI-Official/server1"
DB_FILE = "users.db"
BRANCH = "main"

# -------------------- GitHub Sync - Download DB --------------------
def download_db_from_github():
    try:
        g = Github(GITHUB_TOKEN)
        repo = g.get_repo(REPO_NAME)
        contents = repo.get_contents(DB_FILE, ref=BRANCH)
        with open(DB_FILE, "wb") as f:
            f.write(base64.b64decode(contents.content))
        print("✅ users.db downloaded from GitHub.")
    except Exception as e:
        print("⚠️ Could not download users.db:", e)

# -------------------- GitHub Sync - Upload DB --------------------
def upload_db_to_github():
    try:
        g = Github(GITHUB_TOKEN)
        repo = g.get_repo(REPO_NAME)
        contents = repo.get_contents(DB_FILE, ref=BRANCH)
        with open(DB_FILE, "rb") as f:
            new_content = f.read()
        repo.update_file(
            path=DB_FILE,
            message="Update users.db via /track-referral",
            content=new_content,
            sha=contents.sha,
            branch=BRANCH
        )
        print("✅ users.db pushed to GitHub.")
    except Exception as e:
        print("⚠️ Could not push users.db:", e)

# -------------------- Flask App Init --------------------
# Pull DB from GitHub on startup
download_db_from_github()

app = Flask(__name__)

# ✅ Dual-origin CORS: allow localhost and production
CORS(app, resources={
    r"/*": {
        "origins": [
            "https://leadbaseai.in",      # 🔒 Production domain
            "http://localhost:5173"       # 🛠️ Local development
        ]
    }
}, supports_credentials=True)

# ✅ Optional: handle preflight manually (for some edge deployments)
@app.before_request
def handle_options():
    if request.method == "OPTIONS":
        return '', 200

# Open DB connection to users.db
conn = sqlite3.connect("users.db", check_same_thread=False)
cursor = conn.cursor()

# Ensure Users table exists
cursor.execute("""
CREATE TABLE IF NOT EXISTS Users (
    email TEXT NOT NULL,
    ip TEXT NOT NULL,
    name TEXT,
    phone TEXT,
    question TEXT,
    affiliate INTEGER DEFAULT 0,
    daily_limit INTEGER DEFAULT 100,
    extra_limit INTEGER DEFAULT 0,
    PRIMARY KEY (email, ip)
)
""")
conn.commit()

# -------------------- Routes --------------------

@app.route("/track-referral", methods=["POST"])
def track_referral():
    data = request.get_json()
    referal_id = data.get("referal_id")
    if not referal_id:
        return jsonify({"error": "No referal_id provided"}), 400

    try:
        # Update affiliate and extra_limit
        cursor.execute("""
            UPDATE Users
            SET affiliate = COALESCE(affiliate, 0) + 1,
                extra_limit = COALESCE(extra_limit, 0) + 30
            WHERE REPLACE(ip, '.', '') = ?
        """, (referal_id,))
        conn.commit()

        # Push updated DB to GitHub
        upload_db_to_github()

        return jsonify({"status": "ok", "referal_id": referal_id})
    except Exception as e:
        print("Referral Error:", e)
        return jsonify({"error": str(e)}), 500

@app.route("/data", methods=["GET"])
def get_data():
    try:
        page = int(request.args.get("page", 1))
        per_page = 10

        cursor.execute("SELECT COUNT(*) FROM Users")
        total_rows = cursor.fetchone()[0]

        start_idx = max(total_rows - (page * per_page), 0)
        limit = per_page

        cursor.execute("""
            SELECT * FROM Users 
            ORDER BY rowid DESC 
            LIMIT ? OFFSET ?
        """, (limit, start_idx))
        rows = cursor.fetchall()

        return jsonify({
            "page": page,
            "data": rows,
            "has_more": start_idx > 0,
            "total": total_rows
        })
    except Exception as e:
        print("Error:", e)
        return jsonify({"error": str(e)}), 500

# -------------------- Run Server --------------------
if __name__ == "__main__":
    app.run(port=5000)
