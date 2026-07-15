from app.models.db import get_connection

code = 'sample_qwen_aigc'
name = 'qwen3.7-plus (示例)'
provider = 'aitoolcore'
base_url = 'https://aigc-api.aitoolcore.com/api/v1'
api_key = 'sk-aigc-8228735868c270b1a6e8b88a08710483d9fa6e39'
model_name = 'qwen3.7-plus'
category = 'text'
system_prompt = 'You are a helpful assistant.'
top_value = 0.8
is_default = 1
status = 'active'

with get_connection() as conn:
    # ensure table exists
    conn.execute("CREATE TABLE IF NOT EXISTS model_engines (id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT UNIQUE NOT NULL, name TEXT NOT NULL, provider TEXT, base_url TEXT, api_key TEXT, model_name TEXT, category TEXT DEFAULT 'text', system_prompt TEXT, top_value REAL DEFAULT 0.8, context_count INTEGER DEFAULT 8, is_default INTEGER DEFAULT 0, status TEXT DEFAULT 'active', token_prompt INTEGER DEFAULT 0, token_completion INTEGER DEFAULT 0, token_total INTEGER DEFAULT 0, last_used_at TEXT)")
    row = conn.execute("SELECT id FROM model_engines WHERE code=?", (code,)).fetchone()
    if row:
        conn.execute("UPDATE model_engines SET name=?, provider=?, base_url=?, api_key=?, model_name=?, category=?, system_prompt=?, top_value=?, is_default=?, status=? WHERE code=?",
                     (name, provider, base_url, api_key, model_name, category, system_prompt, top_value, is_default, status, code))
        print('updated existing model with code:', code)
    else:
        conn.execute("INSERT INTO model_engines (code, name, provider, base_url, api_key, model_name, category, system_prompt, top_value, is_default, status) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                     (code, name, provider, base_url, api_key, model_name, category, system_prompt, top_value, is_default, status))
        print('inserted model with code:', code)
    conn.commit()
