from __future__ import annotations

import errno
import os
import secrets
import stat
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .canonical import content_address
from .errors import ConflictError, LimitError, StorageError, UnsafePathError
from .limits import MAX_FILES_PER_COLLECTION, MAX_JSON_BYTES, MAX_PATH_DEPTH


@dataclass(frozen=True, slots=True)
class WritePlan:
    relative_path: str
    content_address: str
    data: bytes


class SafeFilesystem:
    """Bounded no-follow storage rooted at one absolute directory."""

    def __init__(self, root: str | os.PathLike[str]) -> None:
        expanded = os.path.abspath(os.path.expanduser(os.fspath(root)))
        if not os.path.isabs(expanded):
            raise UnsafePathError("storage root must be absolute")
        self.root = Path(expanded)
        fd = self._open_absolute_dir(create=True)
        os.close(fd)

    @staticmethod
    def _dir_flags() -> int:
        flags = os.O_RDONLY
        flags |= getattr(os, "O_DIRECTORY", 0)
        flags |= getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        return flags

    def _open_absolute_dir(self, *, create: bool) -> int:
        components = [part for part in self.root.parts if part not in ("", os.sep)]
        fd = os.open(os.sep, self._dir_flags())
        try:
            for component in components:
                try:
                    child_fd = os.open(component, self._dir_flags(), dir_fd=fd)
                except FileNotFoundError:
                    if not create:
                        raise
                    with suppress(FileExistsError):
                        os.mkdir(component, mode=0o700, dir_fd=fd)
                    child_fd = os.open(component, self._dir_flags(), dir_fd=fd)
                except OSError as exc:
                    if exc.errno in (errno.ELOOP, errno.ENOTDIR):
                        raise UnsafePathError("storage root contains a symlink") from exc
                    raise
                os.close(fd)
                fd = child_fd
            return fd
        except Exception:
            os.close(fd)
            raise

    @staticmethod
    def _parts(relative_path: str) -> tuple[str, ...]:
        path = PurePosixPath(relative_path)
        parts = path.parts
        if path.is_absolute() or not parts or len(parts) > MAX_PATH_DEPTH:
            raise UnsafePathError("unsafe relative storage path")
        if any(
            part in ("", ".", "..") or "/" in part or "\x00" in part or part.startswith(".tmp-")
            for part in parts
        ):
            raise UnsafePathError("unsafe relative storage path")
        return parts

    @contextmanager
    def _open_dir(self, parts: tuple[str, ...], *, create: bool) -> Iterator[int]:
        fd = self._open_absolute_dir(create=True)
        try:
            for component in parts:
                try:
                    child_fd = os.open(component, self._dir_flags(), dir_fd=fd)
                except FileNotFoundError:
                    if not create:
                        raise
                    with suppress(FileExistsError):
                        os.mkdir(component, mode=0o700, dir_fd=fd)
                    child_fd = os.open(component, self._dir_flags(), dir_fd=fd)
                except OSError as exc:
                    if exc.errno in (errno.ELOOP, errno.ENOTDIR):
                        raise UnsafePathError("storage path contains a symlink") from exc
                    raise
                os.close(fd)
                fd = child_fd
            yield fd
        finally:
            os.close(fd)

    def plan_write(self, relative_path: str, data: bytes) -> WritePlan:
        self._parts(relative_path)
        if len(data) > MAX_JSON_BYTES:
            raise LimitError("file exceeds the configured byte limit")
        return WritePlan(relative_path, content_address(data, raw=True), data)

    def apply_write(self, plan: WritePlan) -> bool:
        if content_address(plan.data, raw=True) != plan.content_address:
            raise ConflictError("write plan content no longer matches its address")
        parts = self._parts(plan.relative_path)
        parent_parts, filename = parts[:-1], parts[-1]
        with self._open_dir(parent_parts, create=True) as parent_fd:
            try:
                existing = self._read_from_fd(parent_fd, filename, max_bytes=len(plan.data) + 1)
            except FileNotFoundError:
                existing = None
            if existing is not None:
                if existing == plan.data:
                    return False
                raise ConflictError("target path already contains different bytes")
            self._enforce_file_count(parent_fd)
            temporary = f".tmp-{os.getpid()}-{secrets.token_hex(12)}"
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            flags |= getattr(os, "O_CLOEXEC", 0)
            flags |= getattr(os, "O_NOFOLLOW", 0)
            temp_fd = os.open(temporary, flags, 0o600, dir_fd=parent_fd)
            try:
                try:
                    view = memoryview(plan.data)
                    while view:
                        written = os.write(temp_fd, view)
                        if written <= 0:
                            raise StorageError("filesystem write made no progress")
                        view = view[written:]
                    os.fsync(temp_fd)
                finally:
                    os.close(temp_fd)
                try:
                    os.link(
                        temporary,
                        filename,
                        src_dir_fd=parent_fd,
                        dst_dir_fd=parent_fd,
                        follow_symlinks=False,
                    )
                    os.fsync(parent_fd)
                except FileExistsError as exc:
                    existing = self._read_from_fd(
                        parent_fd,
                        filename,
                        max_bytes=len(plan.data) + 1,
                    )
                    if existing != plan.data:
                        raise ConflictError("target path raced with different bytes") from exc
                    return False
            finally:
                with suppress(FileNotFoundError):
                    os.unlink(temporary, dir_fd=parent_fd)
            return True

    def read_bytes(self, relative_path: str, *, max_bytes: int = MAX_JSON_BYTES) -> bytes:
        parts = self._parts(relative_path)
        with self._open_dir(parts[:-1], create=False) as parent_fd:
            return self._read_from_fd(parent_fd, parts[-1], max_bytes=max_bytes)

    def exists(self, relative_path: str) -> bool:
        try:
            self.read_bytes(relative_path, max_bytes=MAX_JSON_BYTES)
        except FileNotFoundError:
            return False
        return True

    def list_files(self, relative_directory: str, *, suffix: str = ".json") -> list[str]:
        parts = self._parts(relative_directory)
        try:
            with self._open_dir(parts, create=False) as directory_fd:
                result: list[str] = []
                count = 0
                with os.scandir(directory_fd) as entries:
                    for entry in entries:
                        count += 1
                        if count > MAX_FILES_PER_COLLECTION:
                            raise LimitError("collection exceeds the configured file-count limit")
                        if not entry.is_file(follow_symlinks=False):
                            raise UnsafePathError("collection contains a non-regular entry")
                        if entry.name.startswith(".tmp-"):
                            continue
                        if not entry.name.endswith(suffix):
                            raise UnsafePathError("collection contains an unexpected file")
                        result.append(entry.name)
                return sorted(result)
        except FileNotFoundError:
            return []

    def remove_if_address(self, relative_path: str, expected_address: str) -> bool:
        parts = self._parts(relative_path)
        try:
            with self._open_dir(parts[:-1], create=False) as parent_fd:
                current = self._read_from_fd(parent_fd, parts[-1], max_bytes=MAX_JSON_BYTES)
                if content_address(current, raw=True) != expected_address:
                    raise ConflictError("stored bytes do not match the reversible write plan")
                os.unlink(parts[-1], dir_fd=parent_fd)
                os.fsync(parent_fd)
                return True
        except FileNotFoundError:
            return False

    @staticmethod
    def _enforce_file_count(directory_fd: int) -> None:
        count = 0
        with os.scandir(directory_fd) as entries:
            for _entry in entries:
                count += 1
                if count >= MAX_FILES_PER_COLLECTION:
                    raise LimitError("collection reached the configured file-count limit")

    @staticmethod
    def _read_from_fd(directory_fd: int, filename: str, *, max_bytes: int) -> bytes:
        flags = os.O_RDONLY
        flags |= getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        try:
            fd = os.open(filename, flags, dir_fd=directory_fd)
        except OSError as exc:
            if exc.errno == errno.ELOOP:
                raise UnsafePathError("refusing to follow a file symlink") from exc
            raise
        try:
            file_stat = os.fstat(fd)
            if not stat.S_ISREG(file_stat.st_mode):
                raise UnsafePathError("refusing to read a non-regular file")
            if file_stat.st_size > max_bytes:
                raise LimitError("file exceeds the configured byte limit")
            chunks: list[bytes] = []
            remaining = max_bytes + 1
            while remaining > 0:
                chunk = os.read(fd, min(64 * 1024, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            data = b"".join(chunks)
            if len(data) > max_bytes:
                raise LimitError("file exceeds the configured byte limit")
            return data
        finally:
            os.close(fd)


def read_external_file(path: str | os.PathLike[str], *, max_bytes: int = MAX_JSON_BYTES) -> bytes:
    absolute = os.path.abspath(os.path.expanduser(os.fspath(path)))
    components = [part for part in Path(absolute).parts if part not in ("", os.sep)]
    if not components:
        raise UnsafePathError("input must name a regular file")
    directory_flags = os.O_RDONLY
    directory_flags |= getattr(os, "O_DIRECTORY", 0)
    directory_flags |= getattr(os, "O_CLOEXEC", 0)
    directory_flags |= getattr(os, "O_NOFOLLOW", 0)
    directory_fd = os.open(os.sep, directory_flags)
    try:
        for component in components[:-1]:
            try:
                child_fd = os.open(component, directory_flags, dir_fd=directory_fd)
            except OSError as exc:
                if exc.errno in (errno.ELOOP, errno.ENOTDIR):
                    raise UnsafePathError("input path contains a symlink") from exc
                raise
            os.close(directory_fd)
            directory_fd = child_fd
        filename = components[-1]
        flags = os.O_RDONLY
        flags |= getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        try:
            fd = os.open(filename, flags, dir_fd=directory_fd)
        except OSError as exc:
            if exc.errno == errno.ELOOP:
                raise UnsafePathError("refusing to follow an input-file symlink") from exc
            raise
    finally:
        os.close(directory_fd)
    try:
        file_stat = os.fstat(fd)
        if not stat.S_ISREG(file_stat.st_mode):
            raise UnsafePathError("input must be a regular file")
        if file_stat.st_size > max_bytes:
            raise LimitError("input file exceeds the configured byte limit")
        chunks: list[bytes] = []
        remaining = max_bytes + 1
        while remaining > 0:
            chunk = os.read(fd, min(64 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
        if len(data) > max_bytes:
            raise LimitError("input file exceeds the configured byte limit")
        return data
    finally:
        os.close(fd)
