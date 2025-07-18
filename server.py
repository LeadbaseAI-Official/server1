from flask import Flask, request, jsonify
import sqlite3, os, subprocess
from flask_cors import CORS
import base64
from github import Github

DB_FILE = "users.db"
GITHUB_TOKEN = os.getenv("GH_TOKEN")
REPO_NAME = os.getenv("REPO_NAME", "LeadbaseAI-Official/server1")  # Default to server1
BRANCH = "main"
SERVER_PREFIX = os.getenv("SERVER_PREFIX", "/server1")  # Default to /server1

app = Flask(__name__)
CORS(app)

# -------------------- GitHub Pull --------------------
def download_db_from_github():
    try:
        g = Github(GITHUB_TOKEN)
        repo = g.get_repo(REPO_NAME)
        contents = repo.get_contents(DB_FILE, ref=BRANCH)
        with open(DB_FILE, "wb") as f:
            f.write(base64.b64decode(contents.content))
        print(f"✅ Pulled {DB_FILE} from GitHub")
    except Exception as e:
        print(f"⚠️ GitHub download failed: {e}")

# -------------------- Git Push CLI --------------------
def upload_db_with_git():
    try:
        subprocess.run(["git", "config", "--global", "user.email", "action@github.com"], check=True)
        subprocess.run(["git", "config", "--global", "user.name", "GitHub Action"], check=True)
        subprocess.run(["git", "add", DB_FILE], check=True)
        subprocess.run(["git", "commit", "-m", f"Update {DB_FILE} from Flask server"], check=True)
        subprocess.run(["git", "push"], check=True)
        print(f"✅ {DB_FILE} pushed via Git CLI")
    except subprocess.CalledProcessError as e:
        print(f"❌ Git push failed: {e}")

# Pull latest DB before starting
download_db_from_github()

# -------------------- DB Connections --------------------
conn_users = sqlite3.connect(DB_FILE, check_same_thread=False)
cursor_users = conn_users.cursor()
conn_leads = sqlite3.connect("Leads.db", check_same_thread=False)
cursor_leads = conn_leads.cursor()

# -------------------- Routes --------------------
@app.before_request
def strip_prefix():
    if request.path.startswith(SERVER_PREFIX):
        request.environ["PATH_INFO"] = request.path[len(SERVER_PREFIX):] or "/"

@app.route("/add-user", methods=["POST"])
def add_user():
    try:
        data = request.get_json()
        required = ["email", "ip", "name", "phone", "question", "affiliate"]
        if not all(field in data for field in required):
            return jsonify({"error": "Missing required fields"}), 400

        email = data["email"]
        ip = data["ip"]
        name = data["name"]
        phone = data["phone"]
        question = data["question"]
        affiliate = data["affiliate"]
        ref_source = data.get("ref_source")
        daily_limit = 100
        extra_limit = 0

        with conn_users:
            cursor_users.execute("""
                INSERT OR IGNORE INTO Users (email, ip, name, phone, question, affiliate, daily_limit, extra_limit)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (email, ip, name, phone, question, affiliate, daily_limit, extra_limit))

            if cursor_users.rowcount == 0:
                return jsonify({"error": "User already exists"}), 400

            if ref_source:
                cursor_users.execute("""
                    UPDATE Users
                    SET affiliate = COALESCE(affiliate, 0) + 1,
                        extra_limit = COALESCE(extra_limit, 0) + 30
                    WHERE REPLACE(ip, '.', '') = ?
                """, (ref_source,))

        conn_users.commit()
        upload_db_with_git()
        return jsonify({"status": "ok"})

    except Exception as e:
        print("❌ Add User Error:", e)
        return jsonify({"error": str(e)}), 500

@app.route("/check-user", methods=["POST"])
def check_user():
    try:
        data = request.get_json()
        email = data.get("email")
        ip = data.get("ip")

        if not email or not ip:
            return jsonify({"error": "Email and IP are required"}), 400

        cursor_users.execute("""
            SELECT email, ip, name, phone, daily_limit, extra_limit, affiliate
            FROM Users WHERE email = ? AND ip = ?
        """, (email, ip))
        user = cursor_users.fetchone()

        if user:
            return jsonify({
                "emailExists": True,
                "ipExists": True,
                "user": {
                    "email": user[0],
                    "ip": user[1],
                    "name": user[2],
                    "phone": user[3],
                    "daily_limit": user[4],
                    "extra_limit": user[5],
                    "affiliate": user[6]
                }
            })

        cursor_users.execute("SELECT 1 FROM Users WHERE ip = ?", (ip,))
        ip_exists = cursor_users.fetchone()

        return jsonify({
            "emailExists": False,
            "ipExists": bool(ip_exists)
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/get-affiliate-link", methods=["POST"])
def get_affiliate_link():
    try:
        data = request.get_json()
        email = data.get("email")
        ip = data.get("ip")

        if not email or not ip:
            return jsonify({"error": "Email and IP are required"}), 400

        cursor_users.execute("SELECT ip FROM Users WHERE email = ? AND ip = ?", (email, ip))
        user = cursor_users.fetchone()

        if not user:
            return jsonify({"error": "User not found"}), 404

        ip_clean = user[0].replace('.', '')
        return jsonify({"status": "ok", "affiliate_link": f"https://leadbaseai.in?referal={ip_clean}"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/data", methods=["GET"])
def get_data():
    try:
        page = int(request.args.get("page", 1))
        country = request.args.get("country", "").replace(" ", "_")
        per_page = 10
        offset = (page - 1) * per_page

        count_query = f"SELECT COUNT(*) FROM '{country}'"
        cursor_leads.execute(count_query)
        total = cursor_leads.fetchone()[0]

        query = f"SELECT * FROM '{country}' ORDER BY ROWID DESC LIMIT ? OFFSET ?"
        cursor_leads.execute(query, (per_page, offset))
        rows = cursor_leads.fetchall()

        cols = [desc[0] for desc in cursor_leads.description]

        return jsonify({
            "data": rows,
            "columns": cols,
            "total": total
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# -------------------- Run --------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
