#!/usr/bin/env python3
# Copyright (c) 2026 The Sugarchain En developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or https://opensource.org/license/mit/.

"""Exercise native production binaries with isolated, offline data directories."""

import argparse
import base64
import contextlib
import json
import os
from pathlib import Path, PureWindowsPath
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET


def runtime_environment(datadir, platform=None):
    platform = os.name if platform is None else platform
    env = os.environ.copy()
    for kind in ("CONFIG", "DATA", "CACHE"):
        env[f"XDG_{kind}_HOME"] = str(datadir / f"xdg-{kind.lower()}")
    # The minimal plugin cannot load application fonts. Windows runners
    # provide the native desktop; Linux's dynamic Qt build has offscreen.
    env["QT_QPA_PLATFORM"] = "windows" if platform == "nt" else "offscreen"
    if platform != "nt":
        env["DBUS_SESSION_BUS_ADDRESS"] = "unix:path=/nonexistent-sugarchain-en-ci-bus"
    return env


def check_version(binary, program, datadir, env, platform=None):
    platform = os.name if platform is None else platform
    windows_gui = platform == "nt" and program == "sugarchain-qt"
    if windows_gui:
        # Windows displays -version in a modal dialog. Read its version resource
        # with the stock .NET API; the GUI still undergoes the runtime RPC check.
        script = (
            "$ErrorActionPreference='Stop'; "
            "$v=[System.Diagnostics.FileVersionInfo]::GetVersionInfo($env:SUGARCHAIN_CI_GUI_BINARY); "
            "@{ProductName=$v.ProductName; FileVersion=$v.FileVersion} | ConvertTo-Json -Compress"
        )
        command = ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script]
        env = env | {"SUGARCHAIN_CI_GUI_BINARY": str(binary)}
    else:
        command = [str(binary)]
        # The daemon reads configuration before handling -version. CI guards the
        # default data directory with a file, so keep this probe private too.
        if program == "sugarchaind":
            command.append(f"-datadir={datadir}")
        command.append("--version" if program == "sugarchain" else "-version")
    result = subprocess.run(command, capture_output=True, text=True, timeout=30, env=env)
    if result.returncode != 0:
        raise RuntimeError(f"{program} version probe exited {result.returncode}:\n{result.stdout}{result.stderr}")
    if windows_gui:
        version = json.loads(result.stdout)
        assert version.get("ProductName") == "Sugarchain En", version
        assert isinstance(version.get("FileVersion"), str) and version["FileVersion"].strip(), version
    else:
        assert "Sugarchain En" in result.stdout, (program, result.stdout, result.stderr)


def shutdown_detail(log_path):
    try:
        with log_path.open("rb") as log:
            log.seek(0, os.SEEK_END)
            log.seek(max(0, log.tell() - 64 * 1024))
            tail = log.read()
    except OSError:
        return "application log unavailable"

    _, started, progress = tail.rpartition(b"Shutdown in progress")
    if b"Shutdown done" in progress:
        # The GUI executor and Qt application outlive core shutdown.
        qt_phases = {
            b"[qt] GUI: Shutdown finished": "GUI executor returned from core shutdown",
            b"[qt] GUI: ~InitExecutor : Stopping thread": "GUI joining executor thread",
            b"[qt] GUI: ~InitExecutor : Stopped thread": "GUI executor thread joined",
            b"[qt] GUI: GUI executor released": "GUI executor released",
            b"[qt] GUI: GUI window and platform style released": "GUI window and platform style released",
            b"[qt] GUI: Qt application destroyed": "Qt application destroyed",
            b"[qt] GUI: GuiMain returned": "GuiMain returned",
        }
        last_qt_phase = None
        for line in reversed(progress.splitlines()):
            record = line.partition(b" ")[2] if line[:1].isdigit() else line
            if record == b"Shutdown done":
                if last_qt_phase:
                    return f"application logged shutdown completion, {last_qt_phase}"
                break
            if last_qt_phase is None:
                last_qt_phase = qt_phases.get(record)
        return "application logged shutdown completion"
    if not started:
        return "no shutdown marker in recent application log"

    # Only report fixed lifecycle messages from this launch, without wallet or RPC data.
    phases = (
        (b"Stopping HTTP RPC server", "stopping HTTP RPC"),
        (b"Stopping RPC", "stopping RPC"),
        (b"RPC stopped.", "RPC stopped"),
        (b"Stopping HTTP server", "stopping HTTP"),
        (b"Stopped HTTP server", "HTTP stopped"),
        (b"Releasing wallet", "releasing wallet"),
        (b"scheduler thread exit", "scheduler stopped"),
        (b"Dumped mempool", "mempool saved"),
        (b"Writing final batch", "writing chainstate"),
        (b"changed transaction outputs", "chainstate written"),
    )
    offset, name = max((progress.rfind(marker), label) for marker, label in phases)
    return f"last shutdown phase: {name}" if offset >= 0 else "application logged shutdown start only"


def fault_location(module, offset=""):
    name = PureWindowsPath(module).name
    digits = offset.lower().removeprefix("0x")
    if name and digits and len(digits) <= 16 and all(c in "0123456789abcdef" for c in digits):
        return f"{name}+0x{int(digits, 16):x}"
    return name


def queued_windows_fault(executable, process, started_ns):
    # The hosted image queues WER reports. Only read the summary of a report
    # matching this binary, this launch interval and this exit status.
    for folder in ("ProgramData", "LOCALAPPDATA"):
        if folder not in os.environ:
            continue
        root = Path(os.environ[folder]) / "Microsoft/Windows/WER"
        for store in ("ReportQueue", "ReportArchive"):
            try:
                reports = list((root / store).glob(f"AppCrash_{executable.stem}*/Report.wer"))
            except OSError:
                continue
            for report in reports:
                try:
                    with report.open("rb") as stream:
                        raw = stream.read(256 * 1024)
                    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
                        encoding = "utf-16"
                    else:
                        encoding = "utf-16-le" if raw[1:2] == b"\0" else "utf-8-sig"
                    values = dict(line.split("=", 1) for line in raw.decode(encoding).splitlines() if "=" in line)
                    if values.get("EventType") != "APPCRASH" or PureWindowsPath(values["AppPath"]) != executable:
                        continue
                    # EventTime is a FILETIME in 100 ns ticks since 1601.
                    event_ns = (int(values["EventTime"]) - 116444736000000000) * 100
                    if not started_ns <= event_ns <= time.time_ns():
                        continue
                    if "ProcessId" in values and int(values["ProcessId"], 0) != process.pid:
                        continue
                    signature = {value: values.get(k.removesuffix(".Name") + ".Value", "")
                                 for k, value in values.items() if k.startswith("Sig[") and k.endswith(".Name")}
                    if int(signature["Exception Code"], 16) == (process.returncode & 0xffffffff):
                        location = fault_location(signature["Fault Module Name"], signature.get("Exception Offset", ""))
                        if location:
                            return location
                except (OSError, UnicodeError, ValueError, KeyError):
                    continue
    return ""


def windows_fault_module(process, started_ns):
    executable = PureWindowsPath(process.args[0])
    query = ("*[System[Provider[@Name='Application Error'] and EventID=1000 and "
             "TimeCreated[timediff(@SystemTime) <= 120000]]]")
    # Windows can publish the event after the child process has already exited.
    for delay in (0, 1, 2, 4):
        if delay:
            time.sleep(delay)
        try:
            result = subprocess.run(
                ["wevtutil", "qe", "Application", f"/q:{query}", "/rd:true", "/c:20", "/f:xml", "/e:Events"],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=True, timeout=5,
            )
            events = ET.fromstring(result.stdout).findall(".//{*}Event") if result.stdout.strip() else []
        except (OSError, subprocess.SubprocessError, ET.ParseError, ValueError):
            events = []
        for event in events:
            data = event.findall("./{*}EventData/{*}Data")
            fields = {field.get("Name"): field.text or "" for field in data}
            if len(data) >= 9 and all(field.get("Name") is None for field in data):
                # Classic Application Error records use the provider's positional fields.
                fields = {"AppName": data[0].text or "", "ModuleName": data[3].text or "",
                          "FaultingOffset": data[7].text or "", "ProcessId": data[8].text or ""}
                if len(data) > 10:
                    fields["AppPath"] = data[10].text or ""
            try:
                pid = int(fields.get("ProcessId", ""), 0)
            except ValueError:
                continue
            if pid != process.pid or fields.get("AppName", "").casefold() != executable.name.casefold():
                continue
            if fields.get("AppPath") and PureWindowsPath(fields["AppPath"]) != executable:
                continue
            module = fault_location(fields.get("ModuleName", ""), fields.get("FaultingOffset", ""))
            if module:
                return module
        queued = queued_windows_fault(executable, process, started_ns)
        if queued:
            return queued
    return ""


class Node:
    def __init__(self, binary, datadir, chain, gui=False):
        self.datadir = datadir
        self.chain = chain
        self.wallet = None
        datadir.mkdir(parents=True)
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            self.port = listener.getsockname()[1]
        command = [
            str(binary), f"-datadir={datadir}", f"-rpcport={self.port}",
            "-server=1", "-listen=0", "-connect=0", "-dnsseed=0", "-discover=0",
            "-debug=http", "-debug=rpc", "-debug=coindb",
            "-networkactive=0", "-maxconnections=0", "-keypool=10",
            "-fallbackfee=0.0002", "-printtoconsole=0",
        ]
        if chain == "regtest":
            command.append("-regtest")
        if gui:
            command += ["-splash=0", "-min", "-debug=qt"]
        self.cookie = datadir / ("regtest/.cookie" if chain == "regtest" else ".cookie")
        self.log = (datadir / "process.log").open("wb")
        self.started_ns = time.time_ns()
        self.process = subprocess.Popen(command, stdout=self.log, stderr=subprocess.STDOUT, env=runtime_environment(datadir))

    def __enter__(self):
        return self

    def __exit__(self, exc_type, _exc_value, _traceback):
        try:
            self.close()
        except Exception as cleanup_error:
            if exc_type is None:
                raise
            print(f"Additional node cleanup error: {cleanup_error}", file=sys.stderr)

    def rpc(self, method, *params):
        auth = base64.b64encode(self.cookie.read_bytes().strip()).decode()
        wallet_path = f"/wallet/{urllib.parse.quote(self.wallet, safe='')}" if self.wallet else "/"
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{wallet_path}",
            json.dumps({"jsonrpc": "2.0", "id": "smoke", "method": method, "params": params}).encode(),
            {"Authorization": f"Basic {auth}", "Content-Type": "application/json"},
        )
        try:
            response = urllib.request.urlopen(request, timeout=30)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            result = json.load(response)
        if result.get("error"):
            raise RuntimeError(result["error"])
        return result["result"]

    def wait(self):
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError(f"Node exited before RPC startup; see {self.datadir / 'process.log'}")
            try:
                return self.rpc("getblockchaininfo")
            except (OSError, RuntimeError):
                time.sleep(0.1)
        raise RuntimeError(f"Node startup timed out; see {self.datadir / 'process.log'}")

    def close(self):
        try:
            if self.process.poll() is None:
                self.wallet = None
                with contextlib.suppress(OSError, RuntimeError):
                    self.rpc("stop")
                try:
                    self.process.wait(timeout=45)
                except subprocess.TimeoutExpired:
                    self.process.terminate()
                    self.process.wait(timeout=15)
                    raise
            if self.process.returncode != 0:
                detail = shutdown_detail(self.cookie.parent / "debug.log")
                if os.name == "nt":
                    module = windows_fault_module(self.process, self.started_ns) or "unavailable"
                    detail += f", Windows faulting module {module}"
                code = self.process.returncode
                raise RuntimeError(
                    f"{Path(self.process.args[0]).name} ({self.chain}) exited with {code} ({code:#x}), {detail}"
                )
        finally:
            self.log.close()


def check_node(binary, cli, datadir, chain, gui=False):
    with Node(binary, datadir, chain, gui) as node:
        info = node.wait()
        assert info["chain"] == chain and info["blocks"] == 0, info
        expected_genesis = {
            "main": "7d5eaec2dbb75f99feadfa524c78b7cabc1d8c8204f79d4f3a83381b811b0adc",
            "regtest": "0f9188f13cb7b2c71f2a335e3a4fc328bf5beb436012afca590b1a11466e2206",
        }
        assert node.rpc("getblockhash", 0) == expected_genesis[chain]
        network = node.rpc("getnetworkinfo")
        assert network["networkactive"] is False and network["connections"] == 0
        command = [str(cli), f"-datadir={datadir}", f"-rpcport={node.port}"]
        if chain == "regtest":
            command.append("-regtest")
        command.append("getblockcount")
        assert subprocess.check_output(command, text=True).strip() == "0"

        node.rpc("createwallet", "smoke", False, False, "", False, True, False)
        node.wallet = "smoke"
        address = node.rpc("getnewaddress", "", "bech32")
        assert address.startswith("sugar1q" if chain == "main" else "bcrt1q"), address
        assert node.rpc("getaddressinfo", address)["ismine"]
        legacy = node.rpc("getnewaddress", "", "legacy")
        if chain == "main":
            assert legacy.startswith("S"), legacy
        message = "Sugarchain En native Windows wallet smoke"
        signature = node.rpc("signmessage", legacy, message)
        assert node.rpc("verifymessage", legacy, signature, message)
        if chain == "main":
            try:
                node.rpc("getnewaddress", "", "bech32m")
            except RuntimeError as error:
                assert "not supported on this network" in str(error), error
            else:
                raise AssertionError("Inactive mainnet Taproot unexpectedly generated an address")
        else:
            blocks = node.rpc("generatetoaddress", 101, address)
            assert len(blocks) == 101
            txid = node.rpc("sendtoaddress", node.rpc("getnewaddress"), 1)
            node.rpc("generatetoaddress", 1, address)
            assert node.rpc("gettransaction", txid)["confirmations"] == 1
            backup = datadir / "fresh-wallet-backup.sqlite"
            node.rpc("backupwallet", str(backup))
            assert backup.is_file() and backup.stat().st_size > 0
            node.wallet = None
            node.rpc("restorewallet", "restored", str(backup), False)
            node.wallet = "restored"
            assert node.rpc("getaddressinfo", address)["ismine"]
        return {"chain": chain, "gui": gui, "height": node.rpc("getblockcount"), "wallet": "passed"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bindir", required=True, type=Path)
    parser.add_argument("--workdir", "--work-dir", dest="workdir", type=Path)
    args = parser.parse_args()
    bindir = args.bindir.resolve()
    workdir = args.workdir.resolve() if args.workdir else Path(tempfile.mkdtemp(prefix="sugarchain-en-smoke-"))
    workdir.mkdir(parents=True, exist_ok=True)
    suffix = ".exe" if os.name == "nt" else ""
    programs = ["sugarchain", "sugarchaind", "sugarchain-cli", "sugarchain-qt", "sugarchain-wallet", "sugarchain-tx", "sugarchain-util"]
    binaries = {}
    version_datadir = workdir / "version-data"
    version_datadir.mkdir()
    version_env = runtime_environment(workdir / "version-env")
    for program in programs:
        candidates = [bindir / f"{program}{suffix}", bindir / "daemon" / f"{program}{suffix}"]
        binary = next((path for path in candidates if path.is_file()), candidates[0])
        assert binary.is_file(), binary
        binaries[program] = binary
        check_version(binary, program, version_datadir, version_env)
    daemon = binaries["sugarchaind"]
    cli = binaries["sugarchain-cli"]
    results = [
        check_node(daemon, cli, workdir / "main", "main"),
        check_node(daemon, cli, workdir / "regtest", "regtest"),
        check_node(binaries["sugarchain-qt"], cli, workdir / "gui-main", "main", gui=True),
    ]
    for chain in ("test", "testnet4", "signet"):
        datadir = workdir / f"unsupported-{chain}"
        datadir.mkdir()
        result = subprocess.run([str(daemon), f"-datadir={datadir}", f"-chain={chain}"], capture_output=True, text=True, timeout=30)
        assert result.returncode != 0 and "not supported" in result.stderr, result
        assert not list(datadir.iterdir()), f"Rejected {chain} created persistent data"
    report = {"binaries": len(programs), "runtime": results, "unsupported_chains_rejected": 3, "status": "passed"}
    (workdir / "results.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
