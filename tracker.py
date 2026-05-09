import sqlite3
import yt_dlp
import datetime
import os

DB_FILE = "history.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS channels (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        handle TEXT UNIQUE,
        added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    
    CREATE TABLE IF NOT EXISTS videos (
        id TEXT PRIMARY KEY,
        channel_handle TEXT,
        published_date TEXT,
        first_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    
    CREATE TABLE IF NOT EXISTS video_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        video_id TEXT,
        retrieved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        title TEXT,
        description TEXT,
        thumbnail_url TEXT,
        status TEXT,
        FOREIGN KEY(video_id) REFERENCES videos(id)
    );
    """)
    conn.commit()
    conn.close()
    print("Database initialized.")

def add_channel(handle):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        c.execute("INSERT INTO channels (handle) VALUES (?)", (handle,))
        conn.commit()
        print(f"Added channel: {handle}")
    except sqlite3.IntegrityError:
        print(f"Channel {handle} already exists.")
    conn.close()

def scrape_channel(handle, limit=10):
    url = f"https://www.youtube.com/{handle}/videos"
    
    ydl_opts = {
        'extract_flat': False, # Need full metadata
        'skip_download': True,
        'playlistend': limit,
        'quiet': True,
        'no_warnings': True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        print(f"Fetching metadata for {handle}/videos (limit {limit})...")
        try:
            info = ydl.extract_info(url, download=False)
        except Exception as e:
            print(f"Error fetching channel: {e}")
            return
            
        entries = info.get('entries', [])
        channel_name = info.get('uploader') or info.get('playlist_uploader') or info.get('channel') or handle
        
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        
        # Update channel name
        c.execute("UPDATE channels SET name = ? WHERE handle = ?", (channel_name, handle))
        conn.commit()
        
        for entry in entries:
            if not entry:
                continue
            v_id = entry.get('id')
            v_title = entry.get('title')
            v_desc = entry.get('description', '')
            v_thumb = entry.get('thumbnail', '')
            upload_date = entry.get('upload_date', '') 
            status = 'PUBLIC' 
            
            try:
                # Insert into videos if not exists
                c.execute("INSERT OR IGNORE INTO videos (id, channel_handle, published_date) VALUES (?, ?, ?)", 
                          (v_id, handle, upload_date))
                
                # Check latest snapshot
                c.execute("""SELECT title, description, thumbnail_url, status 
                             FROM video_snapshots 
                             WHERE video_id = ? 
                             ORDER BY retrieved_at DESC LIMIT 1""", (v_id,))
                latest = c.fetchone()
                
                changed = False
                if not latest:
                    changed = True
                else:
                    if (latest[0] != v_title or 
                        latest[1] != v_desc or 
                        latest[2] != v_thumb or 
                        latest[3] != status):
                        changed = True
                
                if changed:
                    print(f"New snapshot saved for video: {v_id} - '{v_title}'")
                    c.execute("""INSERT INTO video_snapshots (video_id, title, description, thumbnail_url, status) 
                                 VALUES (?, ?, ?, ?, ?)""", 
                              (v_id, v_title, v_desc, v_thumb, status))
                conn.commit()
            except Exception as e:
                print(f"Database error for video {v_id}: {e}")
                
        conn.close()

if __name__ == "__main__":
    init_db()
    handle = "@PrimoRico"
    add_channel(handle)
    scrape_channel(handle, limit=5)

