"""Cross-platform regular-file verification for release tooling."""

from __future__ import annotations

import os
import stat
from pathlib import Path


class FileIntegrityError(RuntimeError):
    """A release input is not one stable, ordinary file."""


def _is_windows() -> bool:
    return os.name == "nt"


def safe_file_link_count(link_count: int, *, windows: bool | None = None) -> bool:
    """Accept NTFS's zero sentinel without permitting actual hardlinks."""
    if windows is None:
        windows = _is_windows()
    return link_count in (0, 1) if windows else link_count == 1


def _matches_regular_file(
    information: os.stat_result,
    expected: os.stat_result,
) -> bool:
    return (
        stat.S_ISREG(information.st_mode)
        and safe_file_link_count(information.st_nlink)
        and information.st_dev == expected.st_dev
        and information.st_ino == expected.st_ino
        and information.st_size == expected.st_size
    )


def read_regular_bytes(path: Path, *, maximum: int | None = None) -> bytes:
    """Read one stable regular file without following links."""
    try:
        expected = path.lstat()
        if (
            not stat.S_ISREG(expected.st_mode)
            or not safe_file_link_count(expected.st_nlink)
            or expected.st_size < 0
            or (maximum is not None and expected.st_size > maximum)
        ):
            raise FileIntegrityError(f"unsafe release file: {path}")
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        try:
            if not _matches_regular_file(os.fstat(descriptor), expected):
                raise FileIntegrityError(f"release file changed before read: {path}")
            chunks: list[bytes] = []
            remaining = expected.st_size
            while remaining:
                chunk = os.read(descriptor, min(65_536, remaining))
                if not chunk:
                    raise FileIntegrityError(f"release file size drifted: {path}")
                chunks.append(chunk)
                remaining -= len(chunk)
            if os.read(descriptor, 1):
                raise FileIntegrityError(f"release file size drifted: {path}")
            if not _matches_regular_file(os.fstat(descriptor), expected):
                raise FileIntegrityError(f"release file changed during read: {path}")
            current = path.lstat()
            if not _matches_regular_file(current, expected):
                raise FileIntegrityError(f"release file changed during read: {path}")
            return b"".join(chunks)
        finally:
            os.close(descriptor)
    except FileIntegrityError:
        raise
    except OSError as exc:
        raise FileIntegrityError(f"cannot verify release file: {path}") from exc


def regular_files(root: Path) -> list[Path]:
    """Return every regular file below a real directory, rejecting unsafe entries."""
    files: list[Path] = []

    def visit(directory: Path) -> None:
        try:
            entries = sorted(os.scandir(directory), key=lambda entry: entry.name)
        except OSError as exc:
            raise FileIntegrityError(f"cannot inspect release directory: {directory}") from exc
        for entry in entries:
            path = Path(entry.path)
            try:
                information = entry.stat(follow_symlinks=False)
            except OSError as exc:
                raise FileIntegrityError(f"cannot inspect release entry: {path}") from exc
            if stat.S_ISLNK(information.st_mode):
                raise FileIntegrityError(f"release tree contains a symlink: {path}")
            if stat.S_ISDIR(information.st_mode):
                visit(path)
            elif stat.S_ISREG(information.st_mode):
                if not safe_file_link_count(information.st_nlink):
                    raise FileIntegrityError(f"release tree contains a hardlink: {path}")
                files.append(path)
            else:
                raise FileIntegrityError(f"release tree contains a special file: {path}")

    try:
        root_information = root.lstat()
    except OSError as exc:
        raise FileIntegrityError(f"cannot inspect release root: {root}") from exc
    if stat.S_ISLNK(root_information.st_mode) or not stat.S_ISDIR(root_information.st_mode):
        raise FileIntegrityError(f"release root must be a real directory: {root}")
    visit(root)
    return files
