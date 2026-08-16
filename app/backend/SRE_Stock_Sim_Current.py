from __future__ import annotations
import jwt, os
from datetime import datetime, timezone, time, date, timedelta
import threading, time as time_module
from zoneinfo import ZoneInfo
from flask import Flask, request, jsonify
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
import socket
import random


#this is a secure way to securely transmit info as JSON
JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-me")
JWT_ALG = "HS256"

#Helper for JWT
def make_token(username: str) -> str:
    now = int(time_module.time())
    payload = {"sub": username, "iat": now, "exp": now + 60*60}  # token expires in 1h
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)

def parse_token(auth_header):
    if not auth_header or not auth_header.startswith("Bearer "):
        return None
    token = auth_header.split(" ",1)[1].strip()
    try:
        data = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
        return data.get("sub")
    except Exception:
        return None

# Optional: psycopg2 for /dbcheck (OK if missing)
try:
    import psycopg2
except Exception:
    psycopg2 = None

# ----------------------------------------- DB HELPERS ---------------------------------------
def get_db_connection():
    import psycopg2
    conn = psycopg2.connect(
        host=os.getenv("DATABASE_HOST"),
        port=os.getenv("DATABASE_PORT", "5432"),
        dbname=os.getenv("DATABASE_NAME"),
        user=os.getenv("DATABASE_USER"),
        password=os.getenv("DATABASE_PASSWORD")
    )
    return conn

def db_get_user_by_username(username: str):
    username = (username or "").strip()
    if not username:
        return None
    conn = get_db_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, username, email, full_name, password_hash, role, created_at
                    FROM users
                    WHERE username = %s
                """, (username,))
                row = cur.fetchone()
                if not row:
                    return None
                return {
                    "id": row[0], "username": row[1], "email": row[2],
                    "full_name": row[3], "password_hash": row[4],
                    "role": row[5], "created_at": row[6]
                }
    finally:
        conn.close()

def db_create_user(full_name: str, username: str, email: str, password: str, role: str = "user"):
    username = (username or "").strip()
    email = (email or "").strip().lower()
    full_name = (full_name or "").strip()

    if not username or not email or not full_name or not password:
        raise ValueError("All fields are required")

    pw_hash = generate_password_hash(password)

    conn = get_db_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO users (username, email, full_name, password_hash, role)
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING id, username, email, full_name, role, created_at
                """, (username, email, full_name, pw_hash, role))
                row = cur.fetchone()
                return {
                    "id": row[0], "username": row[1], "email": row[2],
                    "full_name": row[3], "role": row[4], "created_at": row[5]
                }
    except Exception as e:
        msg = str(e)
        if "users_username_key" in msg or "unique constraint" in msg.lower():
            raise ValueError("Username already exists")
        if "users_email_key" in msg:
            raise ValueError("Email already exists")
        raise
    finally:
        conn.close()

def db_deposit(user_id: str, amount: float) -> float:
    """Add to cash_balance; returns new balance."""
    import psycopg2
    conn = get_db_connection()
    with conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE users
                   SET cash_balance = cash_balance + %s
                 WHERE id = %s
             RETURNING cash_balance;
            """, (amount, user_id))
            row = cur.fetchone()
            if not row:
                raise ValueError("User not found")
            return float(row[0])

def db_withdraw(user_id: str, amount: float) -> float:
    """
    Subtract from cash_balance; returns new balance.
    Fails if balance would go negative.
    """
    import psycopg2
    conn = get_db_connection()
    with conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE users
                   SET cash_balance = cash_balance - %s
                 WHERE id = %s
                   AND cash_balance >= %s
             RETURNING cash_balance;
            """, (amount, user_id, amount))
            row = cur.fetchone()
            if not row:
                # Either user not found or insufficient funds
                raise ValueError("Insufficient funds")
            return float(row[0])

def db_get_portfolio_history(user_id: int, days: int = 7):
    """
    Returns cumulative 'invested' value per day for the last N days,
    based on the transactions table.

    For each transaction:
      - type = 'buy'      -> +total_value
      - type = 'sell'     -> -total_value
      - type = 'deposit'  -> +total_value (if you log these)
      - type = 'withdraw' -> -total_value (if you log these)

    Output list:
      [ { "date": "2025-11-10", "value": 1234.56 }, ... ]
    """
    from collections import defaultdict

    conn = get_db_connection()
    try:
        start_date = date.today() - timedelta(days=days - 1)

        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        created_at::date AS d,
                        type,
                        total_value
                    FROM transactions
                    WHERE user_id = %s
                      AND created_at::date >= %s
                    ORDER BY d ASC;
                    """,
                    (user_id, start_date),
                )
                rows = cur.fetchall()

        # Date -> net change that day
        changes = defaultdict(float)
        for d, ttype, total in rows:
            total = float(total or 0)
            ttype = (ttype or "").lower()
            if ttype in ("buy", "deposit"):
                changes[d] += total
            elif ttype in ("sell", "withdraw"):
                changes[d] -= total

        # Build cumulative series
        history = []
        cumulative = 0.0
        for i in range(days):
            current = start_date + timedelta(days=i)
            cumulative += changes.get(current, 0.0)
            history.append(
                {
                    "date": current.isoformat(),
                    "value": cumulative,
                }
            )

        return history
    finally:
        conn.close()

def db_list_transactions(user_id, tx_type=None, ticker=None, limit=200):
    """
    Returns the most recent transaction of a user (last 200)
    Schema assumed:
      transactions(
        id serial primary key,
        user_id int, references user(id),
        type text, e.g. is it a 'buy', 'sell', 'deposit', 'withdraw'?
        ticker text, --obvious null for cash transactions
        quantity integer, --same sitch
        price numeric, --ditto
        total_value numeric, --value calculated of the trade or cash movement
        created_at timestamptz default now()
      )
    """
    conn = get_db_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                sql = """
                   SELECT created_at, type, ticker, quantity, price, total_value
                   FROM transactions
                   WHERE user_id = %s
                """

                params = [user_id]

                if tx_type:
                    sql += " AND type = %s"
                    params.append(tx_type)

                if ticker:
                    sql += " AND ticker = %s"
                    params.append(ticker)

                sql += " ORDER BY created_at DESC LIMIT %s"
                params.append(limit)

                cur.execute(sql, params)
                rows = cur.fetchall()

        results = []
        for created_at, ttype, tk, qty, price, total_value, in rows:
            results.append({
                "created_at": created_at.isoformat() if hasattr(created_at, "isoformat") else None,
                "type": ttype,
                "ticker": tk,
                "quantity": qty,
                "price": float(price) if price is not None else None,
                "total_value": float(total_value) if total_value is not None else None,
            })
        return results
    finally:
        conn.close()

# ------------------------------ DataBase For Administrative Controls ------------------------------
def db_get_market_hours():
    """
    Returns {"open_time": "6:00", "close_time": "17:00", "tz_name": "America/New_York"}
    """
    conn = get_db_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT open_time, close_time, tz_name, COALESCE(allow_weekend_trading, FALSE)
                    FROM market_hours
                    WHERE id = TRUE
                    LIMIT 1
                """)
                row = cur.fetchone()
                if not row:
                    # Fallback if table exists but row is missing
                    return {"open_time": "6:00", "close_time": "17:00", "tz_name": "America/New_York","allow_weekend_trading": False}
                # row[0], and row[1] are POSTGRES time converted to HH:MM
                open_time, close_time, tz_name, allow_weekend_trading = row
                open_str = open_time.strftime("%H:%M")
                close_str = close_time.strftime("%H:%M")
                return {"open_time": open_str, "close_time": close_str, "tz_name": tz_name, "allow_weekend_trading": bool(allow_weekend_trading)}
    finally:
        conn.close()

def db_update_market_hours(open_time_str: str, close_time_str: str, tz_name: str, allow_weekend_trading: bool | None = None):
    """
    Expects HH:MM 24H strings. Validates basic format and open<close.
    Also returns updated record.
    """

    #This does basic validation
    try:
        openHour, openMinute = map(int, open_time_str.split(":"))
        closeHour, closeMinute = map(int, close_time_str.split(":"))
        openTime = time(openHour, openMinute)
        closeTime = time(closeHour, closeMinute)
    except Exception:
        raise ValueError("Invalid time format; use HH:MM (24-hours).")

    if not (0 <= openHour < 24 and 0 <= closeHour < 24 and 0 <= openMinute < 60 and 0 <= closeMinute < 60):
        raise ValueError("Hours must be between 0-23 and minutes must be between 0-59.")

    if not (openTime < closeTime):
        raise ValueError("Open time must be earlier than close.")

    #This validates the timezone
    try:
        tzName = ZoneInfo(tz_name)
    except Exception:
        raise ValueError("Invalid timezone name; it must be a valid IANA time zone...look em up.")

    conn = get_db_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                if allow_weekend_trading is None:
                    cur.execute("""
                        UPDATE market_hours
                           SET open_time = %s,
                               close_time = %s,
                               tz_name = %s,
                               updated_at = now()
                        WHERE id = TRUE
                    """, (openTime, closeTime, tz_name))
                else:
                    cur.execute("""
                        UPDATE market_hours
                           SET open_time = %s, close_time = %s, tz_name = %s,
                               allow_weekend_trading = %s,
                               updated_at = now()
                         WHERE id = TRUE
                    """, (openTime, closeTime,
                          tz_name, bool(allow_weekend_trading)))

        return db_get_market_hours()
    finally:
        conn.close()

def db_get_market_closure_for_date(d: date):
    """
    This will look up the specific date closure in the market schedule closures table.
    Returns a dict or none if there is no row for that date.

    Table:
      market_schedule_closures(
        close_date DATE PRIMARY KEY,
        is_closed BOOLEAN,
        open_time TIME,
        close_time TIME,
        note TEXT,
        updated_at TIMESTAMPTZ
      )
    """

    conn = get_db_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT close_date, is_closed, open_time, close_time, note
                      FROM market_schedule_closures
                     WHERE close_date = %s
                     LIMIT 1
                """, (d,))
                row = cur.fetchone()
                if not row:
                    return None

                close_date, is_closed, open_time, close_time, note = row

                #Makes sure time is in HH:MM as a string and not am integer
                open_str = open_time.strftime("%H:%M") if open_time is not None else None
                close_str = close_time.strftime("%H:%M") if close_time is not None else None

                return {
                    "close_date": close_date.isoformat(),
                    "is_closed": bool(is_closed),
                    "open_time": open_str,
                    "close_time": close_str,
                    "note": note,
                }

    finally:
        conn.close()

def db_list_market_closures():
    """
    Return all closure/override rows from market_schedule_closures,
    ordered by close_date ascending.

    Schema (your names):
      market_schedule_closures(
        close_date date primary key,
        is_closed  boolean,
        open_time  time,
        close_time time,
        note       text,
        updated_at timestamptz
      )
    """
    conn = get_db_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT close_date, is_closed, open_time, close_time, note
                      FROM market_schedule_closures
                  ORDER BY close_date ASC
                """)
                rows = cur.fetchall()

        results = []
        for close_date, is_closed, open_time, close_time, note in rows:
            open_str = open_time.strftime("%H:%M") if open_time is not None else None
            close_str = close_time.strftime("%H:%M") if close_time is not None else None
            results.append({
                "close_date": close_date.isoformat(),
                "is_closed": bool(is_closed),
                "open_time": open_str,
                "close_time": close_str,
                "note": note,
            })
        return results
    finally:
        conn.close()

def db_upsert_market_closure( close_date_str: str, is_closed: bool, open_time_str: str | None, close_time_str: str | None, note: str | None,):
    """
    Insert or update a single row in market_schedule_closures.

    close_date_str: "YYYY-MM-DD"
    is_closed: True  -> full-day closure (times must be None/empty)
                False -> open, but may use special open/close times
    open_time_str, close_time_str: "HH:MM" or None/"" (24-hour clock)
    """
    # 1) Parse date
    try:
        close_date = datetime.strptime(close_date_str, "%Y-%m-%d").date()
    except Exception:
        raise ValueError("Invalid close_date; expected YYYY-MM-DD")

    # Normalize empty strings to None
    open_time_str = (open_time_str or "").strip() or None
    close_time_str = (close_time_str or "").strip() or None
    note = (note or "").strip() or None

    # 2) Validate combinations
    if is_closed:
        # Fully closed: times must not be provided
        if open_time_str is not None or close_time_str is not None:
            raise ValueError("Closed days cannot have open_time or close_time.")
        open_time = None
        close_time = None
    else:
        # Open, possibly with half-day/special hours
        open_time = None
        close_time = None
        if open_time_str is not None:
            try:
                oh, om = map(int, open_time_str.split(":"))
                open_time = time(oh, om)
            except Exception:
                raise ValueError("Invalid open_time; expected HH:MM (24-hour).")
        if close_time_str is not None:
            try:
                ch, cm = map(int, close_time_str.split(":"))
                close_time = time(ch, cm)
            except Exception:
                raise ValueError("Invalid close_time; expected HH:MM (24-hour).")

        # If both provided, ensure open < close
        if open_time is not None and close_time is not None and not (open_time < close_time):
            raise ValueError("For special hours, open_time must be earlier than close_time.")

    # 3) Upsert row
    conn = get_db_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO market_schedule_closures (close_date, is_closed, open_time, close_time, note, updated_at)
                    VALUES (%s, %s, %s, %s, %s, now())
                    ON CONFLICT (close_date) DO UPDATE
                      SET is_closed = EXCLUDED.is_closed,
                          open_time = EXCLUDED.open_time,
                          close_time = EXCLUDED.close_time,
                          note = EXCLUDED.note,
                          updated_at = now()
                """, (close_date, is_closed, open_time, close_time, note))

        # Return a normalized dict (same shape as db_list_market_closures)
        return {
            "close_date": close_date.isoformat(),
            "is_closed": bool(is_closed),
            "open_time": open_time.strftime("%H:%M") if open_time is not None else None,
            "close_time": close_time.strftime("%H:%M") if close_time is not None else None,
            "note": note,
        }
    finally:
        conn.close()

def db_get_user_holdings(user_id: int):
    """
    This will pull the user's current stock holdings

    Each item looks like this:
      {"ticker": "AAPL",
      "quantity": 10,
      "current_price": 123.45,
      "total_value": 1234.50
    """
    conn = get_db_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        p.ticker,
                        s.company_name,
                        p.quantity,
                        COALESCE(s.current_price, 0) AS current_price,
                        p.quantity * COALESCE(s.current_price, 0) AS total_value
                      FROM user_positions AS p
                      JOIN stocks AS s
                        ON s.ticker = p.ticker
                     WHERE p.user_id = %s
                       AND p.quantity > 0
                    ORDER BY s.company_name ASC;
                    """,
                    (user_id,),
                )
                rows = cur.fetchall()

        holdings = []
        for ticker, company_name, qty, price, total in rows:
            holdings.append(
                {
                    "ticker": ticker,
                    "company_name": company_name,
                    "quantity": float(qty),
                    "current_price": float(price),
                    "total_value": float(total),
                }
            )
        return holdings

    finally:
        conn.close()

# -------------------------------MARKET OPEN AND CLOSURE ENFORCEMENT HELPER------------------------------
def is_market_open(now_utc: datetime | None = None) -> dict:
    """
    This returns dictionary with (is_open, now_local, open_time, close_time, and tz_name
    """

    #1) This is used for a normal day (base hours)
    rec = db_get_market_hours()
    tz = ZoneInfo(rec["tz_name"])
    allow_wknd = bool(rec.get("allow_weekend_trading", False))

    #2) This works to make sure "now" is the local time
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)
    now_local = now_utc.astimezone(tz)
    local_date = now_local.date()

    #2.5) Enforces closure on Sat/Sun
    weekday = now_local.weekday()
    is_weekend = weekday >= 5

    #3) This should look for date meant for markey closure
    override = db_get_market_closure_for_date(local_date)

    #Starts with the base hours (reg day) as the effective hours
    eff_open = rec["open_time"]
    eff_close = rec["close_time"]

    #4) If override equals a day to be closed this should hit
    if override is not None:
        if override ["is_closed"]:
            #Closes the market regardless of the time for that day
            return {
                "is_open": False,
                "now_local": now_local.isoformat(),
                "open_time": eff_open,
                "close_time": eff_close,
                "tz_name": rec["tz_name"],
                "date": local_date.isoformat(),
                "override": override,
                "weekday": weekday,
                "is_weekend": is_weekend,
                "allow_weekend_trading": allow_wknd,
            }

        # Half-day / special hours: if provided, replace effective hours
        if override.get("open_time"):
            eff_open = override["open_time"]
        if override.get("close_time"):
            eff_close = override["close_time"]

    if is_weekend and not allow_wknd:
        return {
            "is_open": False,
            "now_local": now_local.isoformat(),
            "open_time": eff_open,
            "close_time": eff_close,
            "tz_name": rec["tz_name"],
            "date": local_date.isoformat(),
            "override": override,
            "weekday": weekday,
            "is_weekend": is_weekend,
            "allow_weekend_trading": allow_wknd,
        }

    #5)This now replace what is in the comments to still enforce open hours
    openHour, openMinute = map(int, eff_open.split(":"))
    closeHour, closeMinute = map(int, eff_close.split(":"))

    open_dt = now_local.replace(hour=openHour, minute=openMinute, second=0, microsecond=0)
    close_dt = now_local.replace(hour=closeHour, minute=closeMinute, second=0, microsecond=0)

    open_flag = (open_dt <= now_local <= close_dt)

    return {
        "is_open": open_flag,
        "now_local": now_local.isoformat(),
        "open_time": eff_open,
        "close_time": eff_close,
        "tz_name": rec["tz_name"],
        "date": local_date.isoformat(),
        "override": override,
        "weekday": weekday,
        "is_weekend": is_weekend,
        "allow_weekend_trading": allow_wknd,
    }

def require_market_open(allow_admin_weekend: bool = True):
    status = is_market_open()
    if status["is_open"]:
        return

    if allow_admin_weekend and status.get("is_weekend"):
        u = get_current_user()
        if u and (u.get("role") or "").lower() == "admin":
            return
        #This pops up in the frontend if the market is closed.
    raise PermissionError({"detail": "Market is closed!", "market": status})

# ----------------------------------------- STOCK PRICE CHANGE HELPERS (This may change)---------------------------------------
# --- Price step config (from Kayla's idea) ---
MIN_PRICE = 1.00
STEP_MIN = 0.05        # 5%
STEP_MAX = 0.08        # 8%
INTERVAL_MINUTES = 15  # how often prices are allowed to change

def _rand_step_with_none():
    """
    Should return a multiplier for the price: price + none, price + percentPrice, or price - percentPrice,
    where percentPrice is uniform between STEP_MIN and STEP_MAX.
    """

    roll = random.random()
    if roll < (1/3):
        return 1.0
    elif roll < (2/3):
        pct = random.uniform(STEP_MIN, STEP_MAX)
        return 1.0 + pct
    else:
        pct = random.uniform(STEP_MIN, STEP_MAX)
        return max(1.0 - pct, 0.0)

def ticker_due_prices() -> int:
    """
    For each stock where at least INTERVAL_MINUTES have passed since last_price_update,
    apply at most one step (up/down/none), enforce a price floor, and stamp last_price_update.
    Concurrency-safe via FOR UPDATE SKIP LOCKED.
    """
    now = datetime.now(timezone.utc)
    threshold = now - timedelta(minutes=INTERVAL_MINUTES)
    changed = 0

    conn = get_db_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                # 1) Read candidates that LOOK due using a Python-computed threshold
                cur.execute("""
                    SELECT ticker, current_price
                    FROM stocks
                    WHERE is_listed = TRUE
                      AND (last_price_update IS NULL
                           OR last_price_update <= %s)
                """, (threshold,))
                due_rows = cur.fetchall()

                for ticker, current_price in due_rows:
                    price = float(current_price or 0.0)
                    if price < MIN_PRICE:
                        price = MIN_PRICE

                    # choose none / up / down (≈1/3 each)
                    roll = random.random()
                    if roll < (1/3):
                        new_price = round(max(MIN_PRICE, price), 2)  # none
                    else:
                        pct = random.uniform(STEP_MIN, STEP_MAX)
                        if roll < (2/3):
                            new_price = round(max(MIN_PRICE, price * (1 + pct)), 2) #up
                        else:
                            new_price = round(max(MIN_PRICE, price * (1 - pct)), 2) #down

                    # 2) Update price + O/H/L in one atomic UPDATE
                    #    - If this is the first tick of the day (date changed or last_ohl_date is NULL),
                    #      set open=high=low=new_price and stamp last_ohl_date = CURRENT_DATE.
                    #    - Otherwise, expand high/low with the new price.   #

                    cur.execute("""
                        UPDATE stocks
                           SET
                             previous_price     = CASE WHEN current_price <> %s THEN current_price ELSE previous_price END,
                             current_price      = %s,
                             last_price_update  = %s,


                             -- O/H/L maintenance (null-safe compare with IS DISTINCT FROM)
                             open_price         = CASE
                                                    WHEN (last_ohl_date IS DISTINCT FROM CURRENT_DATE) OR open_price IS NULL
                                                      THEN %s
                                                    ELSE open_price
                                                  END,
                             day_high           = CASE
                                                     WHEN (last_ohl_date IS DISTINCT FROM CURRENT_DATE) OR day_high IS NULL
                                                      THEN %s
                                                    ELSE GREATEST(day_high, %s)
                                                  END,
                             day_low            = CASE
                                                    WHEN (last_ohl_date IS DISTINCT FROM CURRENT_DATE) OR day_low IS NULL
                                                      THEN %s
                                                    ELSE LEAST(day_low, %s)
                                                  END,
                             -- set last_ohl_date ONCE at the end
                             last_ohl_date      = CURRENT_DATE
                         WHERE ticker = %s
                           AND (last_price_update IS NULL OR last_price_update <= %s)
                    """, (
                        new_price,                 # previous_price CASE compare target
                        new_price, now,            # current_price, last_price_update
                        new_price,                 # open reset value
                        new_price, new_price,      # high reset, high expand
                        new_price, new_price,      # low reset,  low expand
                        ticker, threshold
                    ))

                    if cur.rowcount:
                        if new_price != price:
                            changed += 1

                return changed
    finally:
        conn.close()
#  ----------------------------------------- END STOCK PRICE CHANGE HELPERS ---------------------------------------


app = Flask(__name__)

def _price_daemon_loop():
    LOCK_KEY = 424242  # any bigint
    while True:
        try:
            if is_market_open()["is_open"]:
                # single-leader using advisory lock
                conn = get_db_connection()
                got_lock = False
                try:
                    with conn:
                        with conn.cursor() as cur:
                            cur.execute("SELECT pg_try_advisory_lock(%s);", (LOCK_KEY,))
                            got_lock = bool(cur.fetchone()[0])
                    if got_lock:
                        try:
                            ticker_due_prices()
                        finally:
                            with conn:
                                with conn.cursor() as cur:
                                    cur.execute("SELECT pg_advisory_unlock(%s);", (LOCK_KEY,))
                finally:
                    conn.close()
        except Exception as e:
            try:
                app.logger.warning(f"price daemon error: {e}")
            except Exception:
                pass
        time_module.sleep(60)  # check once per minute

def _start_price_daemon_once():
    if getattr(app, "_price_daemon_started", False):
        return
    app._price_daemon_started = True
    t = threading.Thread(target=_price_daemon_loop, name="price-daemon", daemon=True)
    t.start()

_start_price_daemon_once()

# Allow your Amplify frontend (set to your exact Amplify URL)
AMPLIFY_ORIGIN = os.getenv("AMPLIFY_ORIGIN", "https://main.d2bmkzvarvu1na.amplifyapp.com")
CORS(app, resources={r"/*": {"origins": [AMPLIFY_ORIGIN, "http://localhost:5173", "http://127.0.0.1:5173"]}}, supports_credentials=True, allow_headers=["Content-Type", "Authorization"], expose_headers=["Content-Type", "Authorization"], methods=["GET", "POST", "OPTIONS"])

# ---- Demo in-memory "DB" ----
USERS = {}      # username -> {password, full_name, email, role}
BALANCES = {}   # username -> float

USERS["mcamac38"] = {
    "password": "Finishthis",
    "full_name": "Matthew Camacho",
    "email": "mcamac38@asu.edu",
    "role": "admin"
}
BALANCES["mcamac38"] = 10000.0

@app.route("/")
def home():
    return jsonify({
        "message": "Stock Trader API is running",
        "endpoints": ["/health", "/dbcheck", "/auth/register", "/auth/login", "/account", "/cash/deposit"]
    })

@app.route("/health")
def health():
    return jsonify({"status": "ok", "host": socket.gethostname()})

@app.route("/dbcheck")
def dbcheck():
    if psycopg2 is None:
        return jsonify(ok=False, error="psycopg2 not installed"), 500
    try:
        conn = psycopg2.connect(
            host=os.getenv("DATABASE_HOST"),
            port=os.getenv("DATABASE_PORT", "5432"),
            dbname=os.getenv("DATABASE_NAME", "postgres"),
            user=os.getenv("DATABASE_USER"),
            password=os.getenv("DATABASE_PASSWORD"),
            connect_timeout=3,
        )
        with conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1;")
                result = cur.fetchone()[0]
                return jsonify(ok=True, result=result)
    except Exception as e:
        return jsonify(ok=False, error=str(e)), 500

# ------------------------------ Auth helpers ------------------------------
def get_current_user():
    """Extract current user from Authorization: Bearer <token>.
       Supports JWT (preferred) and legacy 'username as token' fallback."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    raw = auth.split(" ", 1)[1].strip()
    if not raw:
        return None

    # Try JWT first
    try:
        payload = jwt.decode(raw, JWT_SECRET, algorithms=[JWT_ALG])
        username = payload.get("sub")
        if not username:
            return None
        u = db_get_user_by_username(username)
        if not u:
            return None
        return {
            "id": u["id"],
            "username": u["username"],
            "email": u["email"],
            "full_name": u["full_name"],
            "role": u["role"],
        }
    except Exception:
        # Fallback: legacy demo token == username
        username = raw
        u = db_get_user_by_username(username)
        if not u:
            return None
        return {
            "id": u["id"],
            "username": u["username"],
            "email": u["email"],
            "full_name": u["full_name"],
            "role": u["role"],
        }

#def ensure_account(conn, user_id):
#   with conn.cursor() as cur:
#        cur.execute("""
#           INSERT INTO accounts (user_id, cash_balance)
#            VALUES (%s, 0)
#            ON CONFLICT (user_id) DO NOTHING;
#        """, (user_id,))

#def get_balance_db(conn, user_id):
#    with conn.cursor() as cur:
#        cur.execute("SELECT cash_balance FROM accounts WHERE user_id = %s;", (user_id,))
#        row = cur.fetchone()
#        return float(row[0]) if row else 0.0

#def deposit_db(conn, user_id, amount):
#    with conn.cursor() as cur:
#        # ensure row exists
#        cur.execute("""
#            INSERT INTO accounts (user_id, cash_balance)
#            VALUES (%s, 0)
#            ON CONFLICT (user_id) DO NOTHING;
#        """, (user_id,))
#        # add amount
#        cur.execute("""
#            UPDATE accounts
#            SET cash_balance = cash_balance + %s
#            WHERE user_id = %s
#            RETURNING cash_balance;
#        """, (amount, user_id))
#       return float(cur.fetchone()[0])

#def withdraw_db(conn, user_id, amount):
#    with conn.cursor() as cur:
#        # ensure row exists
#        cur.execute("""
#            INSERT INTO accounts (user_id, cash_balance)
#            VALUES (%s, 0)
#            ON CONFLICT (user_id) DO NOTHING;
#        """, (user_id,))
#        # subtract only if enough funds
#        cur.execute("""
#           UPDATE accounts
#            SET cash_balance = cash_balance - %s
#           WHERE user_id = %s AND cash_balance >= %s
#            RETURNING cash_balance;
#       """, (amount, user_id, amount))
#        row = cur.fetchone()
#        if not row:
#            return None  # insufficient funds
#        return float(row[0])

# --- ------------------------------- Auth endpoints ----------------------------------
@app.route("/auth/register", methods=["POST"])
def register():
    body = request.get_json(force=True) or {}
    full_name = (body.get("full_name") or "").strip()
    username  = (body.get("username")  or "").strip()
    email     = (body.get("email")     or "").strip()
    password  = (body.get("password")  or "")

    if not username or not username or not email or not password:
        return jsonify({"detail": "All fields are required"}), 400

    try:
        user =db_create_user(full_name, username, email, password, role="user")
        token = make_token(user["username"])
        return jsonify({"access_token": token, "token_type": "bearer"}), 201
    except ValueError as ve:
        return jsonify({"detail": str(ve)}), 400
    except Exception as e:
        return jsonify({"detail": f"Registration failed: {e}"}), 500

@app.route("/auth/login", methods=["POST"])
def login():
    body = request.get_json(force=True) or {}
    username = (body.get("username") or "").strip()
    password = (body.get("password") or "")
    u = db_get_user_by_username(username)
    if not u:
        return jsonify({"detail": "Invalid credentials"}), 401

    if not check_password_hash(u["password_hash"], password):
        return jsonify({"detail": "Invalid credentials"}), 401

    token = make_token(username)
    return jsonify({"access_token": token, "token_type": "bearer"})

# ---------------------------------- Protected endpoints ----------------------------------
@app.route("/account", methods=["GET"])
def account():
    user = get_current_user()
    if not user:
        return jsonify({"detail": "Not authenticated"}), 401
    try:
        conn = get_db_connection()
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT cash_balance FROM users WHERE id = %s LIMIT 1;",
                    (user["id"],)
                )
                row = cur.fetchone()
                balance = float(row[0]) if row and row[0] is not None else 0.0
        return jsonify({
            "username":  user["username"],
            "full_name": user["full_name"],
            "email":     user["email"],
            "role":      user["role"],
            "cash_balance": balance,
        })
    except Exception as e:
        return jsonify({"detail": str(e)}), 500

@app.route("/transactions", methods=["GET"])
def get_transactions():
    """
    This will return the list of transactions of the current user order from newest to oldest

    Should be GET /transactions?type=buy|sell|deposit|withdraw||all&symbol=AAPL
    """
    user = get_current_user()
    if not user:
        return jsonify({"detail": "Not Authenticated"}), 401

    #this reads the filters from the query string
    raw_type = (request.args.get("type") or "") .strip().lower()
    #treats all  or empty as having no filter
    if raw_type in ("", "all"):
        tx_type = None
    else:
        tx_type = raw_type

    symbol = (
        request.args.get("symbol")
        or request.args.get("ticker")
        or ""
    ).strip().upper()
    ticker = symbol or None

    try:
        items = db_list_transactions(
            user_id=user["id"],
            tx_type=tx_type,
            ticker=ticker,
        )
        return jsonify(items), 200

    except Exception as e:
        return jsonify({"detail": str(e)}), 500

@app.route("/cash/deposit", methods=["POST"])
def cash_deposit():
    user = get_current_user()
    if not user:
        return jsonify({"detail": "Not authenticated"}), 401

    body = request.get_json(force=True) or {}
    try:
        amount = float(body.get("amount", 0))
    except (TypeError, ValueError):
        amount = 0.00

    if amount <= 0:
        return jsonify({"detail": "Amount must be > 0"}), 400

    try:
        new_balance = db_deposit(user["id"], amount)  # <-- use users-table helper

        try:
            conn = get_db_connection()
            with conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO transactions (
                            user_id, type, ticker, quantity, price, total_value
                        )
                        VALUES (%s, 'deposit', NULL, NULL, NULL, %s);
                    """, (user["id"], amount))
        except Exception:
            pass

        return jsonify({"ok": True, "new_balance": new_balance})
    except Exception as e:
        return jsonify({"detail": str(e)}), 500

@app.route("/cash/withdraw", methods=["POST"])
def cash_withdraw():
    user = get_current_user()
    if not user:
        return jsonify({"detail": "Not Authenticated"}), 401

    body = request.get_json(force=True) or {}
    try:
        amount = float(body.get("amount", 0))
    except (TypeError, ValueError):
        amount = 0.00

    if amount <= 0:
        return jsonify({"detail": "Amount must be > 0"}), 400

    try:
        new_balance = db_withdraw(user["id"], amount)  # <-- use users-table helper

        try:
            conn = get_db_connection()
            with conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO transactions (
                            user_id, type, ticker, quantity, price, total_value
                        )
                        VALUES (%s, 'withdraw', NULL, NULL, NULL, %s);
                    """, (user["id"], amount))
        except Exception:
            # Optional: log this somewhere; don't interrupt the withdraw
            pass

        return jsonify({"ok": True, "new_balance": new_balance})
    except ValueError as ve:
        # raised by db_withdraw on insufficient funds
        return jsonify({"detail": str(ve)}), 400
    except Exception as e:
        return jsonify({"detail": str(e)}), 500

@app.route("/trade/buy", methods=["POST"])
def place_order():
    """
    POST body: { "ticker": "ACME", "side": "buy", "quantity": 1 }
    Only 'buy' is implemented for now.
    Returns: { ticker, price, quantity, total_value, new_cash_balance }
    """
    user = get_current_user()
    if not user:
        return jsonify({"detail": "Not authenticated"}), 401

    body = request.get_json(force=True) or {}
    ticker = (body.get("ticker") or "").strip().upper()
    side = (body.get("side") or "").strip().lower()
    qty_raw = body.get("quantity")

    # Basic validation
    try:
        quantity = int(qty_raw)
    except (TypeError, ValueError):
        quantity = 0

    if not ticker:
        return jsonify({"detail": "Ticker is required"}), 400
    if side != "buy":
        return jsonify({"detail": "Only 'buy' is supported at this time"}), 400
    if quantity <= 0:
        return jsonify({"detail": "Quantity must be a positive integer"}), 400

    #This is what will enforce market hours on the buy page...you can also use it on the sell page
    try:
        require_market_open()
    except PermissionError as pe:
        payload = pe.args[0] if pe.args else {"detail": "Market is closed. Go home Rodger!"}
        return jsonify(payload), 403

    try:
        ticker_due_prices()
    except Exception as e:
        app.logger.warning(f"ticker_due_prices failed: {e}")

    try:
        conn = get_db_connection()
        with conn:
            with conn.cursor() as cur:
                # 1) Get current price for ticker (must be listed)
                cur.execute("""
                    SELECT current_price
                    FROM stocks
                    WHERE ticker = %s AND is_listed = TRUE
                    LIMIT 1;
                """, (ticker,))
                row = cur.fetchone()
                if not row:
                    return jsonify({"detail": f"Ticker {ticker} not found or not listed"}), 404
                price = float(row[0])
                total_value = round(price * quantity, 2)

                # 2) Deduct cash if enough balance (atomic guard)
                cur.execute("""
                    UPDATE users
                       SET cash_balance = cash_balance - %s
                     WHERE id = %s
                       AND cash_balance >= %s
                 RETURNING cash_balance;
                """, (total_value, user["id"], total_value))
                row = cur.fetchone()
                if not row:
                    # rollback happens automatically on leaving the 'with conn' if exception is raised
                    return jsonify({"detail": "Insufficient funds"}), 400
                new_cash_balance = float(row[0])

                # 3) Upsert position (recompute average cost)
                #    avg_cost' = (old_qty*old_avg + qty*price) / (old_qty + qty)
                #    Handle first-buy case by COALESCE.
                cur.execute("""
                    INSERT INTO user_positions (user_id, ticker, quantity, avg_cost)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (user_id, ticker) DO UPDATE
                    SET quantity = user_positions.quantity + EXCLUDED.quantity,
                        avg_cost = ROUND(
                            (
                              (user_positions.quantity * user_positions.avg_cost)
                              + (EXCLUDED.quantity * EXCLUDED.avg_cost)
                            ) / NULLIF(user_positions.quantity + EXCLUDED.quantity, 0)
                        , 2),
                        updated_at = now()
                    RETURNING quantity, avg_cost;
                """, (user["id"], ticker, quantity, price))
                pos_row = cur.fetchone()
                new_qty = float(pos_row[0]) if pos_row else quantity
                new_avg = float(pos_row[1]) if pos_row else price

                # 4) Insert transaction record
                cur.execute("""
                    INSERT INTO transactions (
                        user_id, type, ticker, quantity, price, total_value
                    )
                    VALUES (%s, 'buy', %s, %s, %s, %s)
                    RETURNING id;
                """, (user["id"], ticker, quantity, price, total_value))
                _tx_id = cur.fetchone()[0]

        # Success response
        return jsonify({
            "ticker": ticker,
            "price": price,
            "quantity": quantity,
            "total_value": total_value,
            "new_cash_balance": new_cash_balance,
            "position": {"quantity": new_qty, "avg_cost": new_avg}
        }), 201

    except Exception as e:
        return jsonify({"detail": str(e)}), 500

#--- THIS IS THE BEGINNING OF KAYLA TRADE SELL PUSH... IF IT DOENST WORK THEN DELETE ALL BELOW :)
@app.route("/trade/sell", methods=["POST"])
def trade_sell():
    """
    POST body: { "ticker": "ACME", "quantity": 1 }

    Behavior:
    - Uses current_price from stocks.
    - Requires valid JWT (same as /trade/buy).
    - Requires existing shares in user_positions.
    - Adds proceeds to users.cash_balance.
    - Updates or deletes user_positions row.
    - Logs row in transactions as type='sell'.
    """
    user = get_current_user()
    if not user:
        return jsonify({"detail": "Not authenticated"}), 401

    body = request.get_json(force=True) or {}
    ticker = (body.get("ticker") or "").strip().upper()
    qty_raw = body.get("quantity")

    # Basic validation
    try:
        quantity = int(qty_raw)
    except (TypeError, ValueError):
        quantity = 0

    if not ticker:
        return jsonify({"detail": "Ticker is required"}), 400
    if quantity <= 0:
        return jsonify({"detail": "Quantity must be a positive integer"}), 400

    # Enforce market hours (same behavior as buy)
    try:
        require_market_open()
    except PermissionError as pe:
        payload = pe.args[0] if pe.args else {"detail": "Market is closed"}
        return jsonify(payload), 403

    try:
        ticker_due_prices()
    except Exception as e:
        app.logger.warning(f"ticker_due_prices failed: {e}")

    try:
        conn = get_db_connection()
        with conn:
            with conn.cursor() as cur:
                # 1) Get existing position
                cur.execute("""
                    SELECT quantity, avg_cost
                    FROM user_positions
                    WHERE user_id = %s AND ticker = %s
                    LIMIT 1;
                """, (user["id"], ticker))
                pos = cur.fetchone()
                if not pos:
                    return jsonify({"detail": f"No position found for {ticker}"}), 400

                current_qty, avg_cost = pos
                if current_qty < quantity:
                    return jsonify({"detail": "Not enough shares to sell"}), 400

                # 2) Get current price from stocks
                cur.execute("""
                    SELECT current_price
                    FROM stocks
                    WHERE ticker = %s AND is_listed = TRUE
                    LIMIT 1;
                """, (ticker,))
                row = cur.fetchone()
                if not row:
                    return jsonify({"detail": f"Ticker {ticker} not found or not listed"}), 404

                price = float(row[0])
                total_value = round(price * quantity, 2)

                # 3) Add cash to user
                cur.execute("""
                    UPDATE users
                       SET cash_balance = cash_balance + %s
                     WHERE id = %s

                     RETURNING cash_balance;
                """, (total_value, user["id"]))
                bal_row = cur.fetchone()
                if not bal_row:
                    raise Exception("User not found while updating cash balance")
                new_cash_balance = float(bal_row[0])

                # 4) Update or delete position
                remaining_qty = current_qty - quantity
                if remaining_qty <= 0:
                    cur.execute("""
                        DELETE FROM user_positions
                        WHERE user_id = %s AND ticker = %s;
                    """, (user["id"], ticker))
                else:
                    cur.execute("""
                        UPDATE user_positions
                           SET quantity = %s,
                               updated_at = now()
                         WHERE user_id = %s AND ticker = %s;
                    """, (remaining_qty, user["id"], ticker))

                # 5) Log transaction as 'sell'
                cur.execute("""
                    INSERT INTO transactions (
                        user_id, type, ticker, quantity, price, total_value
                    )
                    VALUES (%s, 'sell', %s, %s, %s, %s)
                    RETURNING id;
                """, (user["id"], ticker, quantity, price, total_value))
                tx_id = cur.fetchone()[0]

        return jsonify({
            "ticker": ticker,
            "price": price,
            "quantity": quantity,
            "total_value": total_value,
            "new_cash_balance": new_cash_balance,
            "remaining_quantity": remaining_qty,
            "transaction_id": tx_id
        }), 201

    except Exception as e:
        return jsonify({"detail": f"Sell failed: {e}"}), 500
#-------THIS IS WHERE KAYLA'S WORK ENDS :)

@app.route("/portfolio", methods=["GET"])
def get_portfolio():
    """
    This will return the current user's portfolio information containing:

    {
      "cash_balance": 10000.00
      "portfolio_value": 2500.00
      "total_equity": 12500.00
      "holdings": [ticker: AAPL, quantity: 10, current_price: 120.50, total_value: 1205.00]
    """

    user = get_current_user()
    if not user:
        return jsonify({"detail": "Not Authenticated"}), 401

    try:
        conn= get_db_connection()
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT cash_balance
                          FROM users
                         WHERE id = %s
                         LIMIT 1;
                        """,
                        (user["id"],),
                    )
                    row = cur.fetchone()
                    cash_balance = float(row[0]) if row[0] is not None else 0.00
        finally:
            conn.close()

        # use the holding helper to get holdings
        holdings = db_get_user_holdings(user["id"])

        # computes the portfolio totals
        portfolio_value = sum(h["total_value"] for h in holdings)
        total_equity = cash_balance + portfolio_value

        return jsonify(
            {
                "cash_balance": cash_balance,
                "portfolio_value": portfolio_value,
                "total_equity": total_equity,
                "holdings": holdings,
            }
        )

    except Exception as e:
        return jsonify({"detail": str(e)}), 500

@app.route("/portfolio/history", methods=["GET"])
def get_portfolio_history():
    """
    Returns historical portfolio values for the current user.

    Query param:
      ?days=7  (optional, defaults to 7, max 90)
    """
    user = get_current_user()
    if not user:
        return jsonify({"detail": "Not authenticated"}), 401

    # Read 'days' from query string, with sane defaults
    raw_days = request.args.get("days", "7")
    try:
        days = int(raw_days)
    except ValueError:
        days = 7

    if days < 1:
        days = 1
    if days > 90:
        days = 90

    try:
        history = db_get_portfolio_history(user["id"], days)
        return jsonify({"history": history}), 200
    except Exception as e:
        return jsonify({"detail": str(e)}), 500

# ----------------------------------------------ADMIN ROUTES---------------------------------------------
@app.route("/admin/stocks", methods=["POST"])
def admin_create_stock():
    user = get_current_user()
    if not user:
        return jsonify({"detail": "Not Authenticated"}), 401

    #will restrict to admin only
    role = (user.get("role") or "").strip().lower()
    if user.get("role") !="admin":
        return jsonify({"detail": "Forbidden"}), 403

    body = request.get_json(force=True) or {}

    #required fields
    ticker = (body.get("ticker") or "").strip().upper()
    company_name = (body.get("company_name") or "").strip()
    try:
        current_price = float(body.get("current_price"))
    except (TypeError, ValueError):
        current_price = 0.0
    shares_outstanding = body.get("shares_outstanding")
    sector = (body.get("sector") or "").strip() or None
    is_listed = bool(body.get("is_listed", True))

    if not ticker or not company_name or current_price <= 0:
        return jsonify({"detail": "Ticker, company name, and positive current price required"}), 400

    try:
        conn = get_db_connection()
        with conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO stocks (ticker, company_name, current_price, shares_outstanding, sector, is_listed, created_by)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (ticker) DO UPDATE
                      SET company_name = EXCLUDED.company_name,
                          current_price = EXCLUDED.current_price,
                          shares_outstanding = COALESCE(EXCLUDED.shares_outstanding, stocks.shares_outstanding),
                          sector = COALESCE(EXCLUDED.sector, stocks.sector),
                          is_listed = EXCLUDED.is_listed,
                          created_by = EXCLUDED.created_by
                    RETURNING ticker, company_name, current_price, shares_outstanding, sector, is_listed;
                """, (ticker, company_name, float(current_price), shares_outstanding, sector, is_listed, user["id"]))
                t = cur.fetchone()

        return jsonify({
            "ticker": t[0],
            "company_name": t[1],
            "current_price": float(t[2]),
            "shares_outstanding": t[3],
            "sector": t[4],
            "is_listed": t[5],
            "created_by": user["username"]
        }), 201
    except Exception as e:
        return jsonify({"detail": str(e)}), 500

@app.route("/admin/market-hours", methods=["GET"])
def admin_get_market_hours():
    user = get_current_user()
    if not user:
        return jsonify({"detail": "Not Authenticated"}), 401
    role = (user.get("role") or "").strip().lower()
    if role != "admin":
        return jsonify({"detail": "Forbidden"}), 403

    rec = db_get_market_hours()
    return jsonify(rec), 200

@app.route("/admin/market-hours", methods=["PUT"])
def admin_update_market_hours():
    user = get_current_user()
    if not user:
        return jsonify({"detail": "Not Authenticated"}), 401
    role = (user.get("role") or "").strip().lower()
    if role != "admin":
        return jsonify({"detail": "Forbidden"}), 403

    body = request.get_json(force=True) or {}
    open_time = (body.get("open_time") or "").strip()
    close_time = (body.get("close_time") or "").strip()
    tz_name = (body.get("tz_name") or "").strip()
    allow_wknd = None

    if "allow_weekend_trading" in body:
        allow_wknd = bool(body.get("allow_weekend_trading"))

    if not open_time or not close_time:
        return jsonify({"detail": "open time and close times are required"}), 400

    try:
        updated = db_update_market_hours(open_time, close_time, tz_name, allow_wknd)
        return jsonify(updated), 200
    except ValueError as ve:
        return jsonify({"detail": str(ve)}), 400
    except Exception as e:
        return jsonify({"detail": str(e)}), 500

@app.route("/admin/market-schedule", methods=["GET"])
def admin_list_market_schedule():
    """
    Admin-only: return all date-specific closures/overrides from market_schedule_closures.
    """
    user = get_current_user()
    if not user:
        return jsonify({"detail": "Not Authenticated"}), 401

    role = (user.get("role") or "").strip().lower()
    if role != "admin":
        return jsonify({"detail": "Forbidden"}), 403

    try:
        rows = db_list_market_closures()
        return jsonify(rows), 200
    except Exception as e:
        return jsonify({"detail": str(e)}), 500

@app.route("/admin/market-schedule", methods=["PUT"])
def admin_upsert_market_schedule():
    """
    Admin-only: create or update a single closure/override date.
    Expects JSON like:
      {
        "close_date": "2025-12-25",  # YYYY-MM-DD
        "is_closed": true,           # full-day closed, OR
        "open_time": "09:30",        # optional HH:MM
        "close_time": "13:00",       # optional HH:MM
        "note": "Christmas (half day)"
      }
    """
    user = get_current_user()
    if not user:
        return jsonify({"detail": "Not Authenticated"}), 401

    role = (user.get("role") or "").strip().lower()
    if role != "admin":
        return jsonify({"detail": "Forbidden"}), 403
    body = request.get_json(force=True) or {}
    close_date = (body.get("close_date") or "").strip()
    if not close_date:
        return jsonify({"detail": "close_date (YYYY-MM-DD) is required"}), 400

    # Default is_closed to False if not provided
    is_closed = bool(body.get("is_closed", False))
    open_time = body.get("open_time")
    close_time = body.get("close_time")
    note = body.get("note")

    try:
        rec = db_upsert_market_closure(
            close_date_str=close_date,
            is_closed=is_closed,
            open_time_str=open_time,
            close_time_str=close_time,
            note=note,
        )
        return jsonify(rec), 200
    except ValueError as ve:
        # validation error from db_upsert_market_closure
        return jsonify({"detail": str(ve)}), 400
    except Exception as e:
        return jsonify({"detail": str(e)}), 500


#------This is used as a basline status return------
@app.route("/market/hours", methods=["GET"])
def public_get_market_hours():
    return jsonify(db_get_market_hours()), 200

@app.route("/market/status", methods=["GET"])
def market_status():
    # Uses your updated is_market_open() which now checks closures/half-days
    try:
        return jsonify(is_market_open()), 200
    except Exception as e:
        # Fallback to static hours so UI doesn't break
        hours = db_get_market_hours()
        tz_name = hours.get("tz_name", "America/New_York")
        try:
            now_local = datetime.now(ZoneInfo(tz_name)).isoformat()
        except Exception:
            now_local = datetime.now(timezone.utc).isoformat()
        safe = {
            "is_open": False,
            "now_local": now_local,
            "open_time": hours.get("open_time"),
            "close_time": hours.get("close_time"),
            "tz_name": hours.get("tz_name"),
            "date": date.today().isoformat(),
            "override": None,
            "detail": str(e),
        }
        # Return 200 so frontend renders; keep detail for troubleshooting
        return jsonify(safe), 200

# -------------------------- OPERATIONAL ENDPOINTS -------------------------

@app.route("/market/tickers", methods=["GET"])
def list_tickers():
    """
    Returns a simple list of tradable tickers.
    Example item:
    { "ticker":"ACME", "company_name":"Acme Corp", "current_price": 99.99 }
    """

    try:
        # Try to tick prices; even if it fails we still return the list
        try:
            if is_market_open()["is_open"]:
                ticker_due_prices()
        except Exception as e:
            print("ticker_due_prices error:", e)

        conn = get_db_connection()
        with conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT
                      ticker,
                      company_name,
                      current_price,
                      volume,
                      open_price,
                      day_high,
                      day_low,
                      shares_outstanding,
                      COALESCE(shares_outstanding, 0) * current_price AS market_cap
                    FROM stocks
                    WHERE is_listed = TRUE
                    ORDER BY ticker ASC
                    LIMIT 500
                """)
                rows = cur.fetchall()

        data = [
            {
                "ticker": r[0],
                "company_name": r[1],
                "current_price": float(r[2]) if r[2] is not None else None,
                "volume": int(r[3]) if r[3] is not None else 0,
                "open_price": float(r[4]) if r[4] is not None else None,
                "day_high": float(r[5]) if r[5] is not None else None,
                "day_low": float(r[6]) if r[6] is not None else None,
                "shares_outstanding": int(r[7]) if r[7] is not None else None,
                "market_cap": float(r[8]) if r[8] is not None else 0.0,
            }
            for r in rows
        ]
        return jsonify(data)
    except Exception as e:
        return jsonify({"detail": str(e)}), 500

@app.route("/market/tickers/<ticker>", methods=["GET"])
def get_ticker(ticker):

    try:
        #New: bring any symbols up-to-date before reading/this might be changed if Kayla can get orginal code fully operational
        if is_market_open()["is_open"]:
            ticker_due_prices()

    except Exception as e:
        print("ticker due prices error:", e)

    ticker = (ticker or "").strip().upper()
    if not ticker:
        return jsonify({"detail": "ticker required"}), 400
    try:
        conn = get_db_connection()
        with conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT ticker, company_name, current_price, volume, sector, is_listed, created_by, created_at
                    FROM stocks
                    WHERE ticker = %s
                """, (ticker,))
                row = cur.fetchone()
        conn.close()

        if not row:
            return jsonify({"detail": "Not found"}), 404

        return jsonify({
            "ticker": row[0],
            "company_name": row[1],
            "current_price": float(row[2]),
            "volume": row[3],
            "sector": row[4],
            "is_listed": row[5],
            "created_by": row[6],
            "created_at": row[7].isoformat() if row[7] else None
        })
    except Exception as e:
        return jsonify({"detail": str(e)}), 500

# ADD: 7-day (or N-day) price history for a ticker
@app.route("/market/tickers/<ticker>/history", methods=["GET"])
def get_ticker_history(ticker):
    """
    Returns a simple daily close series for the past N days (default 7).
    Shape: [ { "date": "YYYY-MM-DD", "close": 123.45 }, ... ]
    For now this is simulated from current_price (deterministic per day+ticker).
    """
    try:
        from datetime import date, timedelta
        import hashlib, random

        t = (ticker or "").strip().upper()
        if not t:
            return jsonify({"detail": "ticker required"}), 400

        # days query param (1..60), default 7
        try:
            days = int(request.args.get("days", 7))
        except Exception:
            days = 7
        days = max(1, min(60, days))

        # 1) get the latest/current price
        conn = get_db_connection()
        with conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT current_price
                      FROM stocks
                     WHERE ticker = %s AND is_listed = TRUE
                     LIMIT 1;
                """, (t,))
                row = cur.fetchone()
        conn.close()

        if not row:
            return jsonify({"detail": f"{t} not found or not listed"}), 404

        base_price = float(row[0])
        # Floor at zero to be safe
        if base_price < 0:
            base_price = 0.0

        # 2) build deterministic N-day series that ends at base_price (today)
        # We walk backwards so the last day (today) is exactly base_price.
        today = date.today()
        prices = [0.0] * days
        prices[-1] = base_price

        for i in range(days - 2, -1, -1):
            day = today - timedelta(days=(days - 1 - i))
            # deterministic seed from (ticker, day)
            seed_str = f"{t}-{day.isoformat()}"
            h = hashlib.sha256(seed_str.encode("utf-8")).hexdigest()
            rnd = int(h[:8], 16) / 0xFFFFFFFF  # 0..1
            # daily change in [-3%, +3%]
            delta = (rnd * 0.06) - 0.03
            scale = 1.0 + delta
            if scale <= 0.0001:
                scale = 0.0001  # guard against pathological scaling
            prev_price = prices[i + 1] / scale
            # never below zero
            prices[i] = max(0.0, prev_price)

        # 3) format response (oldest -> newest), round to cents
        items = []
        for i in range(days):
            d = (today - timedelta(days=(days - 1 - i))).isoformat()
            # y-axis should never dip below 0 in the client; we also clamp here
            close_val = round(max(0.0, prices[i]), 2)
            items.append({"date": d, "close": close_val})

        # Return just the array for easy client use
        return jsonify(items)
    except Exception as e:
        return jsonify({"detail": str(e)}), 500

if __name__ == "__main__":
    # Only used if you run app.py directly; systemd runs gunicorn
    from os import getenv
    app.run(host="0.0.0.0", port=int(getenv("PORT", "8000")))