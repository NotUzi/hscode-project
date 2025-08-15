# HScode.py
import os
import pandas as pd
import sqlite3
import json
from datetime import datetime
from fastapi import FastAPI, Query
import re

# ------------------------------
# Paths (relative, portable)
# ------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))       # src/ folder
DATA_DIR = os.path.join(BASE_DIR, "..", "data")            # ../data
DB_DIR = os.path.join(BASE_DIR, "..", "db")                # ../db
DB_PATH = os.path.join(DB_DIR, "tariffs.db")
CSV_PATH = os.path.join(DATA_DIR, "TPHS.csv")

# Make directories if they don't exist
os.makedirs(DB_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

# ------------------------------
# FastAPI app
# ------------------------------
app = FastAPI(title="Canadian HS Code API")

# ------------------------------
# Helper functions
# ------------------------------
def clean_search_text(text: str) -> str:
    """Normalize search input: remove special chars, lowercase"""
    return re.sub(r"[^a-zA-Z0-9\s]", "", text).strip().lower()

# ------------------------------
# Database setup
# ------------------------------
def init_db():
    """Create main and FTS tables with indexes"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Main tariffs table
    c.execute('''
        CREATE TABLE IF NOT EXISTS tariffs (
            id INTEGER PRIMARY KEY,
            country_code TEXT NOT NULL,
            hs_code TEXT NOT NULL,
            original_description TEXT,
            full_context TEXT NOT NULL,
            hierarchy_level INTEGER,
            parent_category TEXT,
            sub_category TEXT,
            uom TEXT,
            effective_date TEXT,
            rates TEXT,
            last_updated TEXT,
            UNIQUE(country_code, hs_code)
        )
    ''')

    # Indexes for faster lookups
    c.execute('CREATE INDEX IF NOT EXISTS idx_hs_code ON tariffs(hs_code)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_country ON tariffs(country_code)')

    # FTS table for full-text search
    c.execute('''
        CREATE VIRTUAL TABLE IF NOT EXISTS tariffs_fts
        USING fts5(
            hs_code,
            original_description,
            full_context,
            parent_category,
            sub_category,
            content='tariffs',
            content_rowid='id'
        )
    ''')

    conn.commit()
    conn.close()

# ------------------------------
# Insert data into DB
# ------------------------------
def insert_tariff_data():
    """Read CSV, clean it, and insert into main + FTS tables"""
    df = pd.read_csv(CSV_PATH, low_memory=False)

    # Clean and normalize
    df['TARIFF'] = df['TARIFF'].astype(str).str.strip().str.replace('"', '')
    df['DESC1'] = df['DESC1'].fillna('').str.strip()
    df['UOM'] = df['UOM'].fillna('').str.strip()

    current_parents = {}
    rate_columns = ['MFN', 'General Tariff', 'UST', 'CCCT', 'LDCT', 'GPT', 'CPTPT', 'UKT']
    cleaned_data = []

    for _, row in df.iterrows():
        tariff = row['TARIFF']
        desc = row['DESC1']
        sections = tariff.split('.')
        hierarchy_level = len(sections)

        # Keep track of parent descriptions
        if hierarchy_level <= 2:
            current_parents['level1'] = desc
            parent_desc = desc
        elif hierarchy_level == 3:
            current_parents['level2'] = desc
            parent_desc = f"{current_parents.get('level1', '')} - {desc}"
        else:
            parent_desc = f"{current_parents.get('level1', '')} - {current_parents.get('level2', '')} - {desc}"

        rates = {col: row[col] for col in rate_columns if col in row and pd.notna(row[col]) and row[col] != ''}

        cleaned_data.append({
            'tariff_code': tariff,
            'original_description': desc,
            'full_context': parent_desc.strip(' -'),
            'hierarchy_level': hierarchy_level,
            'parent_category': current_parents.get('level1', ''),
            'sub_category': current_parents.get('level2', ''),
            'uom': row['UOM'],
            'rates': rates,
            'effective_date': row['EFF_DATE'] if 'EFF_DATE' in row else '',
        })

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    for item in cleaned_data:
        # Insert into main table
        c.execute('''
            INSERT OR IGNORE INTO tariffs (
                country_code, hs_code, original_description, full_context, hierarchy_level,
                parent_category, sub_category, uom, effective_date, rates, last_updated
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            'CA',
            item['tariff_code'],
            item['original_description'],
            item['full_context'],
            item['hierarchy_level'],
            item['parent_category'],
            item['sub_category'],
            item['uom'],
            item['effective_date'],
            json.dumps(item['rates']),
            datetime.now().isoformat()
        ))

        # Insert into FTS table
        c.execute('''
            INSERT INTO tariffs_fts (hs_code, original_description, full_context, parent_category, sub_category)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            item['tariff_code'],
            item['original_description'],
            item['full_context'],
            item['parent_category'],
            item['sub_category']
        ))

    conn.commit()
    conn.close()

# ------------------------------
# API Endpoint
# ------------------------------
@app.get("/suggestions")
def get_suggestions(query: str = Query(..., description="Search term for HS code suggestions")):
    """Return top HS code matches for a query"""
    from sqlite3 import Error

    # Clean input for safer searching
    search_text = clean_search_text(query)
    exact = search_text
    prefix = f"{search_text}%"
    contains = f"%{search_text}%"
    fts_query = " OR ".join([f'"{word}"' for word in search_text.split()])

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    results = []

    try:
        # 1️⃣ LIKE search for quick filtering
        cur.execute("""
            SELECT hs_code, original_description, full_context
            FROM tariffs
            WHERE original_description LIKE ?
               OR original_description LIKE ?
               OR original_description LIKE ?
        """, (exact, prefix, contains))
        results.extend([dict(r) for r in cur.fetchall()])

        # 2️⃣ FTS search for deeper matches
        cur.execute("""
            SELECT t.hs_code, t.original_description, t.full_context
            FROM tariffs t
            JOIN tariffs_fts f ON t.id = f.rowid
            WHERE f.full_context MATCH ?
        """, (fts_query,))
        results.extend([dict(r) for r in cur.fetchall()])

    except Error as e:
        return {"error": str(e)}

    finally:
        conn.close()

    # Remove duplicates
    seen = set()
    unique_results = []
    for r in results:
        if r['hs_code'] not in seen:
            unique_results.append(r)
            seen.add(r['hs_code'])

    return unique_results

# ------------------------------
# Startup (for first run)
# ------------------------------
if __name__ == "__main__":
    init_db()
    insert_tariff_data()
    print(f"DB created at {DB_PATH}. You can now run 'uvicorn HScode:app --reload'")
