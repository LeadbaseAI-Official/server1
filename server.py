from flask import Flask, request, jsonify
import sqlite3, base64, os
from flask_cors import CORS
from github import Github

# -------------------- GitHub Config --------------------
GITHUB_TOKEN = os.getenv("GH_TOKEN")  # GitHub Actions secret or env var
REPO_NAME = "LeadbaseAI-Official/server1"
DB_FILE = "users.db"
BRANCH = "main"
print('configuration succesful')

# -------------------- GitHub Sync --------------------
def upload_db_to_github():
    try:
        g = Github(GITHUB_TOKEN)
        repo = g.get_repo(REPO_NAME)
        print('github cinfig succesful')
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

# -------------------- App Init --------------------
app = Flask(__name__)
CORS(app)

# Open DB connections
conn_users = sqlite3.connect("users.db", check_same_thread=False)
cursor_users = conn_users.cursor()
conn_data = sqlite3.connect("data.db", check_same_thread=False)
cursor_data = conn_data.cursor()

@app.route("/check-user", methods=["POST"])
def check_user():
    try:
        data = request.get_json()
        print('data get succesfull')
        email = data.get("email")
        ip = data.get("ip")

        if not email or not ip:
            return jsonify({"error": "Email and IP are required"}), 400

        cursor_users.execute("""
            SELECT email, ip, name, phone, daily_limit, extra_limit, affiliate
            FROM Users
            WHERE email = ? AND ip = ?
        """, (email, ip))
        print('data submitted')
        user = cursor_users.fetchone()
        print('db connection scf')

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
        print('done')
        ip_exists = cursor_users.fetchone()

        return jsonify({
            "emailExists": False,
            "ipExists": bool(ip_exists)
        })
    except Exception as e:
        print("Check User Error:", e)
        return jsonify({"error": str(e)}), 500

@app.route("/add-user", methods=["POST"])
def add_user():
    try:
        data = request.get_json()
        print('data get succesul')
        required_fields = ["email", "ip", "name", "phone", "question", "affiliate"]
        if not all(field in data for field in required_fields):
            return jsonify({"error": "Missing required fields"}), 400

        email = data["email"]
        ip = data["ip"]
        name = data["name"]
        phone = data["phone"]
        question = data["question"]
        affiliate = data["affiliate"]
        daily_limit = 100
        extra_limit = 0
        ref_source = data.get("ref_source")
        print('data mappend succesuful')

        with conn_users:
            cursor_users.execute("""
                INSERT OR IGNORE INTO Users (email, ip, name, phone, question, affiliate, daily_limit, extra_limit)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (email, ip, name, phone, question, affiliate, daily_limit, extra_limit))
            print('db connect scf')

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
        print('committed')
        upload_db_to_github()
        return jsonify({"status": "ok"})

    except Exception as e:
        print("Add User Error:", e)
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

        ip_without_dots = user[0].replace('.', '')
        link = f"https://leadbaseai.in?referal={ip_without_dots}"
        return jsonify({"status": "ok", "affiliate_link": link})
    except Exception as e:
        print("Affiliate Link Error:", e)
        return jsonify({"error": str(e)}), 500

@app.route("/data", methods=["GET"])
def get_data():
    try:
        page = int(request.args.get("page", 1))
        country = request.args.get("country", "India")
        per_page = 10

        if country not in ["India", "USA", "UK", "Australia", "UAE", "Canada"]:
            return jsonify({"error": "Invalid country"}), 400

        cursor_data.execute(f"SELECT COUNT(*) FROM {country}")
        total_rows = cursor_data.fetchone()[0]

        start_idx = max(total_rows - (page * per_page), 0)
        cursor_data.execute(f"""
            SELECT * FROM {country} 
            ORDER BY id DESC 
            LIMIT {per_page} OFFSET {start_idx}
        """)
        rows = cursor_data.fetchall()

        return jsonify({
            "page": page,
            "country": country,
            "data": rows,
            "has_more": start_idx > 0,
            "total": total_rows
        })
    except Exception as e:
        print("Data Fetch Error:", e)
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(port=5000)
