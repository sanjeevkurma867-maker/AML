import csv
import re
import sqlite3
import time
from collections import Counter
from pathlib import Path


# ============================================================
# CONFIG
# ============================================================

DB_PATH = Path("output/blocking_recall.sqlite")

MAX_NAME_TOKEN_DF = 100
MAX_ADDRESS_TOKEN_DF = 100

CHUNK_SIZE = 50_000


# ============================================================
# TOKENIZATION
# ============================================================

def tokens(text):
    if not text:
        return []

    return text.split()


def numeric_tokens(text):
    if not text:
        return []

    return re.findall(r"\d+", text)


# ============================================================
# ADD V2 TABLES
# ============================================================

def create_v2_tables(conn):

    print()
    print("=" * 70)
    print("CREATING V2 BLOCKING TABLES")
    print("=" * 70)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS name_token_stats (
            token TEXT PRIMARY KEY,
            df INTEGER NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS address_token_stats (
            token TEXT PRIMARY KEY,
            df INTEGER NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS rare_name_tokens (
            entity_id TEXT NOT NULL,
            token TEXT NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS rare_address_tokens (
            entity_id TEXT NOT NULL,
            token TEXT NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS number_tokens (
            entity_id TEXT NOT NULL,
            number TEXT NOT NULL
        )
    """)

    conn.commit()


# ============================================================
# TOKEN FREQUENCY
# ============================================================

def calculate_token_frequencies(conn):

    print()
    print("=" * 70)
    print("CALCULATING TOKEN FREQUENCIES")
    print("=" * 70)

    start = time.time()

    name_counts = Counter()
    address_counts = Counter()

    cursor = conn.execute("""
        SELECT name_key, address_key
        FROM records
    """)

    processed = 0

    while True:

        rows = cursor.fetchmany(CHUNK_SIZE)

        if not rows:
            break

        for name_key, address_key in rows:

            # Count each token once per record.
            name_counts.update(
                set(tokens(name_key))
            )

            address_counts.update(
                set(tokens(address_key))
            )

        processed += len(rows)

        if processed % 500_000 == 0:

            print(
                f"Processed "
                f"{processed:,} records"
            )

    print(
        f"Unique name tokens: "
        f"{len(name_counts):,}"
    )

    print(
        f"Unique address tokens: "
        f"{len(address_counts):,}"
    )

    # Store frequencies.
    conn.executemany(
        """
        INSERT OR REPLACE INTO name_token_stats
        (token, df)
        VALUES (?, ?)
        """,
        name_counts.items()
    )

    conn.executemany(
        """
        INSERT OR REPLACE INTO address_token_stats
        (token, df)
        VALUES (?, ?)
        """,
        address_counts.items()
    )

    conn.commit()

    print(
        f"Frequency calculation completed "
        f"in {time.time() - start:.1f}s"
    )


# ============================================================
# BUILD RARE TOKEN INDEXES
# ============================================================

def build_rare_token_indexes(conn):

    print()
    print("=" * 70)
    print("BUILDING RARE TOKEN INDEXES")
    print("=" * 70)

    start = time.time()

    # --------------------------------------------------------
    # Load rare token sets.
    # --------------------------------------------------------

    rare_name = {
        row[0]
        for row in conn.execute(
            """
            SELECT token
            FROM name_token_stats
            WHERE df <= ?
            """,
            (MAX_NAME_TOKEN_DF,)
        )
    }

    rare_address = {
        row[0]
        for row in conn.execute(
            """
            SELECT token
            FROM address_token_stats
            WHERE df <= ?
            """,
            (MAX_ADDRESS_TOKEN_DF,)
        )
    }

    print(
        f"Rare name tokens: "
        f"{len(rare_name):,}"
    )

    print(
        f"Rare address tokens: "
        f"{len(rare_address):,}"
    )

    # --------------------------------------------------------
    # Build inverted indexes.
    # --------------------------------------------------------

    cursor = conn.execute("""
        SELECT entity_id, name_key, address_key
        FROM records
    """)

    name_rows = []
    address_rows = []
    number_rows = []

    processed = 0

    while True:

        rows = cursor.fetchmany(CHUNK_SIZE)

        if not rows:
            break

        for entity_id, name_key, address_key in rows:

            # Rare name tokens.
            for token in set(tokens(name_key)):

                if token in rare_name:

                    name_rows.append(
                        (
                            entity_id,
                            token
                        )
                    )

            # Rare address tokens.
            for token in set(tokens(address_key)):

                if token in rare_address:

                    address_rows.append(
                        (
                            entity_id,
                            token
                        )
                    )

            # Numeric fragments.
            for number in set(
                numeric_tokens(address_key)
            ):

                if len(number) >= 2:

                    number_rows.append(
                        (
                            entity_id,
                            number
                        )
                    )

        if len(name_rows) >= CHUNK_SIZE:

            conn.executemany(
                """
                INSERT INTO rare_name_tokens
                (entity_id, token)
                VALUES (?, ?)
                """,
                name_rows
            )

            name_rows.clear()

        if len(address_rows) >= CHUNK_SIZE:

            conn.executemany(
                """
                INSERT INTO rare_address_tokens
                (entity_id, token)
                VALUES (?, ?)
                """,
                address_rows
            )

            address_rows.clear()

        if len(number_rows) >= CHUNK_SIZE:

            conn.executemany(
                """
                INSERT INTO number_tokens
                (entity_id, number)
                VALUES (?, ?)
                """,
                number_rows
            )

            number_rows.clear()

        processed += len(rows)

        if processed % 500_000 == 0:

            print(
                f"Indexed "
                f"{processed:,} records"
            )

    # Flush remaining rows.

    if name_rows:

        conn.executemany(
            """
            INSERT INTO rare_name_tokens
            (entity_id, token)
            VALUES (?, ?)
            """,
            name_rows
        )

    if address_rows:

        conn.executemany(
            """
            INSERT INTO rare_address_tokens
            (entity_id, token)
            VALUES (?, ?)
            """,
            address_rows
        )

    if number_rows:

        conn.executemany(
            """
            INSERT INTO number_tokens
            (entity_id, number)
            VALUES (?, ?)
            """,
            number_rows
        )

    conn.commit()

    print("Creating indexes...")

    conn.execute("""
        CREATE INDEX IF NOT EXISTS
        idx_rare_name_token
        ON rare_name_tokens(token)
    """)

    conn.execute("""
        CREATE INDEX IF NOT EXISTS
        idx_rare_name_entity
        ON rare_name_tokens(entity_id)
    """)

    conn.execute("""
        CREATE INDEX IF NOT EXISTS
        idx_rare_address_token
        ON rare_address_tokens(token)
    """)

    conn.execute("""
        CREATE INDEX IF NOT EXISTS
        idx_rare_address_entity
        ON rare_address_tokens(entity_id)
    """)

    conn.execute("""
        CREATE INDEX IF NOT EXISTS
        idx_number_token
        ON number_tokens(number)
    """)

    conn.execute("""
        CREATE INDEX IF NOT EXISTS
        idx_number_entity
        ON number_tokens(entity_id)
    """)

    conn.commit()

    print(
        f"Rare-token indexing completed "
        f"in {time.time() - start:.1f}s"
    )


# ============================================================
# EVALUATE V2 RECALL
# ============================================================

def evaluate_v2(conn):

    print()
    print("=" * 70)
    print("V2 BLOCKING RECALL")
    print("=" * 70)

    start = time.time()

    # --------------------------------------------------------
    # Rare name token recall
    # --------------------------------------------------------

    query_name = """
        SELECT COUNT(DISTINCT g.matched_entity_id)

        FROM ground_truth g

        JOIN rare_name_tokens r1
            ON r1.entity_id =
               g.source1_entity_id

        JOIN rare_name_tokens r2
            ON r2.entity_id =
               g.matched_entity_id

        WHERE r1.token = r2.token
    """

    name_hits = conn.execute(
        query_name
    ).fetchone()[0]

    # --------------------------------------------------------
    # Rare address token recall
    # --------------------------------------------------------

    query_address = """
        SELECT COUNT(DISTINCT g.matched_entity_id)

        FROM ground_truth g

        JOIN rare_address_tokens r1
            ON r1.entity_id =
               g.source1_entity_id

        JOIN rare_address_tokens r2
            ON r2.entity_id =
               g.matched_entity_id

        WHERE r1.token = r2.token
    """

    address_hits = conn.execute(
        query_address
    ).fetchone()[0]

    # --------------------------------------------------------
    # Numeric address recall
    # --------------------------------------------------------

    query_number = """
        SELECT COUNT(DISTINCT g.matched_entity_id)

        FROM ground_truth g

        JOIN number_tokens n1
            ON n1.entity_id =
               g.source1_entity_id

        JOIN number_tokens n2
            ON n2.entity_id =
               g.matched_entity_id

        WHERE n1.number = n2.number
    """

    number_hits = conn.execute(
        query_number
    ).fetchone()[0]

    # --------------------------------------------------------
    # Total links
    # --------------------------------------------------------

    total_links = conn.execute(
        """
        SELECT COUNT(*)
        FROM ground_truth
        """
    ).fetchone()[0]

    print()

    print(
        f"Ground-truth links: "
        f"{total_links:,}"
    )

    print()

    print(
        f"{'Blocking pass':<32}"
        f"{'Hits':>15}"
        f"{'Recall':>12}"
    )

    print("-" * 60)

    def report(
        name,
        hits
    ):

        recall = (
            hits / total_links
            if total_links
            else 0
        )

        print(
            f"{name:<32}"
            f"{hits:>15,}"
            f"{recall * 100:>11.2f}%"
        )

    report(
        "Rare name token",
        name_hits
    )

    report(
        "Rare address token",
        address_hits
    )

    report(
        "Shared address number",
        number_hits
    )

    # --------------------------------------------------------
    # Combined V1 + V2 recall.
    # --------------------------------------------------------

    combined_query = """

        SELECT COUNT(DISTINCT g.rowid)

        FROM ground_truth g

        JOIN records s1
            ON s1.entity_id =
               g.source1_entity_id

        JOIN records t
            ON t.entity_id =
               g.matched_entity_id

        WHERE

            (
                s1.name_key != ''
                AND s1.name_key = t.name_key
            )

            OR

            (
                s1.address_key != ''
                AND s1.address_key = t.address_key
            )

            OR EXISTS (

                SELECT 1

                FROM rare_name_tokens a

                JOIN rare_name_tokens b
                    ON a.token = b.token

                WHERE
                    a.entity_id =
                        g.source1_entity_id

                    AND
                    b.entity_id =
                        g.matched_entity_id
            )

            OR EXISTS (

                SELECT 1

                FROM rare_address_tokens a

                JOIN rare_address_tokens b
                    ON a.token = b.token

                WHERE
                    a.entity_id =
                        g.source1_entity_id

                    AND
                    b.entity_id =
                        g.matched_entity_id
            )

            OR EXISTS (

                SELECT 1

                FROM number_tokens a

                JOIN number_tokens b
                    ON a.number = b.number

                WHERE
                    a.entity_id =
                        g.source1_entity_id

                    AND
                    b.entity_id =
                        g.matched_entity_id
            )
    """

    combined_hits = conn.execute(
        combined_query
    ).fetchone()[0]

    report(
        "V1 + V2 combined",
        combined_hits
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

    start = time.time()

    print()
    print("=" * 70)
    print("BUSINESS ENTITY RESOLUTION")
    print("V2 STRONGER BLOCKING")
    print("=" * 70)

    if not DB_PATH.exists():

        raise FileNotFoundError(
            f"Database not found: {DB_PATH}"
        )

    print()
    print(
        f"Using database: {DB_PATH}"
    )

    conn = sqlite3.connect(
        DB_PATH,
        timeout=120
    )

    try:

        create_v2_tables(
            conn
        )

        calculate_token_frequencies(
            conn
        )

        build_rare_token_indexes(
            conn
        )

        conn.execute(
            "ANALYZE"
        )

        conn.commit()

        evaluate_v2(
            conn
        )

    finally:

        conn.close()

    print()
    print("=" * 70)
    print("V2 COMPLETE")
    print("=" * 70)

    print(
        f"Total runtime: "
        f"{time.time() - start:.1f}s"
    )


if __name__ == "__main__":
    main()
    