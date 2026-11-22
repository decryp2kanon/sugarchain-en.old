#!/usr/bin/env python3
# Copyright (c) 2026 The Sugarchain En developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or https://opensource.org/license/mit/.

"""Verify silent install, in-place upgrade, native runtime, and safe uninstall."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys


def nsis_command(program, install_dir, uninstall=False):
    # NSIS consumes the entire final /D= or _?= suffix, including spaces.
    # Python's list2cmdline would quote this argument and change NSIS parsing.
    if '"' in str(program) or '"' in str(install_dir):
        raise ValueError("NSIS command paths must not contain quotes")
    suffix = "_?=" if uninstall else "/D="
    return f'"{program}" /S {suffix}{install_dir}'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installer", required=True, type=Path)
    parser.add_argument("--work-dir", required=True, type=Path)
    parser.add_argument("--with-wallet-restart", action="store_true",
                        help="Check persistence across two native GUI launches after upgrading the installation")
    args = parser.parse_args()
    if os.name != "nt" or os.environ.get("GITHUB_ACTIONS") != "true":
        parser.error("Installer checks require an ephemeral Windows GitHub Actions runner")
    import winreg

    installer = args.installer.resolve(strict=True)
    workdir = args.work_dir.resolve()
    workdir.mkdir(parents=True, exist_ok=False)
    install = workdir / "Sugarchain En install"
    keyname = r"SOFTWARE\Sugarchain En"

    def registry_value(name):
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, keyname, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
            return winreg.QueryValueEx(key, name)[0]

    try:
        registry_value("Path")
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("Refusing to overwrite an existing registered installation")

    command = nsis_command(installer, install)
    subprocess.run(command, check=True, timeout=180, shell=False)
    programs = [install / name for name in ("sugarchain.exe", "sugarchain-qt.exe")]
    programs += [install / "daemon" / name for name in ("sugarchaind.exe", "sugarchain-cli.exe", "sugarchain-wallet.exe", "sugarchain-tx.exe", "sugarchain-util.exe")]
    assert all(path.is_file() for path in programs), programs
    assert not list(install.rglob("test_bitcoin*.exe")), "Production installer contains test programs"
    assert not list(install.rglob("bench_*.exe")), "Production installer contains benchmarks"
    assert Path(registry_value("Path")) == install
    startmenu = Path(os.environ["APPDATA"]) / "Microsoft/Windows/Start Menu/Programs" / registry_value("StartMenuGroup")
    obsolete = [startmenu / f"Sugarchain En ({network}).lnk" for network in ("testnet", "testnet4", "test signet")]
    assert not any(path.exists() for path in obsolete)

    config = install / "sugarchain.conf"
    config.write_text("# CI configuration preservation sentinel\nlisten=0\n")
    extra = install / "user-file.txt"
    extra.write_text("Installer must preserve unowned files.\n")
    expected_config = config.read_bytes()
    expected_extra = extra.read_bytes()
    for path in obsolete:
        path.write_text("Obsolete launcher sentinel\n")
    subprocess.run(command, check=True, timeout=180, shell=False)
    assert config.read_bytes() == expected_config
    assert extra.read_bytes() == expected_extra
    assert not any(path.exists() for path in obsolete)

    smoke = Path(__file__).with_name("ci-windows-smoke.py")
    smoke_command = [sys.executable, str(smoke), "--bindir", str(install)]
    if args.with_wallet_restart:
        subprocess.run([*smoke_command, "--verify-wallet-restart", "--work-dir", str(workdir / "installed-wallet-restart")],
                       check=True, timeout=300)
    subprocess.run([*smoke_command, "--work-dir", str(workdir / "installed-runtime")], check=True, timeout=300)
    # Use no shell; all paths belong to this fresh runner-specific workspace.
    uninstaller = install / "uninstall.exe"
    subprocess.run(nsis_command(uninstaller, install, uninstall=True), check=True, timeout=180, shell=False)
    assert not any(path.exists() for path in programs), "Uninstaller left packaged production programs"
    assert config.read_bytes() == expected_config
    assert extra.read_bytes() == expected_extra
    report = {"production_binaries": len(programs), "install": "passed", "upgrade": "passed", "native_runtime": "passed", "uninstall_preserves_user_files": "passed"}
    if args.with_wallet_restart:
        report["gui_wallet_restart"] = "passed"
    (workdir / "installer-results.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
