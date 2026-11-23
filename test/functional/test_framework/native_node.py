# Copyright (c) 2026 The Sugarchain En developers
# Distributed under the MIT software license, see the accompanying file COPYING.
"""Cookie-authenticated, isolated nodes for native legacy-wallet tests."""

import base64
import json
import os
from pathlib import Path
import socket
import subprocess
import time
import urllib.error
import urllib.request


class Node:
    """Control only the direct child created in a new private data directory."""

    def __init__(self, binary, directory, *, chain="main", extra=(), legacy=False,
                 coverage_dir=None, timeout=90):
        self.binary = str(binary)
        self.directory = Path(directory)
        self.chain = chain
        self.extra = list(extra)
        self.legacy = legacy
        self.coverage_dir = coverage_dir
        self.timeout = timeout
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.directory.chmod(0o700)
        self.process = None
        self.output = None
        with socket.socket() as candidate:
            candidate.bind(("127.0.0.1", 0))
            self.port = candidate.getsockname()[1]
        self.cookie = self.directory / {"main": "", "regtest": "regtest"}[chain] / ".cookie"

    def rpc(self, method, *params):
        auth = base64.b64encode(self.cookie.read_bytes().strip()).decode()
        data = json.dumps({"jsonrpc": "1.0", "id": "native-wallet-check",
                           "method": method, "params": params}).encode()
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/", data,
            {"Authorization": "Basic " + auth, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                value = json.load(response)
        except urllib.error.HTTPError as error:
            value = json.load(error)
        if value.get("error") is not None:
            # Do not include RPC arguments or error messages containing secrets.
            raise RuntimeError(f"RPC {method} failed: code {value['error']['code']}")
        if self.coverage_dir and not self.legacy:
            filename = Path(self.coverage_dir) / f"coverage.pid{os.getpid()}.native-legacy.txt"
            with filename.open("a", encoding="utf-8") as coverage:
                coverage.write(method + "\n")
        return value["result"]

    def __enter__(self):
        config = self.directory / "sugarchain.conf"
        config.touch(exist_ok=True)
        args = [self.binary, f"-datadir={self.directory}", f"-conf={config}",
                "-server=1", "-listen=0", "-connect=0", "-dnsseed=0",
                "-discover=0", "-maxconnections=0", f"-rpcport={self.port}",
                "-rpcbind=127.0.0.1", "-rpcallowip=127.0.0.1", "-printtoconsole=0"]
        if self.chain == "regtest":
            args.append("-regtest=1")
        if not self.legacy:
            args.append("-networkactive=0")
        args.extend(self.extra)
        environment = os.environ.copy()
        for key, name in (("XDG_CONFIG_HOME", "config"), ("XDG_DATA_HOME", "data"),
                          ("XDG_CACHE_HOME", "cache")):
            directory = self.directory / "xdg" / name
            directory.mkdir(parents=True, exist_ok=True)
            environment[key] = str(directory)
        self.output = (self.directory / "process.log").open("ab")
        self.process = subprocess.Popen(args, stdout=self.output, stderr=subprocess.STDOUT,
                                        env=environment)
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                self.output.close()
                raise RuntimeError(f"Private node exited with status {self.process.returncode}")
            if self.cookie.exists():
                try:
                    self.rpc("getblockchaininfo")
                    if self.coverage_dir and not self.legacy:
                        reference = Path(self.coverage_dir) / "rpc_interface.txt"
                        if not reference.exists():
                            commands = {line.split()[0] for line in self.rpc("help").splitlines()
                                        if line.strip() and not line.startswith("=")}
                            reference.write_text("\n".join(sorted(commands)) + "\n", encoding="utf-8")
                    return self
                except (OSError, RuntimeError, urllib.error.URLError):
                    pass
            time.sleep(0.1)
        self.__exit__(None, None, None)
        raise RuntimeError("Private node startup timed out")

    def __exit__(self, kind, value, _traceback):
        try:
            if self.process and self.process.poll() is None:
                try:
                    self.rpc("stop")
                except (OSError, RuntimeError, urllib.error.URLError):
                    self.process.terminate()
                try:
                    self.process.wait(timeout=self.timeout)
                except subprocess.TimeoutExpired:
                    self.process.terminate()
                    self.process.wait(timeout=self.timeout)
            if self.process and self.process.returncode != 0 and kind is None:
                raise RuntimeError(f"Private node shutdown status {self.process.returncode}")
        finally:
            if self.output:
                self.output.close()
