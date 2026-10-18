import sqlite3
import os

db_path = os.path.join("instance", "cems.db")
print("Opening database:", db_path)
con = sqlite3.connect(db_path)
cur = con.cursor()

# Get existing columns of event
cur.execute("PRAGMA table_info(event)")
event_cols = [row[1] for row in cur.fetchall()]
print("Current event columns:", event_cols)

if "event_type" not in event_cols:
    cur.execute("ALTER TABLE event ADD COLUMN event_type VARCHAR(20) DEFAULT 'Individual'")
    print("Added event.event_type")

if "min_team_size" not in event_cols:
    cur.execute("ALTER TABLE event ADD COLUMN min_team_size INTEGER DEFAULT 1")
    print("Added event.min_team_size")

if "max_team_size" not in event_cols:
    cur.execute("ALTER TABLE event ADD COLUMN max_team_size INTEGER DEFAULT 1")
    print("Added event.max_team_size")

# Get existing columns of registration
cur.execute("PRAGMA table_info(registration)")
reg_cols = [row[1] for row in cur.fetchall()]
print("Current registration columns:", reg_cols)

if "participation_type" not in reg_cols:
    cur.execute("ALTER TABLE registration ADD COLUMN participation_type VARCHAR(20) DEFAULT 'Individual'")
    print("Added registration.participation_type")

if "team_name" not in reg_cols:
    cur.execute("ALTER TABLE registration ADD COLUMN team_name VARCHAR(120) DEFAULT ''")
    print("Added registration.team_name")

if "team_size" not in reg_cols:
    cur.execute("ALTER TABLE registration ADD COLUMN team_size INTEGER DEFAULT 1")
    print("Added registration.team_size")

if "team_members" not in reg_cols:
    cur.execute("ALTER TABLE registration ADD COLUMN team_members TEXT DEFAULT ''")
    print("Added registration.team_members")

if "phone" not in reg_cols:
    cur.execute("ALTER TABLE registration ADD COLUMN phone VARCHAR(30) DEFAULT ''")
    print("Added registration.phone")

con.commit()
con.close()
print("Migration completed successfully.")
