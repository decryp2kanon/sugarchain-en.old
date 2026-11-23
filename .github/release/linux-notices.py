"""Collect upstream dependency license notices from the pinned source archives."""

from pathlib import Path, PurePosixPath
import sys
import tarfile

sources, output = map(Path, sys.argv[1:])
output.mkdir()
found = set()
for archive in sorted(sources.iterdir()):
    if not archive.is_file() or ".tar." not in archive.name:
        continue
    archive_name = archive.name.split(".tar.", 1)[0]
    with tarfile.open(archive, mode="r|*") as contents:
        for member in contents:
            parts = PurePosixPath(member.name).parts
            if not member.isfile() or len(parts) < 2 or ".." in parts or "/" in parts:
                continue
            filename = parts[-1].upper()
            root_notice = len(parts) == 2 and filename.startswith(("COPYING", "LICENSE", "LICENCE", "NOTICE", "COPYRIGHT"))
            license_dir = len(parts) == 3 and parts[1].upper() in {"LICENSES", "LICENCES"}
            freetype_notice = archive_name.startswith("freetype-") and filename in {"FTL.TXT", "GPLV2.TXT"}
            if not (root_notice or license_dir or freetype_notice):
                continue
            target = output.joinpath(archive_name, *parts[1:])
            target.parent.mkdir(parents=True, exist_ok=True)
            with contents.extractfile(member) as notice:
                target.write_bytes(notice.read())
            found.add(archive_name)

for dependency in ("fontconfig-", "freetype-", "qtbase-"):
    if not any(name.startswith(dependency) for name in found):
        raise SystemExit(f"Missing source license notices for {dependency.rstrip('-')}")
