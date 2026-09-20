from __future__ import annotations

import multiprocessing
import re
import time
from multiprocessing.connection import Connection
from typing import Any

from .canonical import canonical_bytes, loads_json
from .errors import FetchError, HiveHubError, LimitError
from .limits import MAX_JSON_BYTES


def _read_snapshot(url: str, timeout: float) -> bytes:
    from http.client import HTTPException
    from urllib.error import HTTPError, URLError
    from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(
            self, req: Request, fp: Any, code: int, msg: str, headers: Any, newurl: str
        ) -> None:
            fp.close()
            raise FetchError("HTTP redirects are forbidden for public snapshot reads")

    request = Request(url, headers={"Accept": "application/json", "Accept-Encoding": "identity"})
    opener = build_opener(ProxyHandler({}), NoRedirect())
    try:
        with opener.open(request, timeout=timeout) as response:
            if response.status != 200 or response.geturl() != url:
                raise FetchError("public Hub snapshot is unreachable")
            if any(
                encoding.strip().lower() != "identity"
                for encoding in response.headers.get_all("Content-Encoding", [])
            ):
                raise FetchError("encoded public Hub responses are forbidden")
            lengths = response.headers.get_all("Content-Length", [])
            if len(lengths) > 1:
                raise FetchError("public Hub response has ambiguous byte counts")
            length = None
            if lengths:
                if not re.fullmatch(r"[0-9]{1,10}", lengths[0]):
                    raise FetchError("public Hub response has an invalid byte count")
                length = int(lengths[0])
                if length > MAX_JSON_BYTES:
                    raise LimitError("public Hub snapshot exceeds the configured byte limit")
            data = bytearray()
            while True:
                chunk = response.read1(min(64 * 1024, MAX_JSON_BYTES + 1 - len(data)))
                if not chunk:
                    break
                data.extend(chunk)
                if len(data) > MAX_JSON_BYTES:
                    raise LimitError("public Hub snapshot exceeds the configured byte limit")
            if length is not None and len(data) != length:
                raise FetchError("public Hub response byte count mismatch")
            return bytes(data)
    except HTTPError as exc:
        exc.close()
        raise FetchError("public Hub snapshot is unreachable") from exc
    except (URLError, OSError, HTTPException) as exc:
        raise FetchError("public Hub snapshot is unreachable") from exc


def _snapshot_worker(connection: Connection, url: str, timeout: float) -> None:
    with connection:
        try:
            data = _read_snapshot(url, timeout)
        except HiveHubError as exc:
            connection.send_bytes(b"\x01" + canonical_bytes(exc.as_dict()))
        else:
            connection.send_bytes(b"\x00" + data)


def read_public_snapshot(url: str, *, timeout: float) -> bytes:
    # A disposable local worker makes DNS, TLS, and dribbled headers cancellable
    # on every platform, without global signals or lingering fetch threads.
    deadline = time.monotonic() + timeout
    context = multiprocessing.get_context("spawn")
    receive, send = context.Pipe(duplex=False)
    worker = context.Process(
        target=_snapshot_worker, args=(send, url, timeout),
        name="hive-hub-public-fetch", daemon=True,
    )
    try:
        worker.start()
        send.close()
        if not receive.poll(max(0.0, deadline - time.monotonic())):
            raise FetchError("public Hub fetch exceeded its total wall-clock deadline")
        packet = receive.recv_bytes(MAX_JSON_BYTES + 1)
        if time.monotonic() >= deadline:
            raise FetchError("public Hub fetch exceeded its total wall-clock deadline")
        if packet[:1] == b"\x00":
            return packet[1:]
        if packet[:1] == b"\x01":
            document = loads_json(packet[1:])
            error = document.get("error") if isinstance(document, dict) else None
            if isinstance(error, dict):
                message = error.get("message")
                if isinstance(message, str):
                    if error.get("code") == LimitError.code:
                        raise LimitError(message)
                    if error.get("code") == FetchError.code:
                        raise FetchError(message)
        raise FetchError("public Hub fetch worker returned an invalid result")
    except (OSError, EOFError) as exc:
        raise FetchError("public Hub fetch worker failed") from exc
    finally:
        receive.close()
        send.close()
        if worker.pid is not None:
            if worker.is_alive():
                worker.terminate()
            worker.join(timeout=0.1)
            if worker.is_alive():
                worker.kill()
                worker.join()
        worker.close()
