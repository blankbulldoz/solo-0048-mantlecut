import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from .errors import Rejected

SCHEMA_VERSION = 1


class Storage:
    def __init__(self, path: Path, clock=None):
        self.path = path
        self.clock = clock or (lambda: time.time_ns() // 1_000_000)
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            current = db.execute("PRAGMA user_version").fetchone()[0]
            if current == 0:
                script = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
                db.executescript(f"BEGIN IMMEDIATE;\n{script}\nPRAGMA user_version = {SCHEMA_VERSION};\nCOMMIT;")
            elif current != SCHEMA_VERSION:
                raise RuntimeError(f"状态库版本 {current} 不受当前服务支持")
            db.execute("PRAGMA journal_mode = WAL")

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=4, isolation_level=None)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA foreign_keys = ON")
            db.execute("PRAGMA synchronous = FULL")
            yield db
        finally:
            db.close()

    @contextmanager
    def transaction(self, *, write=False):
        with self.connection() as db:
            try:
                db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
                yield db, self.clock()
                db.commit()
            except sqlite3.OperationalError as exc:
                db.rollback()
                if getattr(exc, "sqlite_errorcode", 0) & 255 in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
                    raise Rejected("storage_busy", "状态库正忙，请稍后重试", 503) from exc
                raise
            except BaseException:
                db.rollback()
                raise
