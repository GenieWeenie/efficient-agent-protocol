# examples/view_state.py
import json
import os
import sqlite3

def view_state(db_path="agent_state.db"):
    if not os.path.exists(db_path):
        print(f"Error: Database '{db_path}' not found. Run a flow first!")
        return

    print(f"\n--- Reading Persistent State from: {db_path} ---")
    
    with sqlite3.connect(db_path) as conn:
        cursor = conn.execute("SELECT pointer_id, summary, metadata, raw_data FROM state_store")
        rows = cursor.fetchall()

        if not rows:
            print("Database is empty.")
            return

        for row in rows:
            p_id, summary, meta_json, raw = row
            meta = json.loads(meta_json)
            
            print(f"\n🆔 Pointer:  {p_id}")
            print(f"📝 Summary:  {summary}")
            print(f"📊 Metadata: {meta}")
            
            # Show just a snippet of the raw data so we don't flood the terminal
            preview = raw[:100] + "..." if len(raw) > 100 else raw
            print(f"📦 Raw Data (Preview): {preview}")
            print("-" * 50)

if __name__ == "__main__":
    view_state()
