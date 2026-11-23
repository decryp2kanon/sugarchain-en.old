#!/usr/bin/env python3
# Copyright (c) 2026 The Sugarchain developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or https://opensource.org/license/mit/.

"""Verify a native shared-Qt macOS deployment on a fresh GitHub-hosted runner."""

import argparse
import base64
import http.client
import json
import os
from pathlib import Path
import platform
import plistlib
import socket
import subprocess
import sys
import time

from verify_bundle import check_metadata, require


class Node:
    def __init__(self, binary, directory, chain, gui=False, restart=False):
        if gui:
            require(sys.platform == "darwin" and os.environ.get("GITHUB_ACTIONS") == "true",
                    "Packaged GUI verification requires a native macOS CI runner")
        self.directory = directory
        self.chain = chain
        directory.mkdir(exist_ok=restart)
        with socket.socket() as port_socket:
            port_socket.bind(("127.0.0.1", 0))
            self.port = port_socket.getsockname()[1]
        self.cookie = directory / ("regtest/.cookie" if chain == "regtest" else ".cookie")
        args = [str(binary), f"-datadir={directory}", f"-chain={chain}", "-server=1",
                "-listen=0", "-listenonion=0", "-connect=0", "-dnsseed=0",
                "-fixedseeds=0", "-discover=0", "-natpmp=0", "-networkactive=0",
                "-maxconnections=0", "-rpcbind=127.0.0.1", "-rpcallowip=127.0.0.1",
                f"-rpcport={self.port}", "-dbcache=16", "-par=1", "-printtoconsole=0"]
        if chain == "regtest":
            args.append("-fallbackfee=0.0002")
        if gui:
            args.append("-splash=0")
        env = dict(os.environ)
        for name in ("QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH", "DYLD_LIBRARY_PATH",
                     "DYLD_FRAMEWORK_PATH", "QT_QPA_PLATFORM"):
            env.pop(name, None)
        if gui:
            env["QT_QPA_PLATFORM"] = "cocoa"
        self.log = (directory / "process.log").open("wb")
        self.process = subprocess.Popen(args, stdout=self.log, stderr=subprocess.STDOUT, env=env)

    def rpc(self, method, *params):
        credentials = base64.b64encode(self.cookie.read_bytes().strip()).decode("ascii")
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            connection.request("POST", "/", json.dumps({"jsonrpc": "2.0", "id": 1,
                                                       "method": method, "params": params}),
                               {"Authorization": "Basic " + credentials})
            response = connection.getresponse()
            payload = json.loads(response.read())
            require(response.status == 200 and payload.get("error") is None,
                    f"RPC {method} failed: {payload.get('error')}")
            return payload["result"]
        finally:
            connection.close()

    def startup_error(self, message):
        with (self.directory / "process.log").open("rb") as process_log:
            process_log.seek(0, os.SEEK_END)
            process_log.seek(max(0, process_log.tell() - 4096))
            output = process_log.read(4096).decode("utf-8", errors="replace")
        return RuntimeError(f"{message}; see {self.directory}\n{output}")

    def __enter__(self):
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                self.log.close()
                raise self.startup_error("Node exited before RPC")
            try:
                self.rpc("getblockcount")
                return self
            except (OSError, ValueError, RuntimeError, http.client.HTTPException):
                time.sleep(0.1)
        try:
            self.close()
        except (OSError, RuntimeError, subprocess.TimeoutExpired) as cleanup_error:
            raise self.startup_error("RPC startup timed out") from cleanup_error
        raise self.startup_error("RPC startup timed out")

    def close(self):
        if self.process.poll() is None:
            try:
                self.rpc("stop")
                self.process.wait(timeout=30)
            except (OSError, ValueError, RuntimeError, http.client.HTTPException, subprocess.TimeoutExpired):
                self.process.terminate()
                self.process.wait(timeout=30)
        self.log.close()
        require(self.process.returncode == 0, f"Node did not shut down cleanly: {self.directory}")

    def __exit__(self, _exc_type, _exc, _traceback):
        self.close()


def check_chain(node, chain):
    info = node.rpc("getblockchaininfo")
    network = node.rpc("getnetworkinfo")
    require(info["chain"] == chain, "Wrong chain selected")
    require(network["networkactive"] is False and network["connections"] == 0,
            "Runtime verification must remain offline")
    return info


def check_version(binary, work):
    directory = work / binary.name
    directory.mkdir(parents=True)
    command = [str(binary), "--version" if binary.name == "sugarchain" else "-version"]
    if binary.name in ("sugarchaind", "sugarchain-cli", "sugarchain-wallet"):
        command.append(f"-datadir={directory}")
    probe = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           text=True, errors="replace", timeout=30, check=False)
    (directory / "version.log").write_text(probe.stdout)
    require(probe.returncode == 0,
            f"{binary.name} version probe failed ({probe.returncode}):\n{probe.stdout[-4096:]}")
    require("Sugarchain En" in probe.stdout, f"Wrong version identity for {binary.name}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", type=Path, required=True)
    parser.add_argument("--bindir", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    args = parser.parse_args()
    require(sys.platform == "darwin", "Native macOS is required")
    require(os.environ.get("GITHUB_ACTIONS") == "true", "Use a fresh GitHub-hosted runner")
    runner_temp = Path(os.environ["RUNNER_TEMP"]).resolve()
    work = args.work_dir.resolve()
    require(work.is_relative_to(runner_temp) and work != runner_temp,
            "The work directory must be a new child of RUNNER_TEMP")
    # macOS NativeFormat QSettings uses CFPreferences rather than XDG paths.
    # Refuse existing profiles; this script must never migrate a user's settings.
    preferences = Path.home() / "Library/Preferences"
    require(not any("sugarchain" in path.name.casefold() for path in preferences.glob("*.plist")),
            "Existing Sugarchain preferences must be preserved; use a fresh runner")
    work.mkdir()

    app = args.app.resolve()
    bindir = args.bindir.resolve()
    with (app / "Contents/Info.plist").open("rb") as source:
        info = plistlib.load(source)
    check_metadata(info)
    gui = app / "Contents/MacOS" / info["CFBundleExecutable"]
    linked = subprocess.check_output(["otool", "-L", str(gui)], text=True)
    require(any(("/Qt" in line and ".framework/" in line) or "/libQt" in line
                for line in linked.splitlines()[1:]),
            "This helper covers native shared-Qt deployments; static depends bundles need separate native validation")
    require((app / "Contents/Resources" / info["CFBundleIconFile"]).is_file(), "Missing bundle icon")
    require((app / "Contents/PlugIns/platforms/libqminimal.dylib").is_file(), "Missing minimal Qt plugin")
    require((app / "Contents/PlugIns/platforms/libqcocoa.dylib").is_file(), "Missing Cocoa Qt plugin")
    subprocess.run(["codesign", "--verify", "--deep", "--strict", str(app)], check=True)
    architectures = subprocess.check_output(["lipo", "-archs", str(gui)], text=True).split()
    require(platform.machine() in architectures, "The native runner architecture is missing")
    for binary in ("sugarchain", "sugarchaind", "sugarchain-cli", "sugarchain-wallet",
                   "sugarchain-tx", "sugarchain-util"):
        check_version(bindir / binary, work / "versions")

    results = {"platform": platform.platform(), "architectures": architectures,
               "bundle_identity": True, "bundle_signature": True,
               "qt_platform": "cocoa", "interactive_ui_actions_verified": False, "runs": []}
    for label, binary, chain, is_gui in (("daemon-main", bindir / "sugarchaind", "main", False),
                                         ("bundle-main", gui, "main", True),
                                         ("bundle-regtest", gui, "regtest", True)):
        directory = work / label
        with Node(binary, directory, chain, is_gui) as node:
            require(check_chain(node, chain)["blocks"] == 0, "Expected a fresh chain")
            cli = subprocess.check_output([str(bindir / "sugarchain-cli"), f"-datadir={directory}",
                                           f"-chain={chain}", f"-rpcport={node.port}",
                                           "getblockcount"], text=True)
            require(cli.strip() == "0", "Installed CLI did not reach the isolated node")
            row = {"mode": label, "offline": True, "cli_rpc": True}
            node.rpc("createwallet", "native-smoke")
            address = node.rpc("getnewaddress", "", "bech32")
            if chain == "main":
                require(address.startswith("sugar1q"), "Expected a native mainnet address")
                row["native_mainnet_address"] = True
            else:
                node.rpc("generatetoaddress", 101, address)
                txid = node.rpc("sendtoaddress", node.rpc("getnewaddress"), 1)
                node.rpc("generatetoaddress", 1, address)
                require(node.rpc("gettransaction", txid)["confirmations"] == 1,
                        "Wallet transfer was not confirmed")
                backup = work / "wallet-backup.sqlite"
                node.rpc("backupwallet", str(backup))
                require(backup.is_file() and backup.stat().st_size > 0, "Wallet backup is missing")
                row.update(wallet_send_confirmed=True, wallet_backup=True)
            results["runs"].append(row)
        row["shutdown_exit"] = node.process.returncode
        print(f"{label}: startup, installed CLI, wallet, normal shutdown passed", flush=True)
        if chain == "regtest":
            with Node(binary, directory, chain, is_gui, restart=True) as restarted:
                require(check_chain(restarted, chain)["blocks"] == 102, "Chain did not survive restart")
                if "native-smoke" not in restarted.rpc("listwallets"):
                    restarted.rpc("loadwallet", "native-smoke")
                require(restarted.rpc("gettransaction", txid)["confirmations"] == 1,
                        "Wallet transaction did not survive restart")
                restarted.rpc("unloadwallet", "native-smoke")
                restarted.rpc("restorewallet", "restored-smoke", str(backup))
                require(restarted.rpc("gettransaction", txid)["confirmations"] == 1,
                        "Restored wallet lost the confirmed transaction")
            row.update(wallet_restart=True, wallet_restore=True,
                       restart_shutdown_exit=restarted.process.returncode)
            print(f"{label}: restart and wallet restoration passed", flush=True)

    (work / "results.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
