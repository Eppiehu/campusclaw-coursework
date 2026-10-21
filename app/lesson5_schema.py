"""Idempotent lesson-5 schema for MySQL runtime and SQLite regression fixtures."""

TABLES = [
    """CREATE TABLE IF NOT EXISTS schema_migrations (name VARCHAR(64) PRIMARY KEY)""",
    """CREATE TABLE IF NOT EXISTS token_revocations (
        jti VARCHAR(64) PRIMARY KEY, expires_at BIGINT NOT NULL,
        revoked_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)""",
    """CREATE TABLE IF NOT EXISTS tutor_agents (
        id INTEGER PRIMARY KEY AUTOINCREMENT, class_id VARCHAR(32) NOT NULL,
        name VARCHAR(64) NOT NULL, prompt TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1,
        UNIQUE(class_id, name))""",
    """CREATE TABLE IF NOT EXISTS prompt_templates (
        id INTEGER PRIMARY KEY AUTOINCREMENT, class_id VARCHAR(32) NOT NULL,
        name VARCHAR(64) NOT NULL, content TEXT NOT NULL,
        enabled INTEGER NOT NULL DEFAULT 1, UNIQUE(class_id,name))""",
    """CREATE TABLE IF NOT EXISTS tutor_agent_skills (
        agent_id INTEGER NOT NULL REFERENCES tutor_agents(id) ON DELETE CASCADE,
        skill_id INTEGER NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
        PRIMARY KEY(agent_id, skill_id))""",
    """CREATE TABLE IF NOT EXISTS tutor_agent_materials (
        agent_id INTEGER NOT NULL REFERENCES tutor_agents(id) ON DELETE CASCADE,
        material_id INTEGER NOT NULL REFERENCES materials(id) ON DELETE CASCADE,
        PRIMARY KEY(agent_id, material_id))""",
    """CREATE TABLE IF NOT EXISTS conversations (
        id INTEGER PRIMARY KEY AUTOINCREMENT, class_id VARCHAR(32) NOT NULL,
        user_id INTEGER NOT NULL REFERENCES users(id), agent_id INTEGER NOT NULL REFERENCES tutor_agents(id),
        title VARCHAR(255) NOT NULL DEFAULT '新的提问',
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)""",
    """CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
        role VARCHAR(16) NOT NULL, content TEXT NOT NULL,
        citations_json TEXT NOT NULL, skill_name VARCHAR(32),
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)""",
]
SKILL_COLUMNS = {
    "class_id": "VARCHAR(32)", "trigger_text": "TEXT",
    "description": "TEXT", "tools_json": "TEXT", "source_text": "TEXT",
    "subject_text": "VARCHAR(32) NOT NULL DEFAULT ''", "enabled": "INTEGER NOT NULL DEFAULT 1",
    "seed_key": "VARCHAR(64)",
}
SEED_SKILLS = [
    ("math-guidance", "数学解题引导", "数学,方程,计算,几何", "数学"),
    ("language-guidance", "语文解题引导", "语文,阅读,作文,古诗", "语文"),
]


def columns(connection, table):
    if getattr(connection, "dialect", None) == "mysql":
        return {row["Field"] for row in connection.execute(f"SHOW COLUMNS FROM {table}").fetchall()}
    return {row[1] for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}


def migrate(connection):
    mysql = getattr(connection, "dialect", None) == "mysql"
    for name, definition in SKILL_COLUMNS.items():
        if name not in columns(connection, "skills"):
            connection.execute(f"ALTER TABLE skills ADD COLUMN {name} {definition}")
    for name, definition in {"status": "VARCHAR(16) NOT NULL DEFAULT 'pending'", "strategy": "VARCHAR(16) NOT NULL DEFAULT 'auto'"}.items():
        if name not in columns(connection, "knowledge_chunks"):
            connection.execute(f"ALTER TABLE knowledge_chunks ADD COLUMN {name} {definition}")
    if mysql and "embedding" in columns(connection, "knowledge_chunks"):
        connection.execute("ALTER TABLE knowledge_chunks DROP COLUMN embedding")
    for statement in TABLES:
        if mysql:
            statement = statement.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "INTEGER PRIMARY KEY AUTO_INCREMENT")
        connection.execute(statement)
    for name, definition in {"prompt_template_id": "INTEGER", "mcp_tools_json": "TEXT"}.items():
        if name not in columns(connection, "tutor_agents"):
            connection.execute(f"ALTER TABLE tutor_agents ADD COLUMN {name} {definition}")
    if mysql and not connection.execute("SELECT name FROM schema_migrations WHERE name='standard-skill-description'").fetchone():
        connection.execute("ALTER TABLE skills MODIFY COLUMN trigger_text TEXT")
        connection.execute("INSERT INTO schema_migrations (name) VALUES ('standard-skill-description')")
    if mysql:
        if not connection.execute("SHOW INDEX FROM skills WHERE Key_name='uq_skill_class_name'").fetchone():
            connection.execute("CREATE UNIQUE INDEX uq_skill_class_name ON skills(class_id,name)")
    else:
        connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_skill_class_name ON skills(class_id,name)")
    if not connection.execute("SELECT name FROM schema_migrations WHERE name='lesson5-chunks-800-80'").fetchone():
        from .chunks import backfill_chunks
        connection.execute("DELETE FROM knowledge_chunks")
        backfill_chunks(connection)
        connection.execute("INSERT INTO schema_migrations (name) VALUES ('lesson5-chunks-800-80')")
    for class_row in connection.execute("SELECT id FROM classes").fetchall():
        for key, name, trigger, subject in SEED_SKILLS:
            if connection.execute("SELECT id FROM skills WHERE class_id=? AND seed_key=?", (class_row[0], key)).fetchone():
                continue
            description = "只指出学生错在哪一步、下一步检查什么；不得提供最终答案、选项、得数或完整解题过程。"
            source = f"名称：{name}\n适用条件：{trigger}\n资料：{subject}\n工具：knowledge_search\n启用：是\n\n{description}"
            connection.execute("""INSERT INTO skills
                (class_id,name,trigger_text,description,tools_json,source_text,subject_text,enabled,seed_key)
                VALUES (?,?,?,?,?,?,?,?,?)""", (class_row[0], name, trigger, description, '["knowledge_search"]', source, subject, 1, key))
    connection.commit()
