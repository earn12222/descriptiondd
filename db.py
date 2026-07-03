import sqlite3
from datetime import datetime

DB_FILE = "ludoman_game.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Players table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS players (
        id INTEGER PRIMARY KEY,
        username TEXT,
        fullname TEXT,
        balance REAL DEFAULT 1000.0,
        daily_claimed_at TEXT,
        loan_amount REAL DEFAULT 0.0,
        loan_taken_at TEXT,
        level INTEGER DEFAULT 1,
        xp INTEGER DEFAULT 0
    )
    """)
    
    # Businesses table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS player_businesses (
        player_id INTEGER PRIMARY KEY,
        kripto_ferma INTEGER DEFAULT 0,
        tungi_klub INTEGER DEFAULT 0,
        yashirin_kazino INTEGER DEFAULT 0,
        last_collected_at TEXT,
        FOREIGN KEY(player_id) REFERENCES players(id)
    )
    """)
    
    conn.commit()
    conn.close()

def get_or_create_player(player_id, username, fullname):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute("SELECT id, username, fullname, balance, daily_claimed_at, loan_amount, loan_taken_at, level, xp FROM players WHERE id = ?", (player_id,))
    player = cursor.fetchone()
    
    if not player:
        # Create player
        cursor.execute("""
        INSERT INTO players (id, username, fullname, balance)
        VALUES (?, ?, ?, 1000.0)
        """, (player_id, username, fullname))
        
        # Create business entry
        cursor.execute("""
        INSERT INTO player_businesses (player_id, last_collected_at)
        VALUES (?, ?)
        """, (player_id, datetime.now().isoformat()))
        
        conn.commit()
        
        cursor.execute("SELECT id, username, fullname, balance, daily_claimed_at, loan_amount, loan_taken_at, level, xp FROM players WHERE id = ?", (player_id,))
        player = cursor.fetchone()
        
    conn.close()
    
    return {
        "id": player[0],
        "username": player[1],
        "fullname": player[2],
        "balance": player[3],
        "daily_claimed_at": player[4],
        "loan_amount": player[5],
        "loan_taken_at": player[6],
        "level": player[7],
        "xp": player[8]
    }

def update_balance(player_id, amount):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("UPDATE players SET balance = balance + ? WHERE id = ?", (amount, player_id))
    conn.commit()
    conn.close()

def update_xp(player_id, amount):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Get current xp and level
    cursor.execute("SELECT xp, level FROM players WHERE id = ?", (player_id,))
    row = cursor.fetchone()
    xp, level = row[0], row[1]
    
    new_xp = xp + amount
    # Level formula: level * 100 xp needed for next level
    xp_needed = level * 100
    new_level = level
    
    while new_xp >= xp_needed:
        new_xp -= xp_needed
        new_level += 1
        xp_needed = new_level * 100
        
    cursor.execute("UPDATE players SET xp = ?, level = ? WHERE id = ?", (new_xp, new_level, player_id))
    conn.commit()
    conn.close()
    return new_level > level # Returns True if leveled up

def claim_daily(player_id, amount):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
    UPDATE players 
    SET balance = balance + ?, daily_claimed_at = ? 
    WHERE id = ?
    """, (amount, datetime.now().isoformat(), player_id))
    conn.commit()
    conn.close()

def get_businesses(player_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT kripto_ferma, tungi_klub, yashirin_kazino, last_collected_at FROM player_businesses WHERE player_id = ?", (player_id,))
    biz = cursor.fetchone()
    conn.close()
    
    if not biz:
        return {"kripto_ferma": 0, "tungi_klub": 0, "yashirin_kazino": 0, "last_collected_at": None}
        
    return {
        "kripto_ferma": biz[0],
        "tungi_klub": biz[1],
        "yashirin_kazino": biz[2],
        "last_collected_at": biz[3]
    }

def buy_business(player_id, biz_type, cost):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Deduct cost
    cursor.execute("UPDATE players SET balance = balance - ? WHERE id = ?", (cost, player_id))
    
    # Upgrade business level (increase by 1)
    query = f"UPDATE player_businesses SET {biz_type} = {biz_type} + 1 WHERE player_id = ?"
    cursor.execute(query, (player_id,))
    
    conn.commit()
    conn.close()

def collect_passive_income(player_id):
    biz = get_businesses(player_id)
    if not biz["last_collected_at"]:
        return 0, "Hozircha daromad yo'q"
        
    last_collected = datetime.fromisoformat(biz["last_collected_at"])
    now = datetime.now()
    duration = now - last_collected
    hours = duration.total_seconds() / 3600.0
    
    # If less than 5 seconds, don't collect to prevent spamming
    if duration.total_seconds() < 5:
        return 0, "Daromad yig'ish uchun kamida 5 soniya kuting!"
        
    # Calculate total passive income
    # Kripto ferma: level * 50 / hour
    # Tungi klub: level * 300 / hour
    # Yashirin kazino: level * 2000 / hour
    income_rate = (biz["kripto_ferma"] * 50) + (biz["tungi_klub"] * 300) + (biz["yashirin_kazino"] * 2000)
    total_income = round(income_rate * hours, 2)
    
    if total_income > 0:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("UPDATE players SET balance = balance + ? WHERE id = ?", (total_income, player_id))
        cursor.execute("UPDATE player_businesses SET last_collected_at = ? WHERE player_id = ?", (now.isoformat(), player_id))
        conn.commit()
        conn.close()
        return total_income, f"Muvaffaqiyatli yig'ildi! Siz {total_income} $ passiv daromad oldingiz. 💰"
        
    return 0, "Yig'ish uchun hali yetarli mablag' yig'ilmadi!"

def take_loan(player_id, amount):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
    UPDATE players 
    SET balance = balance + ?, loan_amount = loan_amount + ?, loan_taken_at = ? 
    WHERE id = ?
    """, (amount, amount, datetime.now().isoformat(), player_id))
    conn.commit()
    conn.close()

def pay_loan(player_id, amount):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute("SELECT loan_amount FROM players WHERE id = ?", (player_id,))
    loan = cursor.fetchone()[0]
    
    pay_amount = min(amount, loan)
    
    cursor.execute("""
    UPDATE players 
    SET balance = balance - ?, loan_amount = loan_amount - ? 
    WHERE id = ?
    """, (pay_amount, pay_amount, player_id))
    
    # If loan is fully paid, clear the date
    cursor.execute("SELECT loan_amount FROM players WHERE id = ?", (player_id,))
    new_loan = cursor.fetchone()[0]
    if new_loan <= 0:
        cursor.execute("UPDATE players SET loan_taken_at = NULL WHERE id = ?", (player_id,))
        
    conn.commit()
    conn.close()
    return pay_amount

def get_leaderboard(limit=10):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
    SELECT fullname, username, balance, level 
    FROM players 
    ORDER BY balance DESC 
    LIMIT ?
    """, (limit,))
    rows = cursor.fetchall()
    conn.close()
    return rows
