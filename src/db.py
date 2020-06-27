import sqlite3

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
SELECT s.field, s.value
FROM   meta m
INNER JOIN targets t ON t.id = m.target_id
WHERE t.addr = ?
"""

@dataclass(frozen=True)
class Target:
    id:   int
    addr: str
    name: str


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

    def add_target(self, addr, name):
        with self.conn:
            self.conn.execute(QRY_INSERT_TARGET, (addr, name))

    def rename_target(self, addr, name):
        with self.conn:
            self.conn.execute(QRY_RENAME_TARGET, (addr, name))

    def get_target(self, addr):
        for row in self.conn.execute("SELECT id, addr, name FROM targets WHERE addr = ?", (addr, )):
            return Target(*row)
        raise LookupError("Target does not exist: %s" % addr)

    def all_targets(self):
        for row in self.conn.execute('SELECT id, addr, name FROM targets'):
            yield Target(*row)

    def delete_target(self, addr):
        target = self.get_target(addr)
        with self.conn:
            self.conn.execute("DELETE FROM histograms WHERE target_id = ?", (target.id, ))
            self.conn.execute("DELETE FROM statistics WHERE target_id = ?", (target.id, ))
            self.conn.execute("DELETE FROM meta       WHERE target_id = ?", (target.id, ))
            self.conn.execute("DELETE FROM targets    WHERE id        = ?", (target.id, ))

    def add_measurement(self, addr, timestamp, bucket):
        target = self.get_target(addr)
        with self.conn:
            self.conn.execute(QRY_INSERT_MEASUREMENT, (target.id, timestamp, bucket))

    def get_histogram(self, addr):
        return pandas.read_sql_query(
            sql     = QRY_SELECT_MEASUREMENTS,
            con     = self.conn,
            params  = (addr, ),
            parse_dates = {'timestamp': 's'}
        ).pivot(                    # flip the dataframe: turn each value of the
            index="timestamp",      # "bucket" DB column into a separate column in
            columns="bucket",       # the DF, using the timestamp as the index
            values="count"          # and the count for the values.
        ).fillna(0)                 # replace NaNs with zero

    def prune_histograms(self, before_timestamp):
        with self.conn:
            self.conn.execute(
                "DELETE FROM histograms WHERE timestamp < ?",
                (before_timestamp, )
            )

    def get_statistics(self, addr):
        return dict(self.conn.execute(QRY_SELECT_STATS, (addr, )))

    def update_statistics(self, addr, stats):
        target = self.get_target(addr)
        with self.conn:
            self.conn.executemany(QRY_INSERT_STATS, [
                (target.id, field, value)
                for field, value in stats.items()
            ])

    def clear_statistics(self):
        with self.conn:
            # sqlite doesn't have truncate
            self.conn.execute("DELETE FROM statistics")

    def get_meta(self, addr):
        return dict(self.conn.execute(QRY_SELECT_META, (addr, )))

    def update_meta(self, addr, meta):
        target = self.get_target(addr)
        with self.conn:
            self.conn.executemany(QRY_INSERT_META, [
                (target.id, field, value)
                for field, value in meta.items()
            ])
