"""Read short symbolized stacks from local Windows QA minidumps using Microsoft CDB."""

import argparse
import mmap
import os
from pathlib import Path, PureWindowsPath
import re
import shutil
import struct
import subprocess
import sys
import time


HEALTHY_SOURCE = r"""
#include <stdio.h>
#include <windows.h>

__declspec(noinline) int healthy_wait(void)
{
    printf("%lu\n", (unsigned long)GetCurrentThreadId());
    fflush(stdout);
    return getchar() == '\n' ? 0 : 1;
}

int main(void)
{
    return healthy_wait();
}
"""
ADDRESS = r"(?:0x)?([0-9a-fA-F`]{8,17})"
NAME, DETAIL, END = "QA_CLEAN_FRAMES", "QA_PHYSICAL_FRAMES", "QA_END_STACK"
CALL_SITE = r"([\w.-]{1,100}(?:![\w?$@:.~-]{1,150}(?:\+0x[0-9a-fA-F]{1,16})?|\+0x[0-9a-fA-F]{1,16}))"
STATIC_REASON = {
    "could not open dump": "dump could not be opened",
    "could not find the dump": "dump unavailable",
    "unable to get exception": "exception context unavailable",
    "couldn't get exception": "exception context unavailable",
    "could not get thread context": "thread context unavailable",
    "stack unwind information not available": "limited unwind information",
    "symbols could not be loaded": "some symbols unavailable",
}


def dump_metadata(path):
    """Read only the standard module directory, PID and stored exception metadata."""
    with path.open("rb") as src, mmap.mmap(src.fileno(), 0, access=mmap.ACCESS_READ) as data:
        if data[:4] != b"MDMP":
            raise ValueError("unexpected dump format")
        count, start = struct.unpack_from("<II", data, 8)
        if start + count * 12 > len(data):
            raise ValueError("incomplete stream directory")
        directory = {}
        for kind, size, rva in struct.iter_unpack("<III", data[start:start + count * 12]):
            if rva + size > len(data):
                raise ValueError("incomplete native stream")
            directory[kind] = (rva, size)
        start, size = directory[4]
        count, = struct.unpack_from("<I", data, start)
        if 4 + count * 108 > size:
            raise ValueError("incomplete module directory")
        modules = []
        for index in range(count):
            base, length, stamp, name = struct.unpack_from("<QI4xII", data, start + 4 + index * 108)
            size, = struct.unpack_from("<I", data, name)
            if name + 4 + size > len(data):
                raise ValueError("incomplete module name")
            base_name = PureWindowsPath(data[name + 4:name + 4 + size].decode("utf-16le")).name
            if re.fullmatch(r"[\w. -]{1,128}", base_name, re.ASCII):
                modules.append((base_name, base, length, stamp))
        pid, exception = None, None
        if 15 in directory and directory[15][1] >= 12:
            flags, value = struct.unpack_from("<II", data, directory[15][0] + 4)
            if flags & 1:
                pid = value
        if 6 in directory:
            if directory[6][1] < 168:
                raise ValueError("incomplete exception context")
            pos = directory[6][0]
            thread, code, pc = struct.unpack_from("<I4xI12xQ", data, pos)
            ctx_size, ctx_rva = struct.unpack_from("<II", data, pos + 160)
            if not ctx_size or ctx_rva + ctx_size > len(data):
                raise ValueError("exception context unavailable")
            exception = (thread, code, pc)
        return modules, pid, exception


def module_rva(modules, pc):
    for name, base, size, _ in modules:
        if pc is not None and base <= pc < base + size:
            return f"{name}+0x{pc-base:x}"
    return None


def address(value):
    return int(value.replace("`", ""), 16)


def frames_from_output(output, modules, initial_pc):
    """Map printed CDB unwind results to known images. Never display debugger output."""
    section, clean_count = None, 0
    unnumbered, symbols, pcs = [], {}, {}
    markers = set()
    tid = None
    if initial_pc is not None:
        pcs[0] = initial_pc
    physical = {}
    for row in output.splitlines():
        line = row.strip()
        if line in (NAME, DETAIL, END):
            section = line
            markers.add(line)
            continue
        ip = re.fullmatch("QA_CURRENT_IP " + ADDRESS, line)
        if ip:
            pcs[0] = address(ip[1])
        thread = re.fullmatch(r"QA_CURRENT_TID ([0-9a-fA-F]{1,8})", line)
        if thread:
            tid = int(thread[1], 16)
        if section == NAME:
            m = re.match(r"^(?:#?([0-9a-fA-F]{1,3})\s+)?" + CALL_SITE, line, re.ASCII)
            if m:
                clean_count += 1
                if m[1] is None:
                    unnumbered.append(m[2])
                else:
                    symbols[int(m[1], 16)] = m[2]
        elif section == DETAIL:
            m = re.match(r"^([0-9a-fA-F]{1,3})\s+" + ADDRESS + r"\s+" + ADDRESS + r"\b", line)
            if m:
                ordinal = int(m[1], 16)
                physical[ordinal] = address(m[3])
                detail_label = re.match(CALL_SITE, line[m.end():].lstrip(), re.ASCII)
                if detail_label:
                    symbols.setdefault(ordinal, detail_label[1])
    if not physical or len(unnumbered) == len(physical):
        for ordinal, label in zip(sorted(physical) if physical else range(len(unnumbered)), unnumbered):
            symbols.setdefault(ordinal, label)
    # The RetAddr of a physical frame is the following caller's instruction
    # address. Ignore an inline gap instead of attributing its neighbour's PC.
    for ordinal in physical:
        if ordinal - 1 in physical:
            pcs[ordinal] = physical[ordinal - 1]
    frames = []
    for i in sorted(set(physical) | set(symbols)):
        origin = module_rva(modules, pcs.get(i))
        label = symbols.get(i)
        if label or origin:
            frames.append((i, origin, label))
    return frames[:12], clean_count, len(physical), END in markers, tid


def invoke(cdb, cwd, args, timeout=35):
    try:
        run = subprocess.run([str(cdb), "-sins", *args], cwd=cwd, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, text=True,
                             errors="replace", timeout=timeout)
        return run.returncode, run.stdout
    except subprocess.TimeoutExpired:
        return "timeout", ""


def read_stack(cdb, dump, image, modules, selector, expected_tid, initial_pc):
    image_paths = str(image.parent) + ";" + str(Path(os.environ["SystemRoot"]) / "System32")
    commands = (f'{selector}; .printf "QA_CURRENT_TID %x\\n", @$tid; .printf "QA_CURRENT_IP %p\\n", @rip; .echo {NAME}; kcn 0xc; '
                f'.echo {DETAIL}; kn 0xc; .echo {END}; q')
    status, output = invoke(cdb, image.parent, ["-i", image_paths, "-y", str(image.parent), "-z", str(dump), "-c", commands])
    frames, clean, physical, complete, tid = frames_from_output(output, modules, initial_pc)
    notes = ", ".join(v for k, v in STATIC_REASON.items() if k in output.lower()) or "none"
    print(f"CDB offline status={status} end-marker={complete} selected-tid={tid} expected-tid={expected_tid} "
          f"clean-sites={clean} physical-rows={physical} notes={notes}")
    if status != 0 or not complete or tid != expected_tid or "context unavailable" in notes:
        raise RuntimeError("CDB did not confirm the requested stack context")
    for ordinal, origin, label in frames:
        print(f"frame {ordinal:02d} " + " ".join(v for v in (origin, label) if v))
    return frames


def preflight(cdb, private):
    directory = private / "healthy"
    directory.mkdir()
    source = directory / "healthy_wallet_probe.c"
    source.write_text(HEALTHY_SOURCE, encoding="ascii")
    executable = directory / "healthy_wallet_probe.exe"
    compiler = shutil.which("cl.exe")
    if not compiler:
        raise RuntimeError("MSVC compiler unavailable for the healthy debugger control")
    compile_result = subprocess.run([compiler, "/nologo", "/Od", "/Ob0", "/Zi", source.name,
                                     "/link", "/DEBUG:FULL", "/INCREMENTAL:NO", "/PDB:healthy_wallet_probe.pdb"],
                                    cwd=directory, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=40)
    if compile_result.returncode:
        raise RuntimeError(f"healthy control compilation returned {compile_result.returncode}")
    dump = directory / "healthy.dmp"
    ready = directory / "ready.txt"
    with ready.open("wb") as output:
        child = subprocess.Popen([str(executable)], cwd=directory, stdin=subprocess.PIPE, stdout=output)
        try:
            deadline = time.monotonic() + 10
            while not (value := ready.read_text(encoding="ascii")).endswith("\n"):
                if child.poll() is not None or time.monotonic() >= deadline:
                    raise RuntimeError("the owned healthy process did not announce its thread")
                time.sleep(0.05)
            if not re.fullmatch(r"[0-9]+", value.strip()):
                raise RuntimeError("the owned healthy process reported an unexpected thread")
            tid = int(value.strip())
            # -pv suspends this one owned process during capture. qd detaches.
            capture, _ = invoke(cdb, directory, ["-pv", "-p", str(child.pid), "-c", ".dump /m healthy.dmp; qd"])
        finally:
            child.communicate(input=b"\n", timeout=20)
    if child.returncode != 0 or capture != 0 or not dump.is_file():
        raise RuntimeError(f"healthy control exit={child.returncode}, capture={capture}, dump-present={dump.is_file()}")
    modules, saved_pid, _ = dump_metadata(dump)
    if saved_pid is not None and saved_pid != child.pid:
        raise ValueError("healthy control PID differs from its snapshot")
    frames = read_stack(cdb, dump, executable, modules, f"~~[{tid:x}]s", tid, None)
    if not any(origin and label and label.lower().startswith("healthy_wallet_probe!healthy_wait")
               for _, origin, label in frames):
        raise RuntimeError("CDB did not identify the healthy_wait PDB call site and its module-relative offset")
    print("Healthy owned process exited 0. CDB resolved its positive-control call site offline.")


def report(cdb, dump, image, expected_pid):
    temp = Path(os.environ["RUNNER_TEMP"]).resolve()
    if not dump.is_relative_to(temp) or image.name.lower() != "sugarchain-qt.exe":
        raise ValueError("unexpected private report or wallet image")
    filename = re.fullmatch(r"sugarchain-qt\.exe\.(\d+)\.dmp", dump.name, re.I)
    if not filename:
        raise ValueError("unexpected wallet dump filename")
    modules, saved_pid, exception = dump_metadata(dump)
    pid = int(filename[1])
    if (expected_pid is not None and pid != expected_pid) or (saved_pid is not None and pid != saved_pid):
        raise ValueError("wallet PID differs from its native report")
    if not exception:
        raise ValueError("stored exception metadata unavailable")
    with image.open("rb") as f:
        f.seek(0x3c)
        pe_offset, = struct.unpack("<I", f.read(4))
        f.seek(pe_offset + 8)
        stamp, = struct.unpack("<I", f.read(4))
        f.seek(pe_offset + 24 + 56)
        size, = struct.unpack("<I", f.read(4))
    if not any(name.casefold() == image.name.casefold() and extent == size and stamp == recorded_stamp
               for name, _, extent, recorded_stamp in modules):
        raise ValueError("the supplied wallet image differs from the recorded module")
    thread, code, pc = exception
    print(f"Windows exception {code:#010x} PID={pid} TID={thread} location={module_rva(modules, pc) or 'outside recorded modules'}")
    if not read_stack(cdb, dump, image, modules, f"~~[{thread:x}]s; .ecxr", thread, pc):
        raise RuntimeError("CDB returned no attributable native stack frames")


def main():
    parser = argparse.ArgumentParser()
    actions = parser.add_subparsers(dest="action", required=True)
    actions.add_parser("preflight")
    observe = actions.add_parser("report")
    observe.add_argument("--dump", type=Path, required=True)
    observe.add_argument("--image", type=Path, required=True)
    observe.add_argument("--pid", type=int)
    args = parser.parse_args()
    if os.name != "nt" or os.environ.get("RUNNER_ENVIRONMENT") != "github-hosted" or os.environ.get("GITHUB_ACTIONS") != "true":
        raise RuntimeError("requires an ephemeral Windows GitHub Actions runner")
    cdb = Path(os.environ["EN_QT_CDB"]).resolve(strict=True)
    private = Path(os.environ["EN_QT_CDB_PRIVATE"]).resolve(strict=True)
    if private.parent != Path(os.environ["RUNNER_TEMP"]).resolve() or not private.name.startswith("en-qa-cdb-"):
        raise ValueError("unexpected private debugger directory")
    if args.action == "preflight":
        try:
            preflight(cdb, private)
        finally:
            if (private / "healthy").is_dir():
                shutil.rmtree(private / "healthy")
    else:
        report(cdb, args.dump.resolve(strict=True), args.image.resolve(strict=True), args.pid)


if __name__ == "__main__":
    try:
        main()
    except (OSError, KeyError, RuntimeError, ValueError, struct.error, subprocess.SubprocessError) as error:
        # Keep paths, raw debugger output, register images and environment values private.
        detail = str(error) if type(error) in (RuntimeError, ValueError) else type(error).__name__
        print(f"CDB QA observation failed: {detail}", file=sys.stderr)
        sys.exit(1)
