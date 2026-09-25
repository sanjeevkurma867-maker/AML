import sqlite3
import time
import re
from collections import Counter

DB = "output/blocking_recall.sqlite"


def tokens(text):
    if not text:
        return set()
    return set(text.split())


def numbers(text):
    if not text:
        return set()
    return set(re.findall(r"\d+", text))


conn = sqlite3.connect(DB)
conn.execute("PRAGMA synchronous=NORMAL")
cur = conn.cursor()

print("=" * 70)
print("BUSINESS ENTITY RESOLUTION")
print("V3 MISSED-LINK ANALYSIS")
print("=" * 70)

start = time.time()

print("\nLoading ground-truth links...")
print("Reading links and classifying blocking signals...")

query = """
SELECT
    g.source1_entity_id,
    g.matched_entity_id,

    s1.name_key,
    s1.address_key,
    s1.country,

    s2.name_key,
    s2.address_key,
    s2.country

FROM ground_truth g

JOIN records s1
    ON s1.entity_id = g.source1_entity_id
   AND s1.source = 'S1'

JOIN records s2
    ON s2.entity_id = g.matched_entity_id
   AND s2.source IN ('S2', 'S3')
"""

total = 0
covered = 0
missed = 0

categories = Counter()
name_overlap = Counter()
address_overlap = Counter()

sample_misses = []

for row in cur.execute(query):

    (
        s1_id,
        s2_id,
        name1,
        addr1,
        country1,
        name2,
        addr2,
        country2
    ) = row

    total += 1

    name1 = name1 or ""
    name2 = name2 or ""
    addr1 = addr1 or ""
    addr2 = addr2 or ""

    n1 = tokens(name1)
    n2 = tokens(name2)

    a1 = tokens(addr1)
    a2 = tokens(addr2)

    nums1 = numbers(addr1)
    nums2 = numbers(addr2)

    # ------------------------------------------------------------
    # Existing V1/V2-style signals
    # ------------------------------------------------------------

    exact_name = bool(name1 and name1 == name2)
    exact_address = bool(addr1 and addr1 == addr2)

    shared_name_token = bool(n1 & n2)
    shared_address_token = bool(a1 & a2)
    shared_number = bool(nums1 & nums2)

    covered_by_existing = (
        exact_name
        or exact_address
        or shared_name_token
        or shared_address_token
        or shared_number
    )

    if covered_by_existing:
        covered += 1
        continue

    missed += 1

    # ------------------------------------------------------------
    # NAME DIAGNOSTICS
    # ------------------------------------------------------------

    name_intersection = n1 & n2
    name_union = n1 | n2

    if name_union:
        ratio = len(name_intersection) / len(name_union)

        if ratio >= 0.75:
            name_overlap["75%+"] += 1
        elif ratio >= 0.50:
            name_overlap["50-74%"] += 1
        elif ratio > 0:
            name_overlap["1-49%"] += 1
        else:
            name_overlap["0%"] += 1

    if (
        len(name1) >= 4
        and len(name2) >= 4
        and name1[:4] == name2[:4]
    ):
        categories["name_prefix4"] += 1

    if (
        len(name1) >= 4
        and len(name2) >= 4
        and name1[-4:] == name2[-4:]
    ):
        categories["name_suffix4"] += 1

    if name1 and name2 and name1[0] == name2[0]:
        categories["same_name_first_char"] += 1

    # ------------------------------------------------------------
    # ADDRESS DIAGNOSTICS
    # ------------------------------------------------------------

    address_intersection = a1 & a2
    address_union = a1 | a2

    if address_union:
        ratio = len(address_intersection) / len(address_union)

        if ratio >= 0.75:
            address_overlap["75%+"] += 1
        elif ratio >= 0.50:
            address_overlap["50-74%"] += 1
        elif ratio > 0:
            address_overlap["1-49%"] += 1
        else:
            address_overlap["0%"] += 1

    if (
        len(addr1) >= 4
        and len(addr2) >= 4
        and addr1[:4] == addr2[:4]
    ):
        categories["address_prefix4"] += 1

    if country1 == country2:
        categories["same_country"] += 1

    # ------------------------------------------------------------
    # SAMPLE MISSES
    # ------------------------------------------------------------

    if len(sample_misses) < 30:
        sample_misses.append(
            (
                s1_id,
                s2_id,
                name1,
                name2,
                addr1,
                addr2,
                country1,
                country2
            )
        )


print("\n" + "=" * 70)
print("V3 MISS ANALYSIS")
print("=" * 70)

print(f"\nTotal GT links:        {total:,}")
print(f"Covered by V1+V2:     {covered:,}")
print(f"Missed by V1+V2:      {missed:,}")

if total:
    print(
        f"Miss percentage:      "
        f"{missed / total * 100:.2f}%"
    )


print("\nPotential signals among MISSES")
print("-" * 70)

for key, value in categories.most_common():

    pct = value / missed * 100 if missed else 0

    print(
        f"{key:30s}"
        f"{value:12,}"
        f"{pct:8.2f}%"
    )


print("\nName token overlap among MISSES")
print("-" * 70)

for key in [
    "75%+",
    "50-74%",
    "1-49%",
    "0%"
]:

    value = name_overlap[key]
    pct = value / missed * 100 if missed else 0

    print(
        f"{key:30s}"
        f"{value:12,}"
        f"{pct:8.2f}%"
    )


print("\nAddress token overlap among MISSES")
print("-" * 70)

for key in [
    "75%+",
    "50-74%",
    "1-49%",
    "0%"
]:

    value = address_overlap[key]
    pct = value / missed * 100 if missed else 0

    print(
        f"{key:30s}"
        f"{value:12,}"
        f"{pct:8.2f}%"
    )


print("\n" + "=" * 70)
print("SAMPLE MISSED LINKS")
print("=" * 70)

for i, row in enumerate(sample_misses, 1):

    (
        s1_id,
        s2_id,
        name1,
        name2,
        addr1,
        addr2,
        country1,
        country2
    ) = row

    print(f"\n[{i}]")
    print(f"S1 ID       : {s1_id}")
    print(f"S2/S3 ID    : {s2_id}")
    print(f"Country     : {country1} -> {country2}")
    print(f"S1 Name     : {name1}")
    print(f"S2/S3 Name  : {name2}")
    print(f"S1 Address  : {addr1}")
    print(f"S2/S3 Addr  : {addr2}")


print("\n" + "=" * 70)
print(f"Analysis completed in {time.time() - start:.1f}s")
print("=" * 70)

conn.close()