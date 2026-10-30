"""SQLite storage. Source DB holds orders/inventory/fulfillment; replica DB holds the synced copy."""
import hashlib
import sqlite3

from shop.config import DATA_DIR

SOURCE_DB = DATA_DIR / "shop.db"
REPLICA_DB = DATA_DIR / "replica.db"
SKUS = [f"SKU-{i:03d}" for i in range(1, 21)]  # 20 products


def connect(path):
    # new connection per call: simple and safe across threads
    return sqlite3.connect(path, timeout=10)


def init_db():
    """Create fresh databases (start-up always begins from a clean state)."""
    DATA_DIR.mkdir(exist_ok=True)
    for p in (SOURCE_DB, REPLICA_DB):
        p.unlink(missing_ok=True)
    with connect(SOURCE_DB) as c:
        c.execute("CREATE TABLE orders (order_id TEXT PRIMARY KEY, sku TEXT, qty INT, amount REAL, created REAL)")
        c.execute("CREATE TABLE inventory (sku TEXT PRIMARY KEY, stock INT)")
        c.execute("CREATE TABLE fulfillment (order_id TEXT, step TEXT, done REAL)")
        c.executemany("INSERT INTO inventory VALUES (?, 1000)", [(s,) for s in SKUS])
    with connect(REPLICA_DB) as c:
        c.execute("CREATE TABLE inventory (sku TEXT PRIMARY KEY, stock INT)")
        c.executemany("INSERT INTO inventory VALUES (?, 1000)", [(s,) for s in SKUS])


def rows_checksum(rows):
    """Short hash of (sku, stock) rows."""
    return hashlib.sha256(repr(sorted(rows)).encode()).hexdigest()[:12]


def inventory_checksum(path):
    """Hash of the whole inventory table in one DB file."""
    with connect(path) as c:
        return rows_checksum(c.execute("SELECT sku, stock FROM inventory").fetchall())
