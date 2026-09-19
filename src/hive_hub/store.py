from __future__ import annotations

import hmac
import os
import re
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

from .canonical import address_digest, canonical_bytes, content_address, is_address, loads_json
from .chant import derive_chant, normalize_chant, validate_dial_record_id
from .contracts import (
    AdapterPlan,
    AdapterRegistration,
    AdapterRegistrationReceipt,
    DialbookIndex,
    DialIndexEntry,
    DialRecord,
    DialResult,
    LearningBundle,
    LocalSubscription,
    PrivateAccessPolicy,
    ProtocolDeclaration,
    SubscriptionPlan,
    Visibility,
    _closed,
    normalize_record_chant,
    validate_dial_query,
    validate_locator,
)
from .errors import ConflictError, FetchError, LimitError, NotFoundError, ValidationError
from .filesystem import SafeFilesystem, WritePlan
from .limits import (
    HTTP_FETCH_TIMEOUT_SECONDS,
    MAX_ARRAY_ITEMS,
    MAX_JSON_BYTES,
    MAX_LEARNING_BUNDLE_BYTES,
    MAX_RECORD_BYTES,
)
from .published import PublishedRecord


def _document_plan(
    filesystem: SafeFilesystem,
    relative_path: str,
    document: dict[str, object],
    *,
    max_bytes: int = MAX_RECORD_BYTES,
) -> WritePlan:
    return filesystem.plan_write(
        relative_path,
        canonical_bytes(document, max_bytes=max_bytes),
    )


def _core_id_query(query: str) -> str:
    if query.startswith("dial:"):
        return validate_dial_record_id(query).replace("dial:", "urn:hivehub:", 1)
    return query


def _match_records(
    records: list[DialRecord], query: str
) -> tuple[Literal["id", "url", "chant"], list[DialRecord]]:
    query = _core_id_query(query)
    if is_address(query):
        return "id", [record for record in records if record.id == query]
    matches = [record for record in records if query in record.urls]
    if matches or re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", query):
        return "url", matches
    try:
        chant = normalize_chant(query)
    except ValidationError:
        try:
            chant = normalize_record_chant(query)
        except ValidationError:
            return "chant", []
    return "chant", [
        record for record in records
        if chant in record.chants or chant == derive_chant(record.dial_id)
    ]


def _snapshot_url(base_url: str) -> str:
    validate_locator(base_url, field="public Hub base URL")
    try:
        parsed = urlsplit(base_url)
        port = parsed.port
    except ValueError as exc:
        raise ValidationError("public Hub base URL is invalid") from exc
    if (
        parsed.scheme not in {"https", "http"}
        or not parsed.hostname
        or parsed.query
        or parsed.fragment
        or "\\" in base_url
        or "%" in base_url
        or any(part in {".", ".."} for part in parsed.path.split("/"))
        or (port is not None and port == 0)
        or base_url != base_url.strip()
    ):
        raise ValidationError("public Hub base URL must be an unambiguous HTTP(S) base")
    if parsed.scheme == "http" and parsed.hostname not in {"127.0.0.1", "::1", "localhost"}:
        raise ValidationError("public Hub fetches require HTTPS except on loopback")
    return base_url.rstrip("/") + "/api/hive-hub/v1/dial-snapshot.json"


def public_dial_plan(
    home: str | os.PathLike[str], query: str, base_url: str
) -> dict[str, Any]:
    candidate = _core_id_query(validate_dial_query(query))
    if not re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", candidate):
        candidate = normalize_chant(candidate)
    expected_id = candidate if is_address(candidate) else None
    body: dict[str, Any] = {
        "kind": "public-dial-fetch-plan",
        "schema_version": 1,
        "home": os.path.abspath(os.path.expanduser(os.fspath(home))),
        "query": candidate,
        "fetches": [{
            "url": _snapshot_url(base_url),
            "expected_sha256": None,
            "max_bytes": MAX_JSON_BYTES,
        }],
        "expected_record_id": expected_id,
        "redirects": "forbidden",
        "timeout_seconds": HTTP_FETCH_TIMEOUT_SECONDS,
        "registration": {
            "scope": "public",
            "selection": "verified-query-candidates-only",
            "max_records": MAX_ARRAY_ITEMS,
            "contracts": "inert-only",
            "overwrite": False,
            "rollback": "remove-only-created-content-addressed-files",
        },
        "adapter_execution": False,
    }
    return {**body, "plan_id": content_address(body)}


def _fetch_public_snapshot(url: str) -> bytes:
    from http.client import HTTPException
    from urllib.error import HTTPError, URLError
    from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(
            self, req: Request, fp: Any, code: int, msg: str, headers: Any, newurl: str
        ) -> None:
            fp.close()
            raise FetchError("HTTP redirects are forbidden for approved fetches")

    request = Request(url, headers={"Accept": "application/json", "Accept-Encoding": "identity"})
    opener = build_opener(ProxyHandler({}), NoRedirect())
    deadline = time.monotonic() + HTTP_FETCH_TIMEOUT_SECONDS
    try:
        with opener.open(request, timeout=HTTP_FETCH_TIMEOUT_SECONDS) as response:
            if response.status != 200 or response.geturl() != url:
                raise FetchError("public Hub snapshot is unreachable")
            if response.headers.get("Content-Encoding", "identity").lower() != "identity":
                raise FetchError("encoded public Hub responses are forbidden")
            length_header = response.headers.get("Content-Length")
            length = None
            if length_header is not None:
                if not re.fullmatch(r"[0-9]{1,10}", length_header):
                    raise FetchError("public Hub response has an invalid byte count")
                length = int(length_header)
                if length > MAX_JSON_BYTES:
                    raise LimitError("public Hub snapshot exceeds the configured byte limit")
            data = bytearray()
            while True:
                if time.monotonic() >= deadline:
                    raise FetchError("public Hub fetch exceeded its time limit")
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


def dial_from_public_hub(
    home: str | os.PathLike[str],
    query: str,
    base_url: str,
    *,
    apply: str | None = None,
) -> dict[str, Any]:
    plan = public_dial_plan(home, query, base_url)
    if apply is None:
        return plan
    if not is_address(apply) or not hmac.compare_digest(apply, plan["plan_id"]):
        raise ValidationError("public fetch approval does not match the current plan")
    data = _fetch_public_snapshot(plan["fetches"][0]["url"])
    snapshot = _closed(
        loads_json(data), required={"kind", "schema_version", "records"},
        field="published dial snapshot",
    )
    if (
        snapshot["kind"] != "published-dial-snapshot"
        or type(snapshot["schema_version"]) is not int
        or snapshot["schema_version"] != 1
        or not isinstance(snapshot["records"], list)
    ):
        raise ValidationError("public Hub does not provide a version 1 dial snapshot")
    published: dict[str, PublishedRecord] = {}
    for entry in snapshot["records"]:
        entry = _closed(entry, required={"ref", "record"}, field="snapshot record")
        raw = canonical_bytes(entry["record"], max_bytes=MAX_RECORD_BYTES - 1) + b"\n"
        expected = "sha256:" + address_digest(content_address(raw, raw=True))
        if entry["ref"] != expected:
            raise ValidationError("published record content address mismatch")
        validated = PublishedRecord.from_dict(entry["record"])
        if validated.record.id in published:
            raise ValidationError("public snapshot contains duplicate record identities")
        published[validated.record.id] = validated
    query_kind, records = _match_records(
        [item.record for item in published.values()], plan["query"]
    )
    if not records:
        return DialResult.unreachable().to_dict()

    filesystem = SafeFilesystem(plan["home"])
    plans: dict[str, WritePlan] = {}
    for record in records:
        item = published[record.id]
        for relative, document in (
            (f"registry/declarations/{address_digest(item.declaration.fingerprint)}.json",
             item.declaration.to_dict()),
            (f"registry/bundles/{address_digest(item.bundle.address)}.json",
             item.bundle.to_dict()),
            (f"registry/adapters/{address_digest(item.adapter.address)}.json",
             item.adapter.to_dict()),
            (f"books/public/records/{address_digest(record.id)}.json", record.to_dict()),
        ):
            plans[relative] = _document_plan(filesystem, relative, document)
    applied = []
    with filesystem.interprocess_lock("state/transactions/public-dial.lock"):
        try:
            for write in plans.values():
                if filesystem.apply_write(write):
                    applied.append(write)
            _, stored_records = PublicDialbook(
                Path(plan["home"]) / "books/public"
            ).match(plan["query"])
            ordered = sorted(stored_records, key=lambda item: item.id)
            if not ordered:
                raise ConflictError("registered public record disappeared")
        except Exception:
            for write in reversed(applied):
                filesystem.remove_if_address(write.relative_path, write.content_address)
            raise
    return DialResult(
        "resolved" if len(ordered) == 1 else "ambiguous",
        query_kind,
        tuple(DialIndexEntry.from_record(record) for record in ordered),
        ordered[0] if len(ordered) == 1 else None,
    ).to_dict()


class ProtocolRegistry:
    def __init__(self, root: str | os.PathLike[str]) -> None:
        self._fs = SafeFilesystem(root)

    def declaration_plan(self, declaration: ProtocolDeclaration) -> WritePlan:
        return _document_plan(
            self._fs,
            f"declarations/{address_digest(declaration.fingerprint)}.json",
            declaration.to_dict(),
        )

    def bundle_plan(self, bundle: LearningBundle) -> WritePlan:
        return _document_plan(
            self._fs,
            f"bundles/{address_digest(bundle.address)}.json",
            bundle.to_dict(),
            max_bytes=MAX_LEARNING_BUNDLE_BYTES,
        )

    def adapter_plan(self, registration: AdapterRegistration) -> WritePlan:
        return _document_plan(
            self._fs,
            f"adapters/{address_digest(registration.address)}.json",
            registration.to_dict(),
        )

    def receipt_plan(self, receipt: AdapterRegistrationReceipt) -> WritePlan:
        return _document_plan(
            self._fs,
            f"receipts/{address_digest(receipt.receipt_id)}.json",
            receipt.to_dict(),
        )

    def apply(self, plan: WritePlan) -> bool:
        return self._fs.apply_write(plan)

    def revert(self, plan: WritePlan) -> bool:
        return self._fs.remove_if_address(plan.relative_path, plan.content_address)

    def get_declaration(self, fingerprint: str) -> ProtocolDeclaration:
        try:
            data = self._fs.read_bytes(
                f"declarations/{address_digest(fingerprint)}.json",
                max_bytes=MAX_RECORD_BYTES,
            )
        except FileNotFoundError as exc:
            raise NotFoundError("protocol declaration is not registered") from exc
        declaration = ProtocolDeclaration.from_dict(loads_json(data, max_bytes=MAX_RECORD_BYTES))
        if declaration.fingerprint != fingerprint:
            raise ConflictError("stored protocol declaration fingerprint mismatch")
        return declaration

    def get_bundle(self, address: str) -> LearningBundle:
        try:
            data = self._fs.read_bytes(
                f"bundles/{address_digest(address)}.json",
                max_bytes=MAX_LEARNING_BUNDLE_BYTES,
            )
        except FileNotFoundError as exc:
            raise NotFoundError("learning bundle is not registered") from exc
        bundle = LearningBundle.from_dict(loads_json(data, max_bytes=MAX_LEARNING_BUNDLE_BYTES))
        if bundle.address != address:
            raise ConflictError("stored learning bundle address mismatch")
        return bundle

    def get_adapter(self, address: str) -> AdapterRegistration:
        try:
            data = self._fs.read_bytes(
                f"adapters/{address_digest(address)}.json",
                max_bytes=MAX_RECORD_BYTES,
            )
        except FileNotFoundError as exc:
            raise NotFoundError("adapter registration is not registered") from exc
        registration = AdapterRegistration.from_dict(loads_json(data, max_bytes=MAX_RECORD_BYTES))
        if registration.address != address:
            raise ConflictError("stored adapter registration address mismatch")
        return registration

    def has_declaration(self, fingerprint: str) -> bool:
        try:
            self.get_declaration(fingerprint)
        except NotFoundError:
            return False
        return True

    def has_bundle(self, address: str) -> bool:
        try:
            self.get_bundle(address)
        except NotFoundError:
            return False
        return True

    def has_adapter(self, address: str) -> bool:
        try:
            self.get_adapter(address)
        except NotFoundError:
            return False
        return True

    def bundles_for_protocol(self, fingerprint: str) -> list[LearningBundle]:
        bundles: list[LearningBundle] = []
        for filename in self._fs.list_files("bundles"):
            data = self._fs.read_bytes(f"bundles/{filename}", max_bytes=MAX_LEARNING_BUNDLE_BYTES)
            bundle = LearningBundle.from_dict(loads_json(data, max_bytes=MAX_LEARNING_BUNDLE_BYTES))
            if bundle.protocol_fingerprint == fingerprint:
                bundles.append(bundle)
        return sorted(bundles, key=lambda item: item.address)

    def adapters_for_protocol(self, fingerprint: str) -> list[AdapterRegistration]:
        adapters: list[AdapterRegistration] = []
        for filename in self._fs.list_files("adapters"):
            data = self._fs.read_bytes(f"adapters/{filename}", max_bytes=MAX_RECORD_BYTES)
            adapter = AdapterRegistration.from_dict(loads_json(data, max_bytes=MAX_RECORD_BYTES))
            if adapter.protocol_fingerprint == fingerprint:
                adapters.append(adapter)
        return sorted(adapters, key=lambda item: item.address)

    def counts(self) -> dict[str, int]:
        declarations = self._fs.list_files("declarations")
        declarations_by_fingerprint: dict[str, ProtocolDeclaration] = {}
        for filename in declarations:
            data = self._fs.read_bytes(f"declarations/{filename}", max_bytes=MAX_RECORD_BYTES)
            declaration = ProtocolDeclaration.from_dict(
                loads_json(data, max_bytes=MAX_RECORD_BYTES)
            )
            if filename != f"{address_digest(declaration.fingerprint)}.json":
                raise ConflictError("protocol declaration filename mismatch")
            declarations_by_fingerprint[declaration.fingerprint] = declaration
        bundles = self._fs.list_files("bundles")
        for filename in bundles:
            data = self._fs.read_bytes(f"bundles/{filename}", max_bytes=MAX_LEARNING_BUNDLE_BYTES)
            bundle = LearningBundle.from_dict(loads_json(data, max_bytes=MAX_LEARNING_BUNDLE_BYTES))
            if filename != f"{address_digest(bundle.address)}.json":
                raise ConflictError("learning bundle filename mismatch")
            matching_declaration = declarations_by_fingerprint.get(bundle.protocol_fingerprint)
            if (
                matching_declaration is None
                or matching_declaration.conformance_address != bundle.conformance_contract.address
            ):
                raise ConflictError("learning bundle has no matching protocol declaration")
        adapters = self._fs.list_files("adapters")
        adapters_by_address: dict[str, AdapterRegistration] = {}
        for filename in adapters:
            data = self._fs.read_bytes(f"adapters/{filename}", max_bytes=MAX_RECORD_BYTES)
            adapter = AdapterRegistration.from_dict(loads_json(data, max_bytes=MAX_RECORD_BYTES))
            if filename != f"{address_digest(adapter.address)}.json":
                raise ConflictError("adapter registration filename mismatch")
            matching_declaration = declarations_by_fingerprint.get(adapter.protocol_fingerprint)
            if (
                matching_declaration is None
                or matching_declaration.conformance_address != adapter.conformance_address
                or matching_declaration.adapter_api_version != adapter.interface_version
            ):
                raise ConflictError("adapter has no matching protocol declaration")
            adapters_by_address[adapter.address] = adapter
        receipts = self._fs.list_files("receipts")
        for filename in receipts:
            data = self._fs.read_bytes(f"receipts/{filename}", max_bytes=MAX_RECORD_BYTES)
            receipt = AdapterRegistrationReceipt.from_dict(
                loads_json(data, max_bytes=MAX_RECORD_BYTES)
            )
            if filename != f"{address_digest(receipt.receipt_id)}.json":
                raise ConflictError("adapter receipt filename mismatch")
            registration = adapters_by_address.get(receipt.registration_address)
            if (
                registration is None
                or registration.protocol_fingerprint != receipt.protocol_fingerprint
            ):
                raise ConflictError("adapter receipt has no matching registration")
        return {
            "protocol_declarations": len(declarations),
            "learning_bundles": len(bundles),
            "adapter_registrations": len(adapters),
            "adapter_receipts": len(receipts),
        }


class BaseDialbook:
    visibility: Visibility

    def __init__(self, root: str | os.PathLike[str], visibility: Visibility) -> None:
        self._fs = SafeFilesystem(root)
        self.visibility = visibility

    def record_plan(self, record: DialRecord) -> WritePlan:
        if record.visibility != self.visibility:
            raise ValidationError("record visibility does not match the target dialbook")
        return _document_plan(
            self._fs,
            f"records/{address_digest(record.id)}.json",
            record.to_dict(),
        )

    def apply(self, plan: WritePlan) -> bool:
        return self._fs.apply_write(plan)

    def revert(self, plan: WritePlan) -> bool:
        return self._fs.remove_if_address(plan.relative_path, plan.content_address)

    def get(self, record_id: str) -> DialRecord:
        try:
            data = self._fs.read_bytes(
                f"records/{address_digest(record_id)}.json",
                max_bytes=MAX_RECORD_BYTES,
            )
        except FileNotFoundError as exc:
            raise NotFoundError("dial record is not registered") from exc
        record = DialRecord.from_dict(loads_json(data, max_bytes=MAX_RECORD_BYTES))
        if record.id != record_id or record.visibility != self.visibility:
            raise ConflictError("stored dial record identity or visibility mismatch")
        return record

    def records(self) -> list[DialRecord]:
        records: list[DialRecord] = []
        for filename in self._fs.list_files("records"):
            data = self._fs.read_bytes(f"records/{filename}", max_bytes=MAX_RECORD_BYTES)
            record = DialRecord.from_dict(loads_json(data, max_bytes=MAX_RECORD_BYTES))
            if record.visibility != self.visibility:
                raise ConflictError("dialbook contains a record from another visibility")
            if filename != f"{address_digest(record.id)}.json":
                raise ConflictError("dial record filename does not match its identity")
            records.append(record)
        return sorted(records, key=lambda item: item.id)

    def match(self, query: str) -> tuple[Literal["id", "url", "chant"], list[DialRecord]]:
        query = _core_id_query(query)
        if is_address(query):
            try:
                return "id", [self.get(query)]
            except NotFoundError:
                return "id", []
        return _match_records(self.records(), query)

    def count(self) -> int:
        return len(self._fs.list_files("records"))


class LocalDialbook(BaseDialbook):
    def __init__(self, root: str | os.PathLike[str]) -> None:
        super().__init__(root, "local")


class PublicDialbook(BaseDialbook):
    """A public-only view whose filesystem root cannot address the private book."""

    def __init__(self, root: str | os.PathLike[str]) -> None:
        super().__init__(root, "public")

    def build_index(self, *, persist: bool = True) -> DialbookIndex:
        index = DialbookIndex.create(visibility="public", records=self.records())
        if persist:
            plan = _document_plan(
                self._fs,
                f"indexes/{address_digest(index.address)}.json",
                index.to_dict(),
            )
            self._fs.apply_write(plan)
        return index


class PrivateDialbook(BaseDialbook):
    def __init__(self, root: str | os.PathLike[str]) -> None:
        super().__init__(root, "private")

    def policy_plan(self, policy: PrivateAccessPolicy) -> WritePlan:
        return _document_plan(
            self._fs,
            f"policies/{address_digest(policy.record_id)}.json",
            policy.to_dict(),
        )

    @contextmanager
    def registration_transaction(self, record_id: str) -> Iterator[None]:
        digest = address_digest(record_id)
        with self._fs.interprocess_lock(f"transactions/{digest}.lock"):
            yield

    def get_policy(self, record_id: str) -> PrivateAccessPolicy:
        try:
            data = self._fs.read_bytes(
                f"policies/{address_digest(record_id)}.json",
                max_bytes=MAX_RECORD_BYTES,
            )
        except FileNotFoundError as exc:
            raise NotFoundError("private access policy is not registered") from exc
        policy = PrivateAccessPolicy.from_dict(loads_json(data, max_bytes=MAX_RECORD_BYTES))
        if policy.record_id != record_id:
            raise ConflictError("stored private policy record id mismatch")
        return policy

    def build_index(self, *, persist: bool = True) -> DialbookIndex:
        index = DialbookIndex.create(visibility="private", records=self.records())
        if persist:
            plan = _document_plan(
                self._fs,
                f"indexes/{address_digest(index.address)}.json",
                index.to_dict(),
            )
            self._fs.apply_write(plan)
        return index

    def policy_count(self) -> int:
        return len(self._fs.list_files("policies"))

    def verify_policies(self, record_ids: set[str]) -> int:
        files = self._fs.list_files("policies")
        found: set[str] = set()
        for filename in files:
            data = self._fs.read_bytes(f"policies/{filename}", max_bytes=MAX_RECORD_BYTES)
            policy = PrivateAccessPolicy.from_dict(loads_json(data, max_bytes=MAX_RECORD_BYTES))
            if filename != f"{address_digest(policy.record_id)}.json":
                raise ConflictError("private policy filename mismatch")
            found.add(policy.record_id)
        if found != record_ids:
            raise ConflictError("private records and private policies are not one-to-one")
        return len(files)


class LocalState:
    def __init__(self, root: str | os.PathLike[str]) -> None:
        self._fs = SafeFilesystem(root)

    def plans_for_subscription(
        self, plan: SubscriptionPlan
    ) -> tuple[WritePlan, WritePlan | None, WritePlan]:
        subscription_plan = _document_plan(
            self._fs,
            f"plans/{address_digest(plan.plan_id)}.json",
            plan.to_dict(),
        )
        adapter_plan: WritePlan | None = None
        if plan.adapter_plan is not None:
            adapter_plan = _document_plan(
                self._fs,
                f"adapter-plans/{address_digest(plan.adapter_plan.address)}.json",
                plan.adapter_plan.to_dict(),
            )
        subscription = _document_plan(
            self._fs,
            f"subscriptions/{address_digest(plan.subscription.id)}.json",
            plan.subscription.to_dict(),
        )
        return subscription_plan, adapter_plan, subscription

    def apply_subscription(self, plan: SubscriptionPlan) -> tuple[bool, str]:
        planned = self.plans_for_subscription(plan)
        applied: list[WritePlan] = []
        subscription_created = False
        try:
            for item in planned:
                if item is None:
                    continue
                created = self._fs.apply_write(item)
                if created:
                    applied.append(item)
                if item is planned[-1]:
                    subscription_created = created
        except Exception:
            for item in reversed(applied):
                self._fs.remove_if_address(item.relative_path, item.content_address)
            raise
        return subscription_created, content_address(plan.subscription.to_dict())

    def revert_subscription(self, plan: SubscriptionPlan) -> bool:
        _, _, subscription = self.plans_for_subscription(plan)
        return self._fs.remove_if_address(subscription.relative_path, subscription.content_address)

    def subscriptions(self) -> list[LocalSubscription]:
        result: list[LocalSubscription] = []
        for filename in self._fs.list_files("subscriptions"):
            data = self._fs.read_bytes(f"subscriptions/{filename}", max_bytes=MAX_RECORD_BYTES)
            subscription = LocalSubscription.from_dict(loads_json(data, max_bytes=MAX_RECORD_BYTES))
            if filename != f"{address_digest(subscription.id)}.json":
                raise ConflictError("subscription filename does not match its identity")
            result.append(subscription)
        return sorted(result, key=lambda item: item.id)

    def verify(self) -> dict[str, int]:
        plan_files = self._fs.list_files("plans")
        plans: list[SubscriptionPlan] = []
        for filename in plan_files:
            data = self._fs.read_bytes(f"plans/{filename}", max_bytes=MAX_RECORD_BYTES)
            plan = SubscriptionPlan.from_dict(loads_json(data, max_bytes=MAX_RECORD_BYTES))
            if filename != f"{address_digest(plan.plan_id)}.json":
                raise ConflictError("subscription plan filename does not match its identity")
            plans.append(plan)
        adapter_files = self._fs.list_files("adapter-plans")
        adapter_addresses: set[str] = set()
        for filename in adapter_files:
            data = self._fs.read_bytes(
                f"adapter-plans/{filename}",
                max_bytes=MAX_RECORD_BYTES,
            )
            adapter_plan = AdapterPlan.from_dict(loads_json(data, max_bytes=MAX_RECORD_BYTES))
            if filename != f"{address_digest(adapter_plan.address)}.json":
                raise ConflictError("adapter plan filename does not match its address")
            adapter_addresses.add(adapter_plan.address)
        subscriptions = self.subscriptions()
        if any(
            subscription.adapter_plan_address is not None
            and subscription.adapter_plan_address not in adapter_addresses
            for subscription in subscriptions
        ):
            raise ConflictError("subscription refers to a missing adapter plan")
        if any(
            plan.adapter_plan is not None and plan.adapter_plan.address not in adapter_addresses
            for plan in plans
        ):
            raise ConflictError("subscription plan refers to a missing adapter plan")
        return {
            "local_subscription_plans": len(plans),
            "local_adapter_plans": len(adapter_addresses),
            "local_subscriptions": len(subscriptions),
        }

    def count(self) -> int:
        return len(self._fs.list_files("subscriptions"))


def public_index_from_home(home: str | os.PathLike[str], *, persist: bool = True) -> DialbookIndex:
    """Build only the public projection; this function never opens the private path."""

    public_root = Path(home).expanduser().absolute() / "books" / "public"
    return PublicDialbook(public_root).build_index(persist=persist)


def private_index_from_home(home: str | os.PathLike[str], *, persist: bool = True) -> DialbookIndex:
    private_root = Path(home).expanduser().absolute() / "books" / "private"
    return PrivateDialbook(private_root).build_index(persist=persist)
