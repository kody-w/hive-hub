from __future__ import annotations

import ctypes
import errno
import os
from ctypes import wintypes
from dataclasses import dataclass
from typing import Any

FILE_ATTRIBUTE_REPARSE_POINT = 0x00000400
FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
FILE_SHARE_DELETE = 0x00000004
OPEN_EXISTING = 3

_INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
_WINDOWS_FILE_API: Any | None = None


class _ByHandleFileInformation(ctypes.Structure):
    _fields_ = [
        ("dwFileAttributes", wintypes.DWORD),
        ("ftCreationTime", wintypes.FILETIME),
        ("ftLastAccessTime", wintypes.FILETIME),
        ("ftLastWriteTime", wintypes.FILETIME),
        ("dwVolumeSerialNumber", wintypes.DWORD),
        ("nFileSizeHigh", wintypes.DWORD),
        ("nFileSizeLow", wintypes.DWORD),
        ("nNumberOfLinks", wintypes.DWORD),
        ("nFileIndexHigh", wintypes.DWORD),
        ("nFileIndexLow", wintypes.DWORD),
    ]


@dataclass(frozen=True, slots=True)
class WindowsFileMetadata:
    attributes: int
    number_of_links: int
    volume_serial_number: int
    file_index: int

    @property
    def is_reparse_point(self) -> bool:
        return bool(self.attributes & FILE_ATTRIBUTE_REPARSE_POINT)


def _windows_error(operation: str, path: str | None = None) -> OSError:
    get_last_error: Any = getattr(ctypes, "get_last_error", None)
    code = int(get_last_error()) if callable(get_last_error) else 0
    message = f"{operation} failed"
    if path is None:
        return OSError(code or errno.EIO, message)
    return OSError(code or errno.EIO, message, path)


def _windows_file_api() -> Any:
    global _WINDOWS_FILE_API
    if _WINDOWS_FILE_API is not None:
        return _WINDOWS_FILE_API
    loader: Any = getattr(ctypes, "WinDLL", None)
    if loader is None:
        raise OSError(errno.ENOSYS, "Windows file metadata is unavailable")
    api = loader("kernel32", use_last_error=True)
    api.CreateFileW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    api.CreateFileW.restype = wintypes.HANDLE
    api.GetFileInformationByHandle.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(_ByHandleFileInformation),
    ]
    api.GetFileInformationByHandle.restype = wintypes.BOOL
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    api.CloseHandle.restype = wintypes.BOOL
    _WINDOWS_FILE_API = api
    return api


def _metadata_from_handle(handle: int, api: Any) -> WindowsFileMetadata:
    information = _ByHandleFileInformation()
    if not api.GetFileInformationByHandle(handle, ctypes.byref(information)):
        raise _windows_error("GetFileInformationByHandle")
    return WindowsFileMetadata(
        attributes=int(information.dwFileAttributes),
        number_of_links=int(information.nNumberOfLinks),
        volume_serial_number=int(information.dwVolumeSerialNumber),
        file_index=(int(information.nFileIndexHigh) << 32)
        | int(information.nFileIndexLow),
    )


def windows_path_metadata(path: str | os.PathLike[str]) -> WindowsFileMetadata:
    absolute = os.path.abspath(os.fspath(path))
    api = _windows_file_api()
    handle = api.CreateFileW(
        absolute,
        0,
        FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
        None,
        OPEN_EXISTING,
        FILE_FLAG_OPEN_REPARSE_POINT | FILE_FLAG_BACKUP_SEMANTICS,
        None,
    )
    if handle is None or handle == _INVALID_HANDLE_VALUE:
        raise _windows_error("CreateFileW", absolute)
    try:
        metadata = _metadata_from_handle(handle, api)
    except Exception:
        api.CloseHandle(handle)
        raise
    if not api.CloseHandle(handle):
        raise _windows_error("CloseHandle", absolute)
    return metadata


def windows_descriptor_metadata(file_descriptor: int) -> WindowsFileMetadata:
    try:
        import msvcrt
    except ImportError as exc:
        raise OSError(errno.ENOSYS, "Windows file metadata is unavailable") from exc
    msvcrt_api: Any = msvcrt
    handle = int(msvcrt_api.get_osfhandle(file_descriptor))
    if handle == -1:
        raise OSError(errno.EBADF, "invalid Windows file descriptor")
    return _metadata_from_handle(handle, _windows_file_api())
