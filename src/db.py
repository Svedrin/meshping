import os
import sqlite3
import sys

from dataclasses        import dataclass
from sqlite3            import OperationalError
from packaging.version  import parse as parse_version

import pandas

# WAL mode is supported since 3.7.0: https://sqlite.org/wal.html
assert parse_version(sqlite3.sqlite_version) >= parse_version("3.7.0"), "need WAL mode support"

# Upsert is supported since 3.24.0: https://www.sqlite.org/draft/lang_UPSERT.html
assert parse_version(sqlite3.sqlite_version) >= parse_version("3.24.0"), "need UPSERT support"

QRY_CREATE_TABLE_TARGETS = """
CREATE TABLE IF NOT EXISTS targets (
    id INTEGER PRIMARY KEY,
    addr TEXT UNIQUE,
    name TEXT,
    UNIQUE (addr, name)
)
"""

QRY_CREATE_TABLE_HISTOGRAMS = """
CREATE TABLE IF NOT EXISTS histograms (
    target_id INTEGER,
    timestamp INTEGER,
    bucket    INTEGER,
    count     INTEGER DEFAULT 1,
    FOREIGN KEY (target_id) REFERENCES targets(id),
    UNIQUE (target_id, timestamp, bucket)
)
"""

QRY_CREATE_TABLE_STATISTICS = """
CREATE TABLE IF NOT EXISTS statistics (
    target_id INTEGER,
    field     TEXT,
    value     DOUBLE,
    FOREIGN KEY (target_id) REFERENCES targets(id),
    UNIQUE (target_id, field)
)
"""

QRY_CREATE_TABLE_META = """
CREATE TABLE IF NOT EXISTS meta (
    target_id INTEGER,
    field     TEXT,
    value     TEXT,
    FOREIGN KEY (target_id) REFERENCES targets(id),
    UNIQUE (target_id, field)
)
"""

QRY_INSERT_TARGET = """
INSERT INTO targets (addr, name) VALUES (?, ?)
ON CONFLICT (addr) DO NOTHING;
"""

QRY_RENAME_TARGET = """
INSERT INTO targets (addr, name) VALUES (?, ?)
ON CONFLICT (addr) DO UPDATE
SET name = excluded.name;
"""

QRY_INSERT_MEASUREMENT = """
INSERT INTO histograms (target_id, timestamp, bucket) VALUES (?, ?, ?)
ON CONFLICT (target_id, timestamp, bucket) DO UPDATE
SET count = count + 1;
"""

QRY_SELECT_MEASUREMENTS = """
SELECT h.timestamp, h.bucket, h.count
FROM   histograms h
INNER JOIN targets t ON t.id = h.target_id
WHERE t.addr = ?
ORDER BY h.timestamp, h.bucket
"""

QRY_INSERT_STATS = """
INSERT INTO statistics (target_id, field, value) VALUES(?, ?, ?)
ON CONFLICT (target_id, field) DO UPDATE
SET value = excluded.value;
"""

QRY_INSERT_META = """
INSERT INTO meta (target_id, field, value) VALUES(?, ?, ?)
ON CONFLICT (target_id, field) DO UPDATE
SET value = excluded.value;
"""

QRY_SELECT_STATS = """
SELECT s.field, s.value
FROM   statistics s
INNER JOIN targets t ON t.id = s.target_id
WHERE t.addr = ?
"""

QRY_SELECT_META = """
SELECT m.field, m.value
FROM   meta m
INNER JOIN targets t ON t.id = m.target_id
WHERE t.addr = ?
"""


class Database:
    def __init__(self, path):
        self.path = path
        self.conn = sqlite3.connect(path)
        self.conn.execute('PRAGMA journal_mode = WAL;')
        self.conn.execute('PRAGMA foreign_keys = ON;')

        with self.conn:
            self.conn.execute(QRY_CREATE_TABLE_TARGETS)
            self.conn.execute(QRY_CREATE_TABLE_HISTOGRAMS)
            self.conn.execute(QRY_CREATE_TABLE_STATISTICS)
            self.conn.execute(QRY_CREATE_TABLE_META)

    def exec_read(self, query, args):
        return self.conn.execute(query, args)

    def exec_write(self, query, args):
        with self.conn:
            return self.conn.execute(query, args)

    def exec_write_many(self, query, list_of_args):
        with self.conn:
            self.conn.executemany(query, list_of_args)

    def add(self, addr, name):
        self.exec_write(QRY_INSERT_TARGET, (addr, name))

    def get(self, addr):
        for row in self.conn.execute("SELECT id, addr, name FROM targets WHERE addr = ?", (addr, )):
            return Target(*row)
        raise LookupError("Target does not exist: %s" % addr)

    def all(self):
        for row in self.conn.execute('SELECT id, addr, name FROM targets'):
            yield Target(*row)

    def delete(self, target_id):
        with self.conn:
            self.conn.execute("DELETE FROM histograms WHERE target_id = ?", (target_id, ))
            self.conn.execute("DELETE FROM statistics WHERE target_id = ?", (target_id, ))
            self.conn.execute("DELETE FROM meta       WHERE target_id = ?", (target_id, ))
            self.conn.execute("DELETE FROM targets    WHERE id        = ?", (target_id, ))

    def prune_histograms(self, before_timestamp):
        with self.conn:
            self.conn.execute(
                "DELETE FROM histograms WHERE timestamp < ?",
                (before_timestamp, )
            )

    def clear_statistics(self):
        with self.conn:
            # sqlite doesn't have truncate
            self.conn.execute("DELETE FROM statistics")
            self.conn.execute("DELETE FROM meta WHERE field = 'state'")


def open_database():
    db_path = os.path.join(os.environ.get("MESHPING_DATABASE_PATH", "db"), "meshping.db")
    try:
        return Database(db_path)
    except OperationalError as err:
        print("Could not open database %s: %s" % (db_path, err), file=sys.stderr)
        sys.exit(1)


@dataclass(frozen=True)
class Target:
    id:   int
    addr: str
    name: str

    db = open_database()

    def rename(self, name):
        self.db.exec_write(QRY_RENAME_TARGET, (self.addr, name))

    def delete(self):
        self.db.delete(self.id)

    @property
    def histogram(self):
        return pandas.read_sql_query(
            sql     = QRY_SELECT_MEASUREMENTS,
            con     = self.db.conn,
            params  = (self.addr, ),
            parse_dates = {'timestamp': 's'}
        ).pivot(                    # flip the dataframe: turn each value of the
            index="timestamp",      # "bucket" DB column into a separate column in
            columns="bucket",       # the DF, using the timestamp as the index
            values="count"          # and the count for the values.
        ).fillna(0)                 # replace NaNs with zero

    def add_measurement(self, timestamp, bucket):
        self.db.exec_write(QRY_INSERT_MEASUREMENT, (self.id, timestamp, bucket))

    @property
    def statistics(self):
        stats = {
            "sent": 0, "lost": 0, "recv": 0, "sum":  0
        }
        stats.update(self.db.exec_read(QRY_SELECT_STATS, (self.addr, )))
        return stats

    @property
    def meta(self):
        return dict(self.db.exec_read(QRY_SELECT_META, (self.addr, )))

    def update_statistics(self, stats):
        self.db.exec_write_many(QRY_INSERT_STATS, [
            (self.id, field, value)
            for field, value in stats.items()
        ])

    def update_meta(self, meta):
        self.db.exec_write_many(QRY_INSERT_META, [
            (self.id, field, value)
            for field, value in meta.items()
        ])

    @property
    def is_foreign(self):
        return self.meta.get("is_foreign", "false") == "true"

    def set_is_foreign(self, is_foreign):
        self.update_meta({"is_foreign": str(is_foreign).lower()})

    @property
    def state(self):
        return self.meta.get("state", "unknown")

    def set_state(self, state):
        if state not in ("up", "down", "unknown"):
            raise ValueError('state must be one of ("up", "down", "unknown"), not %s' % state)
        self.update_meta({"state": str(state)})

    @property
    def error(self):
        return self.meta.get("error")

    def set_error(self, error):
        self.update_meta({"state": "error", "error": error})
