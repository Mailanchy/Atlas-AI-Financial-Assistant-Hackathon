import sqlite3
import json

def init_db():
    print("\n---> [DATABASE] Initializing database and checking tables...")
    conn = sqlite3.connect('assistant.db')
    
    conn.execute("PRAGMA foreign_keys = ON;")
    cursor = conn.cursor()

    # 1. users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            telegram_id INTEGER PRIMARY KEY,
            onboarding_stage TEXT,
            role TEXT,
            briefing_time TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # 2. preferences table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS preferences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER,
            category TEXT,
            value TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(telegram_id) REFERENCES users(telegram_id) ON DELETE CASCADE
        )
    ''')

    # 3. integrations table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS integrations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER,
            service_name TEXT,
            status TEXT,
            auth_token TEXT,
            FOREIGN KEY(telegram_id) REFERENCES users(telegram_id) ON DELETE CASCADE
        )
    ''')

    # 4. chat_history table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER,
            sender TEXT,
            message TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(telegram_id) REFERENCES users(telegram_id) ON DELETE CASCADE
        )
    ''')

    # 5. memory table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER,
            fact_type TEXT,
            fact_content TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(telegram_id) REFERENCES users(telegram_id) ON DELETE CASCADE
        )
    ''')

    # 6. documents table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER,
            file_name TEXT,
            telegram_file_id TEXT,
            gemini_file_id TEXT,
            file_type TEXT,
            uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(telegram_id) REFERENCES users(telegram_id) ON DELETE CASCADE
        )
    ''')

    cursor.execute('CREATE INDEX IF NOT EXISTS idx_preferences_user ON preferences(telegram_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_history_user ON chat_history(telegram_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_memory_user ON memory(telegram_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_documents_user ON documents(telegram_id)')

    conn.commit()
    conn.close()
    print("---> [DATABASE] Database initialized successfully with 6 tables!")

# --- HELPER FUNCTIONS ---

def get_user_stage(user_id):
    """Inserts user if new, and returns their current onboarding stage."""
    conn = sqlite3.connect('assistant.db')
    cursor = conn.cursor()
    
    # 1. Insert them as 'new' if they don't exist yet (ignores if they do)
    cursor.execute('''
        INSERT OR IGNORE INTO users (telegram_id, onboarding_stage)
        VALUES (?, ?)
    ''', (user_id, 'new'))
    conn.commit()
    
    # 2. Fetch and return their current stage
    cursor.execute('SELECT onboarding_stage FROM users WHERE telegram_id = ?', (user_id,))
    stage = cursor.fetchone()[0]
    conn.close()
    
    print(f"---> [DATABASE DB] Fetched stage '{stage}' for User {user_id}")
    return stage

def update_user_stage(user_id, new_stage):
    """Updates the user's onboarding stage."""
    print(f"---> [DATABASE DB] Updating stage to '{new_stage}' for User {user_id}")
    conn = sqlite3.connect('assistant.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET onboarding_stage = ? WHERE telegram_id = ?', (new_stage, user_id))
    conn.commit()
    conn.close()

def save_user_preferences(user_id, extracted_data):
    """Saves the AI-extracted JSON data directly into the database, merging arrays safely."""
    print(f"\n---> [DATABASE] save_user_preferences triggered for User {user_id}")
    conn = sqlite3.connect('assistant.db')
    cursor = conn.cursor()

    # 1. Save standard string fields to the users table
    role = extracted_data.get('role')
    briefing_time = extracted_data.get('briefing_time')
    
    # Strings can safely overwrite older strings if the user updates them
    if role:
        print(f"---> [DATABASE] Saving single string: Role = '{role}'")
        cursor.execute('UPDATE users SET role = ? WHERE telegram_id = ?', (role, user_id))
    if briefing_time:
        print(f"---> [DATABASE] Saving single string: Briefing Time = '{briefing_time}'")
        cursor.execute('UPDATE users SET briefing_time = ? WHERE telegram_id = ?', (briefing_time, user_id))
        
    # 2. Save arrays to the preferences table (with Merge Logic)
    prefs = {
        'sectors': extracted_data.get('sectors'),
        'watchlist': extracted_data.get('watchlist'),
        'insight_types': extracted_data.get('insight_types'),
        'custom_alerts': extracted_data.get('custom_alerts')
    }
    
    for category, new_values in prefs.items():
        # Only process if the AI actually found new items (not None and not empty [])
        if new_values: 
            if isinstance(new_values, str):
                new_values = [new_values]
            print(f"---> [DATABASE] Processing Array for '{category}': {new_values}")
            # Check if they already have an existing array saved for this category
            cursor.execute('SELECT value FROM preferences WHERE telegram_id = ? AND category = ?', (user_id, category))
            existing_row = cursor.fetchone()
            
            if existing_row:
                # 1. Load the old list from the database
                existing_values = json.loads(existing_row[0])
                
                # 2. Combine old and new lists, use set() to remove duplicates, back to list
                merged_values = list(set(existing_values + new_values))
                val_str = json.dumps(merged_values)
                
                print(f"---> [DATABASE] Merged old and new '{category}'. Result: {val_str}")
                
                # 3. Update the database with the merged list
                cursor.execute('''
                    UPDATE preferences SET value = ?, updated_at = CURRENT_TIMESTAMP 
                    WHERE telegram_id = ? AND category = ?
                ''', (val_str, user_id, category))
            else:
                # If nothing existed yet, just insert the new array directly
                val_str = json.dumps(new_values)
                print(f"---> [DATABASE] Inserting NEW array for '{category}': {val_str}")
                cursor.execute('''
                    INSERT INTO preferences (telegram_id, category, value) 
                    VALUES (?, ?, ?)
                ''', (user_id, category, val_str))
                
    conn.commit()
    conn.close()
    print("---> [DATABASE] Save preferences complete.")


def save_chat_message(user_id, sender, message):
    """Saves a single message to the chat history."""
    print(f"---> [DATABASE] Saving chat message from '{sender}' for User {user_id}")
    conn = sqlite3.connect('assistant.db')
    cursor = conn.cursor()
    
    # sender should be either 'user' or 'assistant'
    cursor.execute('''
        INSERT INTO chat_history (telegram_id, sender, message)
        VALUES (?, ?, ?)
    ''', (user_id, sender, message))
    
    conn.commit()
    conn.close()

def get_recent_chat_history(user_id, limit=10):
    """Fetches the last N messages to give the AI short-term context."""
    print(f"---> [DATABASE] Fetching last {limit} messages for User {user_id}...")
    conn = sqlite3.connect('assistant.db')
    cursor = conn.cursor()
    
    # We order by timestamp DESC to get the newest, but then we must reverse them 
    # so they are in the correct chronological order for the LLM!
    cursor.execute('''
        SELECT sender, message FROM chat_history 
        WHERE telegram_id = ? 
        ORDER BY timestamp DESC LIMIT ?
    ''', (user_id, limit))
    
    rows = cursor.fetchall()
    conn.close()
    
    # Reverse the list so the oldest message is first, newest is last
    rows.reverse()
    
    # Format them into the dictionary structure that Groq/OpenAI expects
    formatted_history = []
    for row in rows:
        formatted_history.append({"role": row[0], "content": row[1]})
        
    print(f"---> [DATABASE] Retrieved {len(formatted_history)} historical messages.")
    return formatted_history

def save_memory_updates(user_id, memory_updates):
    """Saves dynamic facts and preferences to the memory table."""
    # If the LLM returned an empty array [], just skip it!
    if not memory_updates:
        return
        
    # Block core preference keys from contaminating the memory table
    FORBIDDEN_FACT_TYPES = {"role", "watchlist", "sectors", "insight_types", "briefing_time"}
        
    print(f"\n---> [DATABASE] Saving long-term memory updates for User {user_id}...")
    conn = sqlite3.connect('assistant.db')
    cursor = conn.cursor()
    
    for item in memory_updates:
        # Convert to lowercase to safely catch "Role" or "ROLE"
        fact_type = item.get("fact_type", "general").lower() 
        fact_content = item.get("fact_content")
        
        # 🛡️ THE FIX: Ignore if the AI mistakenly tagged a core setting as a memory
        if fact_type in FORBIDDEN_FACT_TYPES:
            print(f"---> [DATABASE] Skipped saving '{fact_type}' to memory table (handled by preferences/users).")
            continue
        
        # Only save if there is actual text content
        if fact_content:
            print(f"---> [DATABASE] Memory saved: [{fact_type}] - {fact_content}")
            cursor.execute('''
                INSERT INTO memory (telegram_id, fact_type, fact_content)
                VALUES (?, ?, ?)
            ''', (user_id, fact_type, fact_content))
            
    conn.commit()
    conn.close()


def get_user_profile(user_id):
    """Fetches the user's role, preferences, AND dynamic memories into a single dictionary."""
    print(f"\n---> [DATABASE] Fetching Master Profile for User {user_id}...")
    conn = sqlite3.connect('assistant.db')
    cursor = conn.cursor()
    
    profile = {}
    
    # 1. Get role
    cursor.execute('SELECT role FROM users WHERE telegram_id = ?', (user_id,))
    user_row = cursor.fetchone()
    profile['role'] = user_row[0] if user_row and user_row[0] else 'Unknown'
    
    # 2. Get standard arrays (sectors, watchlist, etc.)
    cursor.execute('SELECT category, value FROM preferences WHERE telegram_id = ?', (user_id,))
    for row in cursor.fetchall():
        category = row[0]
        # Convert the JSON string back into a Python list
        profile[category] = json.loads(row[1]) 
        
    # 3. Get Dynamic Memories (portfolio, preferences, goals)
    cursor.execute('SELECT fact_type, fact_content FROM memory WHERE telegram_id = ?', (user_id,))
    for row in cursor.fetchall():
        fact_type = row[0]
        fact_content = row[1]
        
        # 🛡️ THE BULLETPROOF SHIELD: This guarantees it NEVER crashes on .append()
        if fact_type not in profile:
            profile[fact_type] = []
        elif not isinstance(profile[fact_type], list):
            # If it is a string, wrap it in brackets so it becomes a list FIRST
            profile[fact_type] = [profile[fact_type]]
            
        # Now we can safely append without Python throwing the 'str' error
        profile[fact_type].append(fact_content)
        
    conn.close()
    print(f"---> [DATABASE] Master Profile Built: {profile}")
    return profile

def get_users_for_briefing(current_time_hhmm):
    """Returns a list of telegram_ids for users who want a brief at this exact minute."""
    conn = sqlite3.connect('assistant.db')
    cursor = conn.cursor()
    
    cursor.execute('SELECT telegram_id FROM users WHERE briefing_time = ?', (current_time_hhmm,))
    users = [row[0] for row in cursor.fetchall()]
    
    conn.close()
    return users

def save_document(user_id, file_name, telegram_file_id, gemini_file_id, file_type):
    """Saves the uploaded document metadata, Gemini File ID"""
    print(f"---> [DATABASE] Saving Document Metadata: {file_name} for User {user_id}")
    conn = sqlite3.connect('assistant.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO documents (telegram_id, file_name, telegram_file_id, gemini_file_id, file_type)
        VALUES (?, ?, ?, ?, ?)
    ''', (user_id, file_name, telegram_file_id, gemini_file_id, file_type))
    
    conn.commit()
    conn.close()
    print("---> [DATABASE] Document Metadata saved.")

def get_latest_document(user_id):
    """Fetches the most recently uploaded document for this user."""
    print(f"---> [DATABASE] Fetching latest document for User {user_id}...")
    conn = sqlite3.connect('assistant.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT file_name, gemini_file_id FROM documents 
        WHERE telegram_id = ? 
        ORDER BY uploaded_at DESC LIMIT 1
    ''', (user_id,))
    
    row = cursor.fetchone()
    conn.close()
    
    if row:
        print(f"---> [DATABASE] Found Document: {row[0]}")
        return {"file_name": row[0], "gemini_file_id": row[1]}
    
    print("---> [DATABASE] No recent documents found.")
    return None

def save_integration_token(telegram_id, service_name, auth_token_json):
    """Saves or updates OAuth tokens in the integrations table."""
    print(f"---> [DATABASE] Saving Integration Token for '{service_name}' (User {telegram_id})")
    conn = sqlite3.connect('assistant.db')
    cursor = conn.cursor()
    
    # Check if this user already connected this service before
    cursor.execute("SELECT id FROM integrations WHERE telegram_id=? AND service_name=?", (telegram_id, service_name))
    row = cursor.fetchone()
    
    if row:
        print(f"---> [DATABASE] Token exists. Updating...")
        # Update existing token
        cursor.execute("UPDATE integrations SET auth_token=?, status=? WHERE id=?", 
                       (auth_token_json, 'active', row[0]))
    else:
        print(f"---> [DATABASE] New Token. Inserting...")
        # Insert new token
        cursor.execute("INSERT INTO integrations (telegram_id, service_name, status, auth_token) VALUES (?, ?, ?, ?)", 
                       (telegram_id, service_name, 'active', auth_token_json))
    conn.commit()
    conn.close()
    print(f"---> [DATABASE] Successfully saved {service_name} token for user {telegram_id}")

def get_integration_token(telegram_id, service_name):
    """Fetches and parses the OAuth token for a specific service."""
    print(f"---> [DATABASE] Fetching Integration Token for '{service_name}' (User {telegram_id})...")
    conn = sqlite3.connect('assistant.db')
    cursor = conn.cursor()
    
    cursor.execute("SELECT auth_token FROM integrations WHERE telegram_id=? AND service_name=?", (telegram_id, service_name))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        print("---> [DATABASE] Token found and loaded.")
        return json.loads(row[0]) # Returns it as a neat Python dictionary
    
    print("---> [DATABASE] No Token found.")
    return None

if __name__ == '__main__':
    init_db()