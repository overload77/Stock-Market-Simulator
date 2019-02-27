import os
import sqlite3, datetime

from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application

app = Flask(__name__)
app.secret_key = "5852971084226238701177882"

# Ensure templates are auto-reloaded
# app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
"""
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response
"""

# Custom filter
# app.jinja_env.filters["usd"] = usd

# Configure db to use in views
""" 
DATABASE = 'finance.db'

def get_db():
    conn = getattr(g, '_database', None)
    if conn is None:
        conn = g._database = sqlite3.connect(DATABASE)
    return conn

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()
"""


@app.route("/")
@login_required
def index():
    """
    Show portfolio of stocks

    Args:
        none
    
    Returns:
        Index page if user is logged in(login page otherwise)
        
    """
    # Create new cursor for thread safety
    connection = sqlite3.connect("finance.db")
    db = connection.cursor()

    # Get user id and his/her purchase info
    user_id = session.get("user_id")
    user_purchases = db.execute("""
                                SELECT symbol, SUM(share_number)
                                FROM transactions
                                WHERE user_id = ( ? )
                                GROUP BY symbol
                                HAVING SUM(share_number) > 0""",(user_id, )).fetchall()

    current_portfolio = list()
    # Calculate current value of his/her shares
    total_portfolio_value = 0
    for tup in user_purchases:
        symbol = tup[0]
        share_number = tup[1]

        # Get stock information from restful api
        stock_info = lookup(symbol)
        current_share_price = stock_info["price"]
        company_name = stock_info["name"]

        # Create new information about this stock to fill portfolio list
        new_share_info = (symbol, company_name, share_number, current_share_price, (share_number * current_share_price))
        current_portfolio.append(new_share_info)
        total_portfolio_value += (share_number * current_share_price)

    # Get user's cash
    user_cash = db.execute("SELECT cash FROM users WHERE id = ( ? )", (user_id, ) ).fetchone()[0]
    total_portfolio_value += user_cash

    return render_template("index.html", portfolio=current_portfolio, usd=usd,
                            user_cash=user_cash, total_value=total_portfolio_value)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    # Create new cursor for thread safety
    connection = sqlite3.connect("finance.db")
    db = connection.cursor()

    if request.method == "POST":
        if not request.form.get("symbol"):
            return apology("No Symbol", 403)
        if not request.form.get("shares") or int(request.form.get("shares")) < 1:
            return apology("No Shares", 403)

        # Get result and check if symbol was valid
        api_result = lookup(request.form.get("symbol"))
        if api_result is None:
            return apology("Wrong Symbol", 403)

        # Local variables to fill transactions table
        current_user_id = session.get("user_id")
        symbol = api_result["symbol"]
        share_number = int(request.form.get("shares"))
        share_price = api_result["price"]
        time = datetime.datetime.now().strftime("%d-%m-%Y %H:%M:%S")

        # Get current users cash from db
        users_cash = db.execute("SELECT cash FROM users WHERE id = ( ? );", (current_user_id, )).fetchone()[0]

        # Check if user has enough money and insert breaking bad meme if he/she has not.
        users_new_cash = users_cash - (share_number * share_price)
        if users_new_cash < 0:
            return apology("Skyler where is the money?", 403)

        # Make a purchase
        db.execute("""
            INSERT INTO transactions (user_id, symbol, share_number, at_price, date)
            VALUES (?, ?, ?, ?, ?);""", (current_user_id, symbol, share_number, share_price, time) )

        # Update user's cash and commit to the database
        db.execute("UPDATE users SET cash = ( ? ) WHERE id = ( ? )", (users_new_cash, current_user_id) )
        connection.commit()

        flash("Purchase successful!")
        return redirect(url_for("index"))
    else:
        return render_template("buy.html")



@app.route("/check", methods=["GET"])
def check():
    """Return true if username available, else false, in JSON format"""
    # Create new cursor for thread safety
    connection = sqlite3.connect("finance.db")
    db = connection.cursor()

    # Check if user gave the right input
    if not request.args.get("username"):
        return apology("Usage: check?username='username'", 403)

    # Fetch parameter
    username = request.args.get("username")

    if len(username) > 0:
        if (db.execute("SELECT * FROM users WHERE username = ( ? )", (username, )).fetchone()) is None:
            return jsonify(True)

    return jsonify(False)


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    # Create new cursor for thread safety
    connection = sqlite3.connect("finance.db")
    db = connection.cursor()

    # Get user's id from session
    user_id = session.get("user_id")

    # Get transactions associated with this user
    transactions = db.execute("""
                              SELECT symbol, share_number, at_price, date
                              FROM transactions
                              WHERE user_id = ( ? )""", (user_id, ) ).fetchall()

    return render_template("history.html", transactions=transactions, usd=usd)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""
    # Create new cursor for thread safety
    connection = sqlite3.connect("finance.db")
    db = connection.cursor()

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = (?)", (request.form.get("username"), )).fetchall()

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0][2], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0][0]
        session.permanent = True
        
        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""

    # Check request type
    if request.method == "POST":
        if not request.form.get("symbol"):
            return apology("Where is my stock", 403)

        # Fetch stock info from api
        api_response = lookup(request.form.get("symbol"))
        company_name = api_response["name"]
        stock_price  = usd(api_response["price"])
        stock_name = api_response["symbol"]

        return render_template("quoted.html", company_name=company_name, stock_price=stock_price, stock_name=stock_name)
    else:
        return render_template("quote.html")




@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    # Create new cursor for thread safety
    connection = sqlite3.connect("finance.db")
    db = connection.cursor()

    if request.method == "POST":
        # Check if user provided right credentials and insert cat meme if he/she didn't
        if not request.form.get("username"):
            return apology("must provide username", 403)
        elif not request.form.get("password"):
            return apology("must provide password", 403)
        elif request.form.get("password") != request.form.get("confirmation"):
            return apology("passwords are not same", 403)
        elif len(request.form.get("password")) < 8:
            return apology("password too short", 403)

        # Check if that username already exists
        username = request.form.get("username")
        if db.execute("SELECT * FROM users WHERE username = ( ? )", (username, )).fetchone() is not None:
            return apology("choose another username", 403)

        password = request.form.get("password")
        if not any(c.isdigit() for c in password):
            return apology("password should contain number", 403)

        hashed_pass = generate_password_hash(request.form.get("password"))

        db.execute("INSERT INTO users (username, hash) VALUES (?, ?)", (username, hashed_pass))
        connection.commit()

        return redirect("/")
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    # Create new cursor for thread safety
    connection = sqlite3.connect("finance.db")
    db = connection.cursor()

    # Get current users id from session
    user_id = session.get("user_id")
    # Check request method
    if request.method == "POST":
        # Validate user input
        if not request.form.get("symbol"):
            return apology("No symbol", 403)
        if not request.form.get("shares") or int(request.form.get("shares")) < 1:
            return apology("No shares", 403)

        # Create local variables from form input
        symbol = request.form.get("symbol")
        shares = int(request.form.get("shares"))

        # Check if user really has that share (more validation)
        users_shares = db.execute("""
                                  SELECT SUM(share_number) FROM transactions
                                  WHERE user_id = ( ? )
                                  AND symbol = ( ? )""", (user_id, symbol) ).fetchone()[0]

        # Check user have more shares than he/she wants to sell (even more validation)
        if users_shares - shares < 0:
            return apology("You dont have that many shares", 403)

        # Get share's current price, total price of shares and transaction time
        price = lookup(symbol).get("price")
        total_price = price * shares
        time = datetime.datetime.now().strftime("%d-%m-%Y %H:%M:%S")

        # Sell shares
        db.execute("""
                   INSERT INTO transactions (user_id, symbol, share_number, at_price, date)
                   VALUES (?, ?, ?, ?, ?)""", (user_id, symbol, -shares, price, time))

        # Update user's cash and commit to the database
        db.execute("UPDATE users SET cash = cash + ( ? ) WHERE id = ( ? )", (total_price, user_id))
        connection.commit()

        flash("Sold!")
        return redirect(url_for("index"))
    else:
        symbol_tuples = db.execute("""
            SELECT symbol FROM transactions
            WHERE user_id = ( ? )
            GROUP BY symbol
            HAVING SUM(share_number) > 0""", (user_id, )).fetchall()

        symbols = [tup[0] for tup in symbol_tuples]
        return render_template("sell.html", symbols=symbols)


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)