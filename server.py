from flask import Flask, request, jsonify
import sqlite3, base64, os
from flask_cors import CORS
from github import Github

# -------------------- GitHub Config --------------------
GITHUB_TOKEN = os.getenv("GH_TOKEN")
REPO_NAME = "LeadbaseAI-Official/server1"
DB_FILE = "users.db"
BRANCH = "main"

print("🔧 GitHub configuration loaded.")

# -------------------- GitHub Pull (Startup) --------------------
def download_db_from_github():
    try:
        g = Github(GITHUB_TOKEN)
        repo = g.get_repo(REPO_NAME)
        contents = repo.get_contents(DB_FILE, ref=BRANCH)
        with open(DB_FILE, "wb") as f:
            f.write(base64.b64decode(contents.content))
        print("✅ Pulled latest users.db from GitHub.")
    except Exception as e:
        print("⚠️ Failed to pull users.db:", e)

# -------------------- GitHub Push (Post-change) --------------------
def upload_db_to_github():
    try:
        g = Github(GITHUB_TOKEN)
        repo = g.get_repo(REPO_NAME)
        contents = repo.get_contents(DB_FILE, ref=BRANCH)
        with open(DB_FILE, "rb") as f:
            new_content = f.read()
        repo.update_file(
            path=DB_FILE,
            message="Update users.db via add-user or referral",
            content=new_content,
            sha=contents.sha,
            branch=BRANCH
        )
        print("✅ users.db pushed to GitHub.")
    except Exception as e:
        print("⚠️ GitHub push failed:", e)

# -------------------- Init --------------------
download_db_from_github()

app = Flask(__name__)
CORS(app)

conn_users = sqlite3.connect(DB_FILE, check_same_thread=False)
cursor_users = conn_users.cursor()

# -------------------- Routes --------------------
@app.route("/add-user", methods=["POST"])
def add_user():
    try:
        data = request.get_json()
        print("📩 Received data:", data)

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

            print("🧾 Insert rowcount:", cursor_users.rowcount)
            if cursor_users.rowcount == 0:
                return jsonify({"error": "User already exists"}), 400

            if ref_source:
                cursor_users.execute("""
                    UPDATE Users
                    SET affiliate = COALESCE(affiliate, 0) + 1,
                        extra_limit = COALESCE(extra_limit, 0) + 30
                    WHERE REPLACE(ip, '.', '') = ?
                """, (ref_source,))
                print(f"🔗 Referral applied for source IP: {ref_source}")

        conn_users.commit()
        print("💾 Committed changes. Pushing to GitHub...")
        upload_db_to_github()

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
        print("❌ Check User Error:", e)
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
        link = f"https://leadbaseai.in?referal={ip_clean}"
        return jsonify({"status": "ok", "affiliate_link": link})
    except Exception as e:
        print("❌ Affiliate Link Error:", e)
        return jsonify({"error": str(e)}), 500

# -------------------- Main --------------------
if __name__ == "__main__":
    app.run(port=5000)
