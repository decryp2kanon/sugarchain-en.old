#!/usr/bin/env python3
# Copyright (c) 2026 The Sugarchain En developers
# Distributed under the MIT software license, see the accompanying file COPYING.
"""Fetch the hash-pinned, genuine Sugarchain legacy daemon for Linux CI."""

import argparse
import hashlib
import os
from pathlib import Path
import shutil
import tarfile
import urllib.request


TAG = "v0.16.5.2-visioneye"
ARCHIVE = "sugarchain-0.16.5.2-visioneye-x86_64-linux-gnu.tar.gz"
SHA256 = "2cfebb1af0436de90f8c142de6de710decc3713802800d1f7d7c9ab258e5900c"
URL = f"https://github.com/sugarchain-project/sugarchain/releases/download/{TAG}/{ARCHIVE}"


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-dir", required=True, type=Path)
    args = parser.parse_args()
    root = args.target_dir.resolve()
    root.mkdir(parents=True, exist_ok=True)
    archive = root / ARCHIVE
    if not archive.is_file():
        temporary = root / (ARCHIVE + ".part")
        with urllib.request.urlopen(URL, timeout=180) as response, temporary.open("wb") as output:
            shutil.copyfileobj(response, output)
        temporary.replace(archive)
    if digest(archive) != SHA256:
        raise RuntimeError("Legacy Sugarchain release archive checksum mismatch")
    binary = root / "sugarchaind"
    # Extract only the regular executable; no archive-provided path is trusted.
    with tarfile.open(archive, mode="r:gz") as source:
        candidates = [item for item in source.getmembers()
                      if item.isfile() and item.name.endswith("/bin/sugarchaind")]
        if len(candidates) != 1:
            raise RuntimeError("Legacy release must contain exactly one daemon")
        temporary_binary = root / "sugarchaind.part"
        with source.extractfile(candidates[0]) as stream, temporary_binary.open("wb") as output:
            shutil.copyfileobj(stream, output)
        os.chmod(temporary_binary, 0o755)
        temporary_binary.replace(binary)
    print(binary)


if __name__ == "__main__":
    main()
