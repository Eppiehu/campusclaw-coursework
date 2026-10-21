"""MySQL runtime connection; SQLite remains for legacy coursework/test fixtures."""
import sqlite3
from urllib.parse import unquote, urlparse
from flask import current_app, g


class Row(dict):
    def __getitem__(self, key):
        return list(self.values())[key] if isinstance(key, int) else super().__getitem__(key)


class MySQLResult:
    def __init__(self, cursor):
        self.cursor = cursor
        self.lastrowid = getattr(cursor, "lastrowid", None)
        self.rowcount = getattr(cursor, "rowcount", 0)

    def fetchone(self):
        row = self.cursor.fetchone()
        return Row(row) if row is not None else None

    def fetchall(self):
        return [Row(row) for row in self.cursor.fetchall()]

    def __iter__(self):
        return iter(self.fetchall())


class MySQLConnection:
    dialect = "mysql"

    def __init__(self, url):
        import pymysql
        parsed = urlparse(url)
        self.connection = pymysql.connect(
            host=parsed.hostname or "localhost", port=parsed.port or 3306,
            user=unquote(parsed.username or "campusclaw"), password=unquote(parsed.password or ""),
            database=parsed.path.lstrip("/"), charset="utf8mb4", autocommit=False,
            cursorclass=pymysql.cursors.DictCursor,
        )

    def execute(self, sql, params=()):
        cursor = self.connection.cursor()
        sql = sql.replace("?", "%s").replace("INSERT OR IGNORE", "INSERT IGNORE")
        cursor.execute(sql.replace("datetime('now')", "CURRENT_TIMESTAMP"), params)
        return MySQLResult(cursor)

    def executemany(self, sql, params):
        cursor = self.connection.cursor()
        cursor.executemany(sql.replace("?", "%s").replace("INSERT OR IGNORE", "INSERT IGNORE"), params)
        return MySQLResult(cursor)

    def commit(self): self.connection.commit()
    def rollback(self): self.connection.rollback()
    def close(self): self.connection.close()
    def __enter__(self): return self
    def __exit__(self, kind, value, traceback):
        self.rollback() if kind else self.commit()


def connect(database, mysql_url=None):
    if mysql_url:
        return MySQLConnection(mysql_url)
    connection = sqlite3.connect(database, timeout=20)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def get_db():
    if "db" not in g:
        g.db = connect(current_app.config["DATABASE"], current_app.config.get("DATABASE_URL"))
    return g.db


def close_db(_error=None):
    connection = g.pop("db", None)
    if connection is not None:
        connection.close()
