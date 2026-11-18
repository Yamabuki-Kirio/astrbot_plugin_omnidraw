"""Persistent, owner-scoped reference image sets."""

import base64
import re
import sqlite3
from contextlib import closing
from pathlib import Path


def match_reference_names(prompt, names):
    patterns = []
    for name in sorted(names, key=lambda name: (-len(name), name)):
        escaped = re.escape(name)
        if name[0].isascii():
            escaped = r"(?<![A-Za-z0-9_])" + escaped
        if name[-1].isascii():
            escaped += r"(?![A-Za-z0-9_])"
        patterns.append(escaped)
    if not patterns:
        return []
    return list(dict.fromkeys(match.group() for match in re.finditer("|".join(patterns), prompt)))


class ReferenceLibrary:
    def __init__(self, data_dir):
        self.path = Path(data_dir) / "reference_library.sqlite3"

    def _connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.execute("""CREATE TABLE IF NOT EXISTS refs (
            scope TEXT, name TEXT, position INTEGER, mime TEXT, payload BLOB,
            PRIMARY KEY (scope, name, position))""")
        return connection

    def save(self, scope, name, images):
        if not images or sum(len(payload) for _, payload in images) > 20 * 1024 * 1024:
            raise ValueError("词条必须有图片，且总大小不能超过 20 MiB")
        with closing(self._connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            names = self._names(connection, scope)
            if name not in names and len(names) >= 10:
                raise ValueError("当前会话最多保存 10 个个人参考词条")
            connection.execute("DELETE FROM refs WHERE scope=? AND name=?", (scope, name))
            connection.executemany("INSERT INTO refs VALUES (?, ?, ?, ?, ?)", (
                (scope, name, position, mime, payload)
                for position, (mime, payload) in enumerate(images)
            ))

    def load(self, scope, name):
        return [f"data:{mime};base64,{base64.b64encode(payload).decode('ascii')}" for mime, payload in self.images(scope, name)]

    def images(self, scope, name):
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT mime, payload FROM refs WHERE scope=? AND name=? ORDER BY position", (scope, name),
            )
            return rows.fetchall()

    def delete(self, scope, name):
        with closing(self._connect()) as connection, connection:
            return bool(connection.execute("DELETE FROM refs WHERE scope=? AND name=?", (scope, name)).rowcount)

    @staticmethod
    def _names(connection, scope):
        return [row[0] for row in connection.execute("SELECT DISTINCT name FROM refs WHERE scope=? ORDER BY name", (scope,))]

    def names(self, scope):
        with closing(self._connect()) as connection:
            return self._names(connection, scope)

    def entries(self):
        if not self.path.is_file():
            return []
        with closing(self._connect()) as connection:
            return [dict(scope=scope, name=name, count=count) for scope, name, count in connection.execute(
                "SELECT scope, name, COUNT(*) FROM refs GROUP BY scope, name ORDER BY name, scope"
            )]

    def preview(self, scope, name, position):
        if not self.path.is_file():
            return None
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT mime, payload FROM refs WHERE scope=? AND name=? AND position=?", (scope, name, position),
            ).fetchone()
            if row:
                mime, payload = row
                return f"data:{mime};base64,{base64.b64encode(payload).decode('ascii')}"
        return None
