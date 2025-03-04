from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
    send_file,
    jsonify,
)
import requests
import csv
import os
import mysql.connector
import json
from dotenv import load_dotenv
import logging
from flask_caching import Cache
from mysql.connector import pooling

load_dotenv()

app = Flask(__name__)
app.secret_key = "frontend_secret_key"

# API URL
API_URL = "https://tokens-rho.vercel.app/"

TOKEN_CSV_PATH = (
    "C:/Users/HansOpoku/OneDrive - Margins Group/Desktop/tokenize/secureEnv/token.csv"
)

# Configure logging
logging.basicConfig(level=logging.DEBUG)

# Configure caching
cache = Cache(app, config={"CACHE_TYPE": "simple"})

# Configure database connection pooling
dbconfig = {
    "host": os.getenv("MYSQL_HOST"),
    "user": os.getenv("MYSQL_USER"),
    "password": os.getenv("MYSQL_PASSWORD"),
    "database": os.getenv("MYSQL_DB"),
}
connection_pool = pooling.MySQLConnectionPool(
    pool_name="mypool", pool_size=5, **dbconfig
)


def get_db_connection():
    return connection_pool.get_connection()


@app.route("/")
def index():
    return render_template("login.html")


@app.route("/login", methods=["POST"])
def login():
    client_id = request.form.get("client_id")
    password = request.form.get("password")

    response = requests.post(
        f"{API_URL}/login",
        json={"client_id": client_id, "password": password},
    )

    if response.status_code == 200:
        session["client_id"] = client_id
        session["cookies"] = response.cookies.get_dict()  # Save cookies from the API
        return redirect(url_for("dashboard"))
    else:
        error_message = response.json().get("error", "Invalid credentials")
        return render_template("login.html", error=error_message)


@app.route("/dashboard")
def dashboard():
    if "client_id" not in session:
        return redirect(url_for("index"))

    client_id = session["client_id"]
    tokenized_entries = fetch_tokenized_entries(client_id)

    return render_template(
        "dashboard.html", client_id=client_id, tokenized_entries=tokenized_entries
    )


@cache.memoize(timeout=300)
def fetch_tokenized_entries(client_id):
    table_name = f"{client_id}_tokens"
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    cursor.execute(f"SELECT id, tokens, created_at FROM {table_name}")
    entries = cursor.fetchall()
    cursor.close()
    connection.close()
    return [
        {
            "id": entry["id"],
            "tokens": json.loads(entry["tokens"]),
            "created_at": entry["created_at"],
        }
        for entry in entries
    ]


@app.route("/logout", methods=["POST"])
def logout():
    session.pop("client_id", None)
    session.pop("cookies", None)
    response = redirect(url_for("index"))
    response.delete_cookie("session")
    return response


@app.route("/tokenize", methods=["POST"])
def tokenize():
    if "client_id" not in session:
        return redirect(url_for("index"))

    ghana_card_number = request.form.get("ghana_card_number")
    phone_number = request.form.get("phone_number")

    # Use the saved cookies for authenticated requests
    api_cookies = session.get("cookies", {})
    response = requests.post(
        f"{API_URL}/tokenize",
        json={"ghana_card_number": ghana_card_number, "phone_number": phone_number},
        cookies=api_cookies,
    )

    if response.status_code == 200:
        token_data = response.json()
        tokens = token_data.get("tokens", {})

        session["tokens"] = tokens

        # Save tokenized data into the respective client's table
        client_id = session["client_id"]
        table_name = f"{client_id}_tokens"
        save_tokens_to_db(table_name, tokens)

        # Clear the cache for the client's tokenized entries
        cache.delete_memoized(fetch_tokenized_entries, client_id)

        return render_template(
            "dashboard.html",
            tokenize_response=tokens,
            success="Tokenization successful",
        )
    else:
        error_message = response.json().get(
            "error", "An error occurred during tokenization"
        )
        return render_template("dashboard.html", error=error_message)


def save_tokens_to_db(table_name, tokens):
    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        # Check if the tokens already exist
        cursor.execute(
            f"SELECT COUNT(*) FROM {table_name} WHERE tokens = %s",
            (json.dumps(tokens),),
        )
        count = cursor.fetchone()[0]

        if count == 0:
            # Insert new tokens if they don't already exist
            cursor.execute(
                f"INSERT INTO {table_name} (tokens) VALUES (%s)", (json.dumps(tokens),)
            )
            connection.commit()

        cursor.close()
        connection.close()
    except mysql.connector.Error as err:
        logging.error(f"Error: {err}")
        raise


@app.route("/detokenize", methods=["POST"])
def detokenize():
    if "client_id" not in session:
        return redirect(url_for("index"))

    token = request.form.get("token")

    # Use the saved cookies for authenticated requests
    api_cookies = session.get("cookies", {})
    response = requests.post(
        f"{API_URL}/detokenize",
        json={"token": token},
        cookies=api_cookies,
    )

    if response.status_code == 200:
        return render_template(
            "dashboard.html",
            detokenize_response=response.json(),
            success="Detokenization successful",
        )
    else:
        error_message = response.json().get(
            "error", "An error occurred during detokenization"
        )
        return render_template("dashboard.html", error=error_message)


@app.route("/detokenize_entry/<int:entry_id>")
def detokenize_entry(entry_id):
    client_id = session["client_id"]
    table_name = f"{client_id}_tokens"
    entry = fetch_token_details(table_name, entry_id)
    tokens = entry["tokens"]

    # Send tokens to the API for detokenization
    api_cookies = session.get("cookies", {})
    response = requests.post(
        f"{API_URL}/detokenize",
        json={"tokens": tokens},
        cookies=api_cookies,
    )

    if response.status_code == 200:
        return jsonify(response.json())
    else:
        return jsonify({"error": "An error occurred during detokenization"}), 500


def fetch_token_details(table_name, entry_id):
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    cursor.execute(f"SELECT tokens FROM {table_name} WHERE id = %s", (entry_id,))
    entry = cursor.fetchone()
    cursor.close()
    connection.close()
    return {"tokens": json.loads(entry["tokens"])}


@app.route("/download_token")
def download_token():
    if "client_id" not in session or "token" not in session:
        return redirect(url_for("index"))

    token = session["token"]

    # Append the new token to the existing CSV file
    with open(TOKEN_CSV_PATH, mode="a", newline="") as file:
        writer = csv.writer(file)
        writer.writerow([token])

    return send_file(
        TOKEN_CSV_PATH,
        as_attachment=True,
        mimetype="text/csv",
        download_name="token.csv",
    )


if __name__ == "__main__":
    app.run(port=5000, host="0.0.0.0", debug=True)
