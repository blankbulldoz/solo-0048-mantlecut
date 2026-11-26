CREATE TABLE IF NOT EXISTS channels (
    slug TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    stable_release INTEGER REFERENCES releases(id)
);
CREATE TABLE IF NOT EXISTS revisions (
    id INTEGER PRIMARY KEY,
    slug TEXT NOT NULL REFERENCES channels(slug),
    title TEXT NOT NULL,
    generation INTEGER NOT NULL DEFAULT 1,
    source_id INTEGER REFERENCES revisions(id),
    base TEXT NOT NULL,
    layers TEXT NOT NULL,
    signature TEXT,
    sealed_ms INTEGER,
    CHECK ((signature IS NULL) = (sealed_ms IS NULL))
);
CREATE INDEX IF NOT EXISTS revisions_by_channel ON revisions(slug, id DESC);
CREATE TABLE IF NOT EXISTS subscribers (
    slug TEXT NOT NULL REFERENCES channels(slug),
    node TEXT NOT NULL,
    tags TEXT NOT NULL,
    wire INTEGER NOT NULL CHECK (wire IN (1, 2)),
    key_sha256 TEXT NOT NULL,
    paused INTEGER NOT NULL DEFAULT 0 CHECK (paused IN (0, 1)),
    PRIMARY KEY (slug, node)
);
CREATE TABLE IF NOT EXISTS releases (
    id INTEGER PRIMARY KEY,
    slug TEXT NOT NULL REFERENCES channels(slug),
    revision INTEGER NOT NULL REFERENCES revisions(id),
    fraction INTEGER NOT NULL CHECK (fraction BETWEEN 1 AND 100),
    stage TEXT NOT NULL CHECK (stage IN ('trial', 'wide', 'stable', 'withdrawn')),
    started_ms INTEGER NOT NULL,
    widened_ms INTEGER,
    ended_ms INTEGER
);
CREATE UNIQUE INDEX IF NOT EXISTS one_inflight_release ON releases(slug)
    WHERE stage IN ('trial', 'wide');
CREATE INDEX IF NOT EXISTS releases_by_channel ON releases(slug, id DESC);
CREATE TABLE IF NOT EXISTS seats (
    release INTEGER NOT NULL REFERENCES releases(id),
    slug TEXT NOT NULL,
    node TEXT NOT NULL,
    rank INTEGER NOT NULL,
    trial INTEGER NOT NULL CHECK (trial IN (0, 1)),
    PRIMARY KEY (release, node),
    UNIQUE (release, rank),
    FOREIGN KEY (slug, node) REFERENCES subscribers(slug, node)
);
CREATE TABLE IF NOT EXISTS offers (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT NOT NULL,
    node TEXT NOT NULL,
    release INTEGER NOT NULL REFERENCES releases(id),
    sha256 TEXT NOT NULL,
    payload BLOB NOT NULL,
    issued_ms INTEGER NOT NULL,
    expires_ms INTEGER NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('open', 'expired', 'superseded', 'applied', 'rejected')),
    UNIQUE (seq, sha256),
    FOREIGN KEY (slug, node) REFERENCES subscribers(slug, node)
);
CREATE UNIQUE INDEX IF NOT EXISTS one_open_offer ON offers(slug, node) WHERE state = 'open';
CREATE INDEX IF NOT EXISTS offers_by_target ON offers(slug, node, release, state, seq DESC);
CREATE INDEX IF NOT EXISTS offers_by_recency ON offers(slug, node, state, seq DESC);
CREATE TABLE IF NOT EXISTS receipts (
    seq INTEGER PRIMARY KEY,
    sha256 TEXT NOT NULL,
    result TEXT NOT NULL CHECK (result IN ('applied', 'rejected')),
    reason TEXT,
    received_ms INTEGER NOT NULL,
    FOREIGN KEY (seq, sha256) REFERENCES offers(seq, sha256)
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT NOT NULL REFERENCES channels(slug),
    at_ms INTEGER NOT NULL,
    kind TEXT NOT NULL,
    detail TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS events_by_channel ON events(slug, id DESC);
