"""
Mini Project: Library Management System (Python + SQLite)
Author : Emad Ali (UID 24BSC10027)

Features
  1. Add / list / search books
  2. Register / list members
  3. Issue a book (14-day loan) and return a book (late fine calculated)
  4. View currently issued books and overdue books
  5. Summary report
Data is stored permanently in library.db (SQLite, included with Python).

Run      : python library_management.py
Demo     : python library_management.py --demo   (loads sample data, shows a scenario)
Requires : Python 3.8+ (no extra libraries)
"""
import sqlite3
import sys
from datetime import date, timedelta

DB_FILE = "library.db"
LOAN_DAYS = 14
FINE_PER_DAY = 2          # rupees per day after the due date


# ------------------------------------------------------------------
# Database setup
# ------------------------------------------------------------------
def connect(path=DB_FILE):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS books (
            book_id   INTEGER PRIMARY KEY AUTOINCREMENT,
            title     TEXT NOT NULL,
            author    TEXT NOT NULL,
            copies    INTEGER NOT NULL CHECK (copies >= 0),
            available INTEGER NOT NULL CHECK (available >= 0)
        );
        CREATE TABLE IF NOT EXISTS members (
            member_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name      TEXT NOT NULL,
            phone     TEXT
        );
        CREATE TABLE IF NOT EXISTS issues (
            issue_id    INTEGER PRIMARY KEY AUTOINCREMENT,
            book_id     INTEGER NOT NULL REFERENCES books(book_id),
            member_id   INTEGER NOT NULL REFERENCES members(member_id),
            issue_date  TEXT NOT NULL,
            due_date    TEXT NOT NULL,
            return_date TEXT,
            fine        INTEGER NOT NULL DEFAULT 0
        );
    """)
    return conn


# ------------------------------------------------------------------
# Core operations (each returns a message so they are easy to test)
# ------------------------------------------------------------------
def add_book(conn, title, author, copies=1):
    if not title.strip() or not author.strip():
        return "Title and author cannot be empty."
    if copies < 1:
        return "Copies must be at least 1."
    cur = conn.execute(
        "INSERT INTO books (title, author, copies, available) VALUES (?,?,?,?)",
        (title.strip(), author.strip(), copies, copies))
    conn.commit()
    return f"Book added with ID {cur.lastrowid}."


def add_member(conn, name, phone=""):
    if not name.strip():
        return "Name cannot be empty."
    cur = conn.execute("INSERT INTO members (name, phone) VALUES (?,?)",
                       (name.strip(), phone.strip()))
    conn.commit()
    return f"Member registered with ID {cur.lastrowid}."


def issue_book(conn, book_id, member_id, today=None):
    today = today or date.today()
    book = conn.execute("SELECT * FROM books WHERE book_id=?", (book_id,)).fetchone()
    member = conn.execute("SELECT * FROM members WHERE member_id=?", (member_id,)).fetchone()
    if book is None:
        return "No such book."
    if member is None:
        return "No such member."
    if book["available"] < 1:
        return f"'{book['title']}' is not available right now."
    already = conn.execute(
        "SELECT 1 FROM issues WHERE book_id=? AND member_id=? AND return_date IS NULL",
        (book_id, member_id)).fetchone()
    if already:
        return "This member already has a copy of this book."
    count = conn.execute(
        "SELECT COUNT(*) FROM issues WHERE member_id=? AND return_date IS NULL",
        (member_id,)).fetchone()[0]
    if count >= 3:
        return "Limit reached: a member can hold at most 3 books."
    due = today + timedelta(days=LOAN_DAYS)
    conn.execute(
        "INSERT INTO issues (book_id, member_id, issue_date, due_date) VALUES (?,?,?,?)",
        (book_id, member_id, today.isoformat(), due.isoformat()))
    conn.execute("UPDATE books SET available = available - 1 WHERE book_id=?", (book_id,))
    conn.commit()
    return f"Issued '{book['title']}' to {member['name']}. Due on {due.isoformat()}."


def return_book(conn, book_id, member_id, today=None):
    today = today or date.today()
    row = conn.execute(
        "SELECT * FROM issues WHERE book_id=? AND member_id=? AND return_date IS NULL",
        (book_id, member_id)).fetchone()
    if row is None:
        return "No active issue found for this book and member."
    due = date.fromisoformat(row["due_date"])
    late_days = max((today - due).days, 0)
    fine = late_days * FINE_PER_DAY
    conn.execute("UPDATE issues SET return_date=?, fine=? WHERE issue_id=?",
                 (today.isoformat(), fine, row["issue_id"]))
    conn.execute("UPDATE books SET available = available + 1 WHERE book_id=?", (book_id,))
    conn.commit()
    if fine:
        return f"Returned {late_days} day(s) late. Fine: Rs {fine}."
    return "Returned on time. No fine."


def search_books(conn, keyword):
    like = f"%{keyword.strip()}%"
    return conn.execute(
        "SELECT * FROM books WHERE title LIKE ? OR author LIKE ? ORDER BY title",
        (like, like)).fetchall()


def list_books(conn):
    return conn.execute("SELECT * FROM books ORDER BY book_id").fetchall()


def list_members(conn):
    return conn.execute("SELECT * FROM members ORDER BY member_id").fetchall()


def issued_books(conn, overdue_only=False, today=None):
    today = (today or date.today()).isoformat()
    sql = """SELECT i.issue_id, b.title, m.name, i.issue_date, i.due_date
             FROM issues i JOIN books b ON b.book_id = i.book_id
             JOIN members m ON m.member_id = i.member_id
             WHERE i.return_date IS NULL"""
    params = ()
    if overdue_only:
        sql += " AND i.due_date < ?"
        params = (today,)
    return conn.execute(sql + " ORDER BY i.due_date", params).fetchall()


def summary(conn):
    q = lambda s: conn.execute(s).fetchone()[0]
    return {
        "Book titles": q("SELECT COUNT(*) FROM books"),
        "Total copies": q("SELECT COALESCE(SUM(copies),0) FROM books"),
        "Copies available": q("SELECT COALESCE(SUM(available),0) FROM books"),
        "Members": q("SELECT COUNT(*) FROM members"),
        "Books currently issued": q("SELECT COUNT(*) FROM issues WHERE return_date IS NULL"),
        "Fines collected (Rs)": q("SELECT COALESCE(SUM(fine),0) FROM issues"),
    }


# ------------------------------------------------------------------
# Display helpers
# ------------------------------------------------------------------
def show_books(rows):
    if not rows:
        print("  (no books found)")
        return
    print(f"  {'ID':<4}{'Title':<32}{'Author':<22}{'Avail/Total':<12}")
    for r in rows:
        print(f"  {r['book_id']:<4}{r['title'][:30]:<32}{r['author'][:20]:<22}"
              f"{r['available']}/{r['copies']}")


def show_members(rows):
    if not rows:
        print("  (no members)")
        return
    print(f"  {'ID':<4}{'Name':<26}{'Phone':<14}")
    for r in rows:
        print(f"  {r['member_id']:<4}{r['name'][:24]:<26}{r['phone'] or '-':<14}")


def show_issues(rows):
    if not rows:
        print("  (none)")
        return
    print(f"  {'Book':<30}{'Member':<20}{'Issued':<12}{'Due':<12}")
    for r in rows:
        print(f"  {r['title'][:28]:<30}{r['name'][:18]:<20}{r['issue_date']:<12}{r['due_date']:<12}")


def ask_int(prompt):
    try:
        return int(input(prompt))
    except ValueError:
        return None


# ------------------------------------------------------------------
# Menu
# ------------------------------------------------------------------
MENU = """
===== LIBRARY MANAGEMENT SYSTEM =====
 1. Add book            6. Register member
 2. List books          7. List members
 3. Search books        8. Currently issued books
 4. Issue book          9. Overdue books
 5. Return book        10. Summary report
 0. Exit
"""


def run_menu(conn):
    while True:
        print(MENU)
        choice = input("Enter choice: ").strip()
        if choice == "1":
            title = input("Title: ")
            author = input("Author: ")
            copies = ask_int("Copies: ")
            print(add_book(conn, title, author, copies) if copies else "Invalid number.")
        elif choice == "2":
            show_books(list_books(conn))
        elif choice == "3":
            show_books(search_books(conn, input("Search title/author: ")))
        elif choice in ("4", "5"):
            b, m = ask_int("Book ID: "), ask_int("Member ID: ")
            if b is None or m is None:
                print("IDs must be numbers.")
            else:
                print(issue_book(conn, b, m) if choice == "4" else return_book(conn, b, m))
        elif choice == "6":
            print(add_member(conn, input("Name: "), input("Phone: ")))
        elif choice == "7":
            show_members(list_members(conn))
        elif choice == "8":
            show_issues(issued_books(conn))
        elif choice == "9":
            show_issues(issued_books(conn, overdue_only=True))
        elif choice == "10":
            for k, v in summary(conn).items():
                print(f"  {k:<26}{v}")
        elif choice == "0":
            print("Goodbye!")
            break
        else:
            print("Invalid choice, try again.")


# ------------------------------------------------------------------
# Demo scenario (uses an in-memory database, nothing is saved)
# ------------------------------------------------------------------
def demo():
    conn = connect(":memory:")
    print(">>> Adding books and members")
    for t, a, c in [("Python Crash Course", "Eric Matthes", 2),
                    ("Data Mining: Concepts and Techniques", "Han and Kamber", 1),
                    ("Introduction to Algorithms", "Cormen et al.", 3)]:
        print(add_book(conn, t, a, c))
    print(add_member(conn, "Emad Ali", "9876500001"))
    print(add_member(conn, "Riya Sharma", "9876500002"))
    show_books(list_books(conn))

    print("\n>>> Issuing books")
    print(issue_book(conn, 1, 1))
    print(issue_book(conn, 2, 1))
    print(issue_book(conn, 2, 2))            # only 1 copy: should fail
    print(issue_book(conn, 1, 1))            # duplicate: should fail

    print("\n>>> Overdue check 20 days from now")
    later = date.today() + timedelta(days=20)
    show_issues(issued_books(conn, overdue_only=True, today=later))

    print("\n>>> Returning books")
    print(return_book(conn, 1, 1, today=later))                     # 6 days late
    print(return_book(conn, 2, 1, today=date.today()))              # on time
    print(return_book(conn, 3, 2))                                  # never issued

    print("\n>>> Summary")
    for k, v in summary(conn).items():
        print(f"  {k:<26}{v}")


if __name__ == "__main__":
    if "--demo" in sys.argv:
        demo()
    else:
        connection = connect()
        try:
            run_menu(connection)
        finally:
            connection.close()
