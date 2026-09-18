#!/usr/bin/env python3
from __future__ import annotations

import argparse
import gzip
import io
import os
import tarfile
from pathlib import Path

DEFAULT_EPOCH = 1_789_758_971


def normalize(source: Path, *, epoch: int) -> None:
    pending = source.with_name(f".{source.name}.normalized")
    try:
        with (
            tarfile.open(source, "r:gz") as archive,
            pending.open("wb") as raw_output,
            gzip.GzipFile(
                filename="",
                mode="wb",
                fileobj=raw_output,
                compresslevel=9,
                mtime=epoch,
            ) as compressed,
            tarfile.open(
                fileobj=compressed,
                mode="w",
                format=tarfile.PAX_FORMAT,
            ) as output,
        ):
            for original in sorted(archive.getmembers(), key=lambda item: item.name):
                member = tarfile.TarInfo(original.name)
                member.mode = original.mode
                member.type = original.type
                member.linkname = original.linkname
                member.mtime = epoch
                member.uid = 0
                member.gid = 0
                member.uname = ""
                member.gname = ""
                member.pax_headers = {}
                if original.isfile():
                    extracted = archive.extractfile(original)
                    if extracted is None:
                        raise ValueError(f"cannot read {original.name}")
                    data = extracted.read()
                    member.size = len(data)
                    output.addfile(member, io.BytesIO(data))
                else:
                    member.size = 0
                    output.addfile(member)
        os.replace(pending, source)
    finally:
        pending.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("sdist", type=Path)
    parser.add_argument(
        "--epoch",
        type=int,
        default=int(os.environ.get("SOURCE_DATE_EPOCH", DEFAULT_EPOCH)),
    )
    args = parser.parse_args()
    normalize(args.sdist, epoch=args.epoch)
    print(f"normalized {args.sdist}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
