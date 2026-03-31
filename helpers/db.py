import sqlite3


def save_matches(matches):
  # Connect to database (creates file if it doesn't exist)
  base_dir = os.path.dirname(os.path.abspath(__file__))
  db_path = os.path.join(base_dir,"../resources/db/matches.db")
  db_path = os.path.abspath(db_path)
  
  os.makedirs(os.path.dirname(db_path), exist_ok=True)

  conn = sqlite3.connect(db_path)
  conn.row_factory = sqlite3.Row
  cursor = conn.cursor()
  
  # Create table if it doesn't exist
  cursor.execute("""
  CREATE TABLE IF NOT EXISTS matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fixture TEXT,
    category TEXT,
    league TEXT,
    date TEXT,
    match_url TEXT,
    match_id TEXT
    )
    """)
    
  #delete all existing entries
  cursor.execute("""DELETE FROM matches""")
  conn.commit()

  # Insert new matches into the table
  for item in matches:
    cursor.execute("""
    INSERT INTO matches (fixture, category, league, date, match_url, match_id)
    VALUES (?, ?, ?, ?, ?, ?)
    """, (item["fixture"], item["category"], item["league"], item["date"], item["match_url"], item["match_id"]))

  # Save changes and close connection
  conn.commit()
  conn.close()
    
def get_matches():
  # Connect to database (creates file if it doesn't exist)
  conn = sqlite3.connect("../resources/db/my_database.db")
  conn.row_factory = sqlite3.Row
  cursor = conn.cursor()
  
  cursor.execute("SELECT * FROM matches")
  rows = cursor.fetchall()
  result = [dict(row) for row in rows]
  
  conn.close()
  return result