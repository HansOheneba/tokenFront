import requests
import csv
import os
from prettytable import PrettyTable
import getpass
import mysql.connector
import json
from dotenv import load_dotenv

load_dotenv()

API_URL = "http://localhost:5000"
SESSION = {"client_id": None, "cookies": None, "token": None, "user_data": None}


def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")


def show_session_info():
    """Displays session details (Client ID & Cookies)."""
    print("\n ===== Session Info =====")
    table = PrettyTable()
    table.field_names = ["Client ID", "Cookies"]
    table.add_row([SESSION["client_id"], SESSION["cookies"]])
    print(table)


def login():
    """Forces login before anything else."""
    while True:
        clear_screen()
        print(" === Client Login ===")
        client_id = input("Client ID: ").strip()
        password = getpass.getpass("Password: ").strip()

        response = requests.post(
            f"{API_URL}/login",
            json={"client_id": client_id, "password": password},
        )

        if response.status_code == 200:
            SESSION["client_id"] = client_id
            SESSION["cookies"] = response.cookies.get_dict()
            print("✅ Login successful!")
            show_session_info()
            break  # Exit the login loop if successful
        else:
            print("❌ Invalid credentials. Try again.\n")


def save_tokens_to_db(client_id, tokens):
    try:
        connection = mysql.connector.connect(
            host=os.getenv("MYSQL_HOST"),
            user=os.getenv("MYSQL_USER"),
            password=os.getenv("MYSQL_PASSWORD"),
            database=os.getenv("MYSQL_DB"),
        )
        cursor = connection.cursor()

        table_name = f"{client_id}_tokens"

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
        print(f"Error: {err}")
        raise


def tokenize():
    clear_screen()
    print("Verifying and Tokenizing Data")
    ghana_card_number = input("Ghana Card Number: ").strip()
    phone_number = input("Phone Number: ").strip()

    response = requests.post(
        f"{API_URL}/tokenize",
        json={"ghana_card_number": ghana_card_number, "phone_number": phone_number},
        cookies=SESSION["cookies"],
    )

    if response.status_code == 200:
        token_data = response.json().get("tokens", {})
        SESSION["token"] = token_data
        print("✅ Token generated:")
        print("User Data:")
        table = PrettyTable()
        table.field_names = ["Field", "Value"]

        ordered_fields = [
            "first_name",
            "middle_name",
            "last_name",
            "ghana_card_number",
            "date_of_birth",
            "place_of_birth",
            "nationality",
            "ethnicity",
            "marital_status",
            "mother_name",
            "father_name",
            "email",
            "gender",
            "address",
            "phone_number",
        ]

        for field in ordered_fields:
            table.add_row([field, token_data.get(field)])
        print(table)

        # Save tokenized data into the respective client's table
        save_tokens_to_db(SESSION["client_id"], token_data)
    else:
        print(f"❌ Error: {response.json().get('error')}")

    show_session_info()


def detokenize():
    clear_screen()
    print("🔄 Detokenizing Data")
    token = input("Enter Token: ").strip()

    response = requests.post(
        f"{API_URL}/detokenize",
        json={"token": token},
        cookies=SESSION["cookies"],
    )

    if response.status_code == 200:
        user_data = response.json()
        print("✅ Detokenized Data:")
        table = PrettyTable()
        table.field_names = ["Field", "Value"]
        ordered_fields = [
            "first_name",
            "middle_name",
            "last_name",
            "ghana_card_number",
            "date_of_birth",
            "place_of_birth",
            "nationality",
            "ethnicity",
            "marital_status",
            "mother_name",
            "father_name",
            "email",
            "gender",
            "address",
            "phone_number",
        ]
        for field in ordered_fields:
            table.add_row([field, user_data.get(field)])
        print(table)
    else:
        print(f"❌ Error: {response.json().get('error')}")

    show_session_info()


def fetch_tokenized_entries():
    """Fetches tokenized entries from the database."""
    client_id = SESSION["client_id"]
    table_name = f"{client_id}_tokens"

    try:
        connection = mysql.connector.connect(
            host=os.getenv("MYSQL_HOST"),
            user=os.getenv("MYSQL_USER"),
            password=os.getenv("MYSQL_PASSWORD"),
            database=os.getenv("MYSQL_DB"),
        )
        cursor = connection.cursor(dictionary=True)
        cursor.execute(f"SELECT id, tokens, created_at FROM {table_name}")
        entries = cursor.fetchall()
        cursor.close()
        connection.close()

        if entries:
            print("✅ Tokenized Entries:")
            for entry in entries:
                tokens = json.loads(entry["tokens"])
                print(f"\nID: {entry['id']}")
                print(f"Created At: {entry['created_at']}")
                ordered_fields = [
                    "first_name",
                    "middle_name",
                    "last_name",
                    "ghana_card_number",
                    "date_of_birth",
                    "place_of_birth",
                    "nationality",
                    "ethnicity",
                    "marital_status",
                    "mother_name",
                    "father_name",
                    "email",
                    "gender",
                    "address",
                    "phone_number",
                ]
                for field in ordered_fields:
                    print(f"{field.replace('_', ' ').title()}: {tokens.get(field)}")
                print("-" * 40)
        else:
            print("⚠️ No tokenized entries found.")
    except mysql.connector.Error as err:
        print(f"Error: {err}")


def save_token():
    if SESSION["token"] is None:
        print("⚠️ No token available. Please tokenize first!")
        return

    file_name = "token.csv"
    file_exists = os.path.isfile(file_name)

    with open(file_name, mode="a", newline="") as file:
        writer = csv.writer(file)
        if not file_exists:
            writer.writerow(["Token"])
        writer.writerow([SESSION["token"]])

    print(f"✅ Token saved to {file_name}")
    show_session_info()


def logout():
    global SESSION
    SESSION = {"client_id": None, "cookies": None, "token": None}
    print("✅ Logged out successfully!")


def menu():
    login()  # Force login before showing menu

    while True:
        print("\n === Tokenization CLI ===")
        print("[1] Verify and Tokenize")
        print("[2] Detokenize")
        print("[3] View Tokenized Entries")
        print("[4] Save Token to CSV")
        print("[5] Logout")
        print("[0] Exit")

        choice = input("\nEnter your choice: ").strip()

        if choice == "1":
            tokenize()
        elif choice == "2":
            detokenize()
        elif choice == "3":
            fetch_tokenized_entries()
        elif choice == "4":
            save_token()
        elif choice == "5":
            logout()
            login()  # Force login again after logout
        elif choice == "0":
            print(" Exiting CLI...")
            break
        else:
            print("❌ Invalid choice! Try again.")


if __name__ == "__main__":
    menu()
