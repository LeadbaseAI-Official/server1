from flask import Flask, request, jsonify
import sqlite3
from flask_cors import CORS

app = Flask(__name__)
CORS(app)  # Allow frontend access

# Open DB connection (assumes `data.db` exists in same folder)
conn = sqlite3.connect("data.db", check_same_thread=False)
cursor = conn.cursor()

@app.route("/data", methods=["GET"])
def get_data():
    try:
        page = int(request.args.get("page", 1))
        per_page = 10

        # Get total number of rows
        cursor.execute("SELECT COUNT(*) FROM users")
        total_rows = cursor.fetchone()[0]

        # Calculate OFFSET from bottom (latest rows)
        start_idx = max(total_rows - (page * per_page), 0)
        limit = per_page

        # Fetch last N rows (ordered descending)
        cursor.execute(f"""
            SELECT * FROM users 
            ORDER BY id DESC 
            LIMIT {limit} OFFSET {start_idx}
        """)
        rows = cursor.fetchall()

        return jsonify({
            "page": page,
            "data": rows,
            "has_more": start_idx > 0,
            "total": total_rows
        })

    except Exception as e:
        print("Error:", e)  # 🔥 Add this line
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(port=5000)
