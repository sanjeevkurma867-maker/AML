import pandas as pd
import re
import unicodedata
from collections import defaultdict

BASE = "/Users/kurmasanjus/Downloads/student_resource/dataset"


def normalize(text):
    if pd.isna(text):
        return ""

    text = str(text).lower()

    # Unicode normalization
    text = unicodedata.normalize("NFKC", text)

    # Remove accents where possible
    text = unicodedata.normalize("NFKD", text)
    text = "".join(
        c for c in text
        if not unicodedata.combining(c)
    )

    # Keep alphanumeric characters
    text = re.sub(r"[^a-z0-9]+", " ", text)

    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()

    return text


print("Loading training data...")

s1 = pd.read_csv(
    f"{BASE}/train/train_source1.tsv",
    sep="\t"
)

s2 = pd.read_csv(
    f"{BASE}/train/train_source2.tsv",
    sep="\t"
)

s3 = pd.read_csv(
    f"{BASE}/train/train_source3.tsv",
    sep="\t"
)

gt = pd.read_csv(
    f"{BASE}/train/train_ground_truth.tsv",
    sep="\t"
)

print("Loaded.")


# --------------------------------------------------
# NORMALIZATION
# --------------------------------------------------

for df in [s1, s2, s3]:

    df["name_norm"] = df["business_name"].map(normalize)
    df["address_norm"] = df["business_address"].map(normalize)

    df["name_address_norm"] = (
        df["name_norm"] + " " + df["address_norm"]
    )


# --------------------------------------------------
# BUILD EXACT LOOKUP TABLES
# --------------------------------------------------

def build_lookup(df, column):
    lookup = defaultdict(list)

    for entity_id, value in zip(
        df["entity_id"],
        df[column]
    ):
        if value:
            lookup[value].append(entity_id)

    return lookup


print("Building indexes...")

indexes = {}

for name, df in [
    ("s2", s2),
    ("s3", s3)
]:

    indexes[name] = {
        "name": build_lookup(df, "name_norm"),
        "address": build_lookup(df, "address_norm"),
        "name_address": build_lookup(df, "name_address_norm")
    }


# --------------------------------------------------
# GROUND TRUTH
# --------------------------------------------------

truth = {}

for _, row in gt.iterrows():

    ids = row["matched_entity_ids"]

    if pd.isna(ids) or not ids:
        truth[row["source1_entity_id"]] = set()
    else:
        truth[row["source1_entity_id"]] = set(
            ids.split(",")
        )


# --------------------------------------------------
# EVALUATE EXACT MATCH COVERAGE
# --------------------------------------------------

stats = {
    "total_truth_matches": 0,
    "name_found": 0,
    "address_found": 0,
    "name_address_found": 0,

    "name_exact_correct": 0,
    "address_exact_correct": 0,
    "name_address_exact_correct": 0
}


for _, row in s1.iterrows():

    s1_id = row["entity_id"]

    true_ids = truth.get(s1_id, set())

    name = row["name_norm"]
    address = row["address_norm"]
    combined = row["name_address_norm"]

    candidates = set()

    # Search S2 + S3
    for source in ["s2", "s3"]:

        if name:
            candidates.update(
                indexes[source]["name"].get(name, [])
            )

        if address:
            candidates.update(
                indexes[source]["address"].get(address, [])
            )

    # Exact name
    exact_name = set()

    for source in ["s2", "s3"]:
        exact_name.update(
            indexes[source]["name"].get(name, [])
        )

    # Exact address
    exact_address = set()

    for source in ["s2", "s3"]:
        exact_address.update(
            indexes[source]["address"].get(address, [])
        )

    # Exact combined
    exact_combined = set()

    for source in ["s2", "s3"]:
        exact_combined.update(
            indexes[source]["name_address"].get(
                combined, []
            )
        )

    stats["total_truth_matches"] += len(true_ids)

    stats["name_found"] += len(
        true_ids & exact_name
    )

    stats["address_found"] += len(
        true_ids & exact_address
    )

    stats["name_address_found"] += len(
        true_ids & exact_combined
    )

    stats["name_exact_correct"] += len(
        true_ids & exact_name
    )

    stats["address_exact_correct"] += len(
        true_ids & exact_address
    )

    stats["name_address_exact_correct"] += len(
        true_ids & exact_combined
    )


print("\n" + "=" * 70)
print("EXACT MATCH COVERAGE")
print("=" * 70)

total = stats["total_truth_matches"]

for label, key in [
    ("Name", "name_exact_correct"),
    ("Address", "address_exact_correct"),
    ("Name + Address", "name_address_exact_correct")
]:

    value = stats[key]

    print(
        f"{label:20s}: "
        f"{value:,} / {total:,} "
        f"= {value / total:.2%}"
    )