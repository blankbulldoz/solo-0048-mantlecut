from .wire import digest


def freeze(db, slug, release, fraction, endpoints):
    ranked = sorted(endpoints, key=lambda endpoint: (digest(f"{slug}/{release}/{endpoint['node']}".encode()), endpoint["node"]))
    count = (len(ranked) * fraction + 99) // 100
    db.executemany(
        "INSERT INTO seats(release, slug, node, rank, trial) VALUES (?, ?, ?, ?, ?)",
        ((release, slug, endpoint["node"], rank, rank <= count) for rank, endpoint in enumerate(ranked, 1)),
    )
    return count


def status(db, release):
    rows = db.execute(
        """SELECT s.node, s.rank, s.trial, u.paused,
             (SELECT state FROM offers o WHERE o.slug = s.slug AND o.node = s.node
              AND o.release = s.release ORDER BY seq DESC LIMIT 1) AS latest,
             (SELECT seq FROM offers o WHERE o.slug = s.slug AND o.node = s.node
              AND o.release = s.release AND state = 'applied' ORDER BY seq DESC LIMIT 1) AS applied_seq
           FROM seats s JOIN subscribers u ON u.slug = s.slug AND u.node = s.node
           WHERE s.release = ? ORDER BY s.rank""", (release,),
    )
    return [dict(row, trial=bool(row["trial"]), paused=bool(row["paused"])) for row in rows]
