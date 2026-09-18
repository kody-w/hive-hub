from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Literal

from .canonical import address_digest, canonical_bytes, content_address, is_address, loads_json
from .contracts import (
    AdapterPlan,
    AdapterRegistration,
    AdapterRegistrationReceipt,
    DialbookIndex,
    DialRecord,
    LearningBundle,
    LocalSubscription,
    PrivateAccessPolicy,
    ProtocolDeclaration,
    SubscriptionPlan,
    Visibility,
    normalize_chant,
)
from .errors import ConflictError, NotFoundError, ValidationError
from .filesystem import SafeFilesystem, WritePlan
from .limits import MAX_LEARNING_BUNDLE_BYTES, MAX_RECORD_BYTES


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
        if is_address(query):
            try:
                return "id", [self.get(query)]
            except NotFoundError:
                return "id", []
        records = self.records()
        matches = [record for record in records if query in record.urls]
        if matches:
            return "url", matches
        if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", query):
            return "url", []
        chant = normalize_chant(query)
        matches = [record for record in records if chant in record.chants]
        return "chant", matches

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
