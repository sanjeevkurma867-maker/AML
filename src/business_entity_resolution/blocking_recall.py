import csv
import sqlite3
import time
import unicodedata
from pathlib import Path


# ============================================================
# CONFIG
# ============================================================

DATASET = Path("/Users/kurmasanjus/Downloads/student_resource/dataset")
TRAIN = DATASET / "train"

S1_FILE = TRAIN / "train_source1.tsv"
S2_FILE = TRAIN / "train_source2.tsv"
S3_FILE = TRAIN / "train_source3.tsv"
GT_FILE = TRAIN / "train_ground_truth.tsv"

DB_PATH = Path("output/blocking_recall.sqlite")

CHUNK_SIZE = 50_000


# ============================================================
# NORMALIZATION
# ============================================================

def normalize_text(text):
    """
    Conservative normalization.

    Keeps multilingual characters.
    """

    if not text:
        return ""

    text = unicodedata.normalize("NFKD", text)

    text = "".join(
        ch
        for ch in text
        if not unicodedata.combining(ch)
    )

    text = text.lower()

    text = "".join(
        ch if ch.isalnum() else " "
        for ch in text
    )

    return " ".join(text.split())


# ============================================================
# DATABASE
# ============================================================

def create_database():

    DB_PATH.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    # Remove old experiment database.
    for suffix in ("", "-wal", "-shm"):

        path = Path(
            str(DB_PATH) + suffix
        )

        if path.exists():
            path.unlink()

    conn = sqlite3.connect(DB_PATH)

    # SQLite performance settings.
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA temp_store=FILE")
    conn.execute("PRAGMA cache_size=-262144")

    conn.execute("""
        CREATE TABLE records (
            entity_id TEXT PRIMARY KEY,
            source TEXT NOT NULL,
            name_key TEXT NOT NULL,
            address_key TEXT NOT NULL,
            country TEXT NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE ground_truth (
            source1_entity_id TEXT NOT NULL,
            matched_entity_id TEXT NOT NULL
        )
    """)

    conn.commit()

    return conn


# ============================================================
# LOAD SOURCE DATA
# ============================================================

def load_source(conn, file_path, source_name):

    print()
    print("=" * 70)
    print(f"Loading {source_name}")
    print(file_path)
    print("=" * 70)

    start = time.time()

    rows = []
    count = 0

    with open(
        file_path,
        "r",
        encoding="utf-8",
        newline=""
    ) as f:

        reader = csv.DictReader(
            f,
            delimiter="\t"
        )

        for row in reader:

            entity_id = row["entity_id"]

            name_key = normalize_text(
                row.get(
                    "business_name",
                    ""
                )
            )

            address_key = normalize_text(
                row.get(
                    "business_address",
                    ""
                )
            )

            country = row.get(
                "country",
                ""
            ).strip()

            rows.append(
                (
                    entity_id,
                    source_name,
                    name_key,
                    address_key,
                    country
                )
            )

            count += 1

            if len(rows) >= CHUNK_SIZE:

                conn.executemany(
                    """
                    INSERT INTO records
                    (
                        entity_id,
                        source,
                        name_key,
                        address_key,
                        country
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    rows
                )

                conn.commit()

                rows.clear()

                if count % 500_000 == 0:

                    elapsed = time.time() - start

                    print(
                        f"{source_name}: "
                        f"{count:,} rows "
                        f"({elapsed:.1f}s)"
                    )

        if rows:

            conn.executemany(
                """
                INSERT INTO records
                (
                    entity_id,
                    source,
                    name_key,
                    address_key,
                    country
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                rows
            )

            conn.commit()

    elapsed = time.time() - start

    print(
        f"Finished {source_name}: "
        f"{count:,} rows "
        f"in {elapsed:.1f}s"
    )


# ============================================================
# LOAD GROUND TRUTH
# ============================================================

def load_ground_truth(conn):

    print()
    print("=" * 70)
    print("Loading ground truth")
    print("=" * 70)

    start = time.time()

    rows = []

    link_count = 0
    s1_count = 0

    with open(
        GT_FILE,
        "r",
        encoding="utf-8",
        newline=""
    ) as f:

        reader = csv.DictReader(
            f,
            delimiter="\t"
        )

        for row in reader:

            s1_id = row[
                "source1_entity_id"
            ]

            matched = row[
                "matched_entity_ids"
            ]

            s1_count += 1

            if not matched:
                continue

            for target_id in matched.split(","):

                target_id = target_id.strip()

                if not target_id:
                    continue

                rows.append(
                    (
                        s1_id,
                        target_id
                    )
                )

                link_count += 1

                if len(rows) >= CHUNK_SIZE:

                    conn.executemany(
                        """
                        INSERT INTO ground_truth
                        (
                            source1_entity_id,
                            matched_entity_id
                        )
                        VALUES (?, ?)
                        """,
                        rows
                    )

                    conn.commit()

                    rows.clear()

                    if link_count % 500_000 == 0:

                        elapsed = time.time() - start

                        print(
                            f"Ground-truth links: "
                            f"{link_count:,} "
                            f"({elapsed:.1f}s)"
                        )

        if rows:

            conn.executemany(
                """
                INSERT INTO ground_truth
                (
                    source1_entity_id,
                    matched_entity_id
                )
                VALUES (?, ?)
                """,
                rows
            )

            conn.commit()

    elapsed = time.time() - start

    print(
        f"S1 rows: "
        f"{s1_count:,}"
    )

    print(
        f"Ground-truth links: "
        f"{link_count:,}"
    )

    print(
        f"Loaded in "
        f"{elapsed:.1f}s"
    )


# ============================================================
# INDEXES
# ============================================================

def create_indexes(conn):

    print()
    print("=" * 70)
    print("Creating indexes")
    print("=" * 70)

    start = time.time()

    indexes = [

        (
            "idx_records_name",
            """
            CREATE INDEX idx_records_name
            ON records(name_key)
            """
        ),

        (
            "idx_records_address",
            """
            CREATE INDEX idx_records_address
            ON records(address_key)
            """
        ),

        (
            "idx_records_name_country",
            """
            CREATE INDEX idx_records_name_country
            ON records(name_key, country)
            """
        ),

        (
            "idx_records_address_country",
            """
            CREATE INDEX idx_records_address_country
            ON records(address_key, country)
            """
        ),

        (
            "idx_gt_source1",
            """
            CREATE INDEX idx_gt_source1
            ON ground_truth(source1_entity_id)
            """
        ),

        (
            "idx_gt_target",
            """
            CREATE INDEX idx_gt_target
            ON ground_truth(matched_entity_id)
            """
        )
    ]

    for name, sql in indexes:

        print(
            f"Creating {name}..."
        )

        conn.execute(sql)
        conn.commit()

    print(
        f"Indexes completed in "
        f"{time.time() - start:.1f}s"
    )


# ============================================================
# BLOCKING RECALL
# ============================================================

def evaluate_blocking(conn):

    print()
    print("=" * 70)
    print("EXACT BLOCKING RECALL")
    print("=" * 70)

    start = time.time()

    query = """

    SELECT

        COUNT(*) AS total_links,

        SUM(
            CASE
                WHEN
                    s1.name_key != ''
                    AND s1.name_key = t.name_key
                THEN 1
                ELSE 0
            END
        ) AS name_hits,

        SUM(
            CASE
                WHEN
                    s1.address_key != ''
                    AND s1.address_key = t.address_key
                THEN 1
                ELSE 0
            END
        ) AS address_hits,

        SUM(
            CASE
                WHEN
                    s1.name_key != ''
                    AND s1.name_key = t.name_key
                    AND s1.country = t.country
                THEN 1
                ELSE 0
            END
        ) AS name_country_hits,

        SUM(
            CASE
                WHEN
                    s1.address_key != ''
                    AND s1.address_key = t.address_key
                    AND s1.country = t.country
                THEN 1
                ELSE 0
            END
        ) AS address_country_hits,

        SUM(
            CASE
                WHEN
                    (
                        s1.name_key != ''
                        AND s1.name_key = t.name_key
                    )
                    OR
                    (
                        s1.address_key != ''
                        AND s1.address_key = t.address_key
                    )
                THEN 1
                ELSE 0
            END
        ) AS union_hits

    FROM ground_truth g

    JOIN records s1
        ON s1.entity_id =
           g.source1_entity_id

    JOIN records t
        ON t.entity_id =
           g.matched_entity_id

    """

    result = conn.execute(
        query
    ).fetchone()

    (
        total_links,
        name_hits,
        address_hits,
        name_country_hits,
        address_country_hits,
        union_hits
    ) = result

    print()

    print(
        f"Ground-truth links : "
        f"{total_links:,}"
    )

    print()

    print(
        f"{'Blocking pass':<28}"
        f"{'Hits':>15}"
        f"{'Recall':>12}"
    )

    print("-" * 55)

    def report(
        name,
        hits
    ):

        recall = (
            hits / total_links
            if total_links
            else 0.0
        )

        print(
            f"{name:<28}"
            f"{hits:>15,}"
            f"{recall * 100:>11.2f}%"
        )

    report(
        "Exact normalized name",
        name_hits
    )

    report(
        "Exact normalized address",
        address_hits
    )

    report(
        "Name + country",
        name_country_hits
    )

    report(
        "Address + country",
        address_country_hits
    )

    report(
        "Name OR address",
        union_hits
    )

    print()

    print(
        f"Evaluation time: "
        f"{time.time() - start:.1f}s"
    )


# ============================================================
# MAIN
# ============================================================

def main():

    overall_start = time.time()

    print()
    print("=" * 70)
    print("BUSINESS ENTITY RESOLUTION")
    print("MEMORY-EFFICIENT BLOCKING EXPERIMENT")
    print("=" * 70)

    print()
    print("Dataset:")
    print(DATASET)

    print()
    print("Database:")
    print(DB_PATH)

    conn = create_database()

    try:

        # ----------------------------------------------------
        # Load data
        # ----------------------------------------------------

        load_source(
            conn,
            S1_FILE,
            "S1"
        )

        load_source(
            conn,
            S2_FILE,
            "S2"
        )

        load_source(
            conn,
            S3_FILE,
            "S3"
        )

        # ----------------------------------------------------
        # Load ground truth
        # ----------------------------------------------------

        load_ground_truth(conn)

        # ----------------------------------------------------
        # Create indexes
        # ----------------------------------------------------

        create_indexes(conn)

        print()
        print("Running ANALYZE...")

        conn.execute(
            "ANALYZE"
        )

        conn.commit()

        # ----------------------------------------------------
        # Evaluate blocking
        # ----------------------------------------------------

        evaluate_blocking(conn)

    finally:

        conn.close()

    print()
    print("=" * 70)
    print("DONE")
    print("=" * 70)

    if DB_PATH.exists():

        size_gb = (
            DB_PATH.stat().st_size
            / (1024 ** 3)
        )

        print(
            f"SQLite database size: "
            f"{size_gb:.2f} GB"
        )

    print(
        f"Total runtime: "
        f"{time.time() - overall_start:.1f}s"
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()