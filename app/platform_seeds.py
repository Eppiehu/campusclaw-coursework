"""First-install applications and reusable prompts, without overwriting teacher edits."""
DEFAULTS = [
    ("数学学习助手", "数学辅导模板", "你是耐心的数学学习助手。先了解学生的推理过程，再帮助检查条件与依据。命中解题引导技能时遵守技能要求。", "math-guidance"),
    ("语文阅读助手", "阅读辅导模板", "你是语文阅读学习助手。引导学生结合上下文寻找依据，分析表达和结构，避免编造文本来源。", "language-guidance"),
]


def seed_platform_apps(connection):
    for class_row in connection.execute("SELECT id FROM classes").fetchall():
        class_id = class_row[0]
        marker = "platform-apps-v1-" + class_id
        if connection.execute("SELECT name FROM schema_migrations WHERE name=?", (marker,)).fetchone():
            continue
        for name, template_name, prompt, skill_key in DEFAULTS:
            template = connection.execute("SELECT id FROM prompt_templates WHERE class_id=? AND name=?", (class_id, template_name)).fetchone()
            template_id = template[0] if template else connection.execute(
                "INSERT INTO prompt_templates (class_id,name,content,enabled) VALUES (?,?,?,1)", (class_id, template_name, prompt)).lastrowid
            existing = connection.execute("SELECT id FROM tutor_agents WHERE class_id=? AND name=?", (class_id, name)).fetchone()
            if existing:
                continue
            agent_id = connection.execute("INSERT INTO tutor_agents (class_id,name,prompt,enabled,prompt_template_id,mcp_tools_json) VALUES (?,?,?,1,?,'[]')",
                                           (class_id, name, prompt, template_id)).lastrowid
            skill = connection.execute("SELECT id FROM skills WHERE class_id=? AND seed_key=?", (class_id, skill_key)).fetchone()
            if skill:
                connection.execute("INSERT INTO tutor_agent_skills (agent_id,skill_id) VALUES (?,?)", (agent_id, skill[0]))
        connection.execute("INSERT INTO schema_migrations (name) VALUES (?)", (marker,))
    connection.commit()
