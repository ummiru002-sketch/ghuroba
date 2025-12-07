import sqlite3

def migrate():
    conn = sqlite3.connect('instance/ghuroba.db')
    cursor = conn.cursor()
    
    # 1. Add status column
    try:
        cursor.execute("ALTER TABLE 'transaction' ADD COLUMN status VARCHAR(20) DEFAULT 'approved'")
        print("Added status column.")
    except sqlite3.OperationalError as e:
        print(f"Status column might already exist: {e}")

    # 2. Add semester_id column
    try:
        cursor.execute("ALTER TABLE 'transaction' ADD COLUMN semester_id INTEGER REFERENCES semester(id)")
        print("Added semester_id column.")
    except sqlite3.OperationalError as e:
        print(f"Semester_id column might already exist: {e}")

    # 3. Update existing dues to have semester_id based on weekly_slot
    # We need to join with weekly_slot to get semester_id
    # SQLite update with join is tricky, often best to do in python loop for simple migration
    
    cursor.execute("SELECT t.id, w.semester_id FROM 'transaction' t JOIN weekly_slot w ON t.weekly_slot_id = w.id WHERE t.type = 'income_dues'")
    dues_updates = cursor.fetchall()
    
    for txn_id, sem_id in dues_updates:
        cursor.execute("UPDATE 'transaction' SET semester_id = ? WHERE id = ?", (sem_id, txn_id))
    print(f"Updated {len(dues_updates)} dues transactions with semester_id.")
    
    # 4. For expenses/donations, we might default to the currently active semester or the most recent one?
    # For now, let's look for an active semester
    cursor.execute("SELECT id FROM semester WHERE is_active = 1")
    active_sem = cursor.fetchone()
    if active_sem:
        active_sem_id = active_sem[0]
        # Update transactions that are NOT dues and have no semester_id
        cursor.execute("UPDATE 'transaction' SET semester_id = ? WHERE semester_id IS NULL", (active_sem_id,))
        print(f"Updated remaining transactions to default semester {active_sem_id}.")

    conn.commit()
    conn.close()

if __name__ == "__main__":
    migrate()
