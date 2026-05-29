CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    display_name TEXT NOT NULL DEFAULT 'Untitled Session',
    campaign_name TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    source_audio_files TEXT,
    num_speakers_detected INTEGER,
    speakers_json_path TEXT,
    transcripts_folder TEXT,
    summary_path TEXT,
    status TEXT DEFAULT 'new'
);

CREATE TABLE IF NOT EXISTS speaker_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER REFERENCES sessions(id) ON DELETE CASCADE,
    source_speaker_id TEXT,
    display_name TEXT,
    character_name TEXT,
    character_class TEXT,
    role TEXT,
    include_in_tracking INTEGER DEFAULT 1,
    notes TEXT,
    speech_patterns TEXT,
    sample_quotes TEXT,
    confidence TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS user_prompts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    content TEXT NOT NULL,
    is_default INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
