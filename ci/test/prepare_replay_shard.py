#!/usr/bin/env python3
# Distributed under the MIT software license, see the accompanying
# file COPYING or https://opensource.org/license/mit/.
"""Stage a disjoint subset of a frozen Git corpus for the ordinary replay runner."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from typing import NamedTuple


class Fixture(NamedTuple):
    name: bytes
    mode: bytes
    oid: bytes
    size: int


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("qa_assets", type=Path)
    parser.add_argument("commit")
    parser.add_argument("group")
    parser.add_argument("shard", help="One-based index and shard count, e.g. 1/4")
    parser.add_argument("corpus_root", type=Path)
    args = parser.parse_args()

    if not re.fullmatch(r"[0-9a-f]{40}", args.commit) or not re.fullmatch(r"[a-z0-9_]+", args.group):
        parser.error("expected a full QA commit and a single replay group")
    try:
        index, count = map(int, args.shard.split("/"))
    except ValueError:
        parser.error("expected a shard in the form INDEX/COUNT")

    git = ["git", "-C", str(args.qa_assets)]
    tree = subprocess.check_output(
        [*git, "rev-parse", "--verify", f"{args.commit}:fuzz_corpora/{args.group}"], text=True,
    ).strip()
    listing = subprocess.check_output([*git, "ls-tree", "-rlz", tree])
    fixtures = []
    for record in listing.split(b"\0")[:-1]:
        header, name = record.split(b"\t", 1)
        mode, kind, oid, size = header.split()
        relative = Path(os.fsdecode(name))
        if kind != b"blob" or mode not in (b"100644", b"100755") or relative.is_absolute() or ".." in relative.parts:
            parser.error(f"expected a regular corpus file: {name!r}")
        fixtures.append(Fixture(name, mode, oid, int(size)))

    if not 1 <= index <= count <= len(fixtures):
        parser.error("each shard must select at least one file")
    fixtures.sort(key=lambda item: (-item.size, item.name))
    selected = fixtures[index - 1::count]

    group_dir = args.corpus_root / args.group
    group_dir.mkdir()
    manifest = hashlib.sha256()
    for item in sorted(selected, key=lambda item: item.name):
        destination = group_dir / os.fsdecode(item.name)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("xb") as output:
            subprocess.run([*git, "cat-file", "blob", item.oid.decode("ascii")], stdout=output, check=True)
        if destination.stat().st_size != item.size:
            raise ValueError(f"incomplete corpus file: {item.name!r}")
        destination.chmod(int(item.mode, 8) & 0o777)
        # Canonical git ls-tree -rz record, including the source blob identity.
        manifest.update(item.mode + b" blob " + item.oid + b"\t" + item.name + b"\0")

    print("Corpus shard manifest " + json.dumps({
        "qa_commit": args.commit,
        "group": args.group,
        "tree": tree,
        "shard": index,
        "shards": count,
        "total_files": len(fixtures),
        "files": len(selected),
        "bytes": sum(item.size for item in selected),
        "manifest_sha256": manifest.hexdigest(),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
