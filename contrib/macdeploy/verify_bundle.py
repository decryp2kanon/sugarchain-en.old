#!/usr/bin/env python3
# Copyright (c) 2026 The Sugarchain developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or https://opensource.org/license/mit/.

"""Verify the contents of a cross-built macOS application archive."""

import argparse
from pathlib import Path
import plistlib
import struct
from zipfile import ZipFile


# Both Darwin cross builds produce thin 64-bit Mach-O executables.
MACH_CPU_TYPES = {"arm64": 0x0100000C, "aarch64": 0x0100000C, "x86_64": 0x01000007}


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def check_metadata(info):
    require(info["CFBundleName"] == "Sugarchain En", "Wrong application name")
    require(info["CFBundleIdentifier"] == "org.sugarchain.SugarchainEn", "Wrong bundle identity")
    require(info["CFBundleExecutable"] == "Sugarchain-Qt", "Wrong bundle executable")
    require("LSArchitecturePriority" not in info, "Bundle must use the host's native architecture")
    schemes = [scheme for entry in info["CFBundleURLTypes"] for scheme in entry["CFBundleURLSchemes"]]
    require(schemes == ["sugarchain"], "Wrong URI scheme")


def check_archive(path, architecture):
    contents = "Sugarchain En.app/Contents"
    with ZipFile(path) as archive:
        bad_member = archive.testzip()
        require(bad_member is None, f"Invalid ZIP checksum for {bad_member}")
        with archive.open(f"{contents}/Info.plist") as source:
            info = plistlib.load(source)
        check_metadata(info)
        icon = archive.getinfo(f"{contents}/Resources/{info['CFBundleIconFile']}")
        require(icon.file_size > 0, "Empty bundle icon")
        gui = archive.getinfo(f"{contents}/MacOS/{info['CFBundleExecutable']}")
        require((gui.external_attr >> 16) & 0o111, "Bundle executable lost its execute permission")
        with archive.open(gui) as source:
            header = source.read(32)

    require(len(header) == 32, "Incomplete 64-bit Mach-O header")
    magic, cpu_type, _subtype, file_type = struct.unpack_from("<4I", header)
    require(magic == 0xFEEDFACF and file_type == 2, "Expected a 64-bit Mach-O executable")
    require(cpu_type == MACH_CPU_TYPES[architecture],
            f"Expected {architecture} executable, got CPU type {cpu_type:#x}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("architecture", choices=MACH_CPU_TYPES)
    args = parser.parse_args()
    check_archive(args.archive, args.architecture)
    print(f"Verified {args.architecture} application in {args.archive}")
