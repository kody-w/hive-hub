from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal, cast

from .canonical import canonical_bytes, content_address
from .contracts import (
    AdapterPlan,
    AdapterRegistration,
    AdapterRegistrationReceipt,
    AIJoinCard,
    BootstrapResult,
    DialIndexEntry,
    DialRecord,
    DialResult,
    LearningBundle,
    LocalSubscription,
    Principal,
    PrivateAccessPolicy,
    ProtocolDeclaration,
    SubscriptionPlan,
    Visibility,
    parse_contract,
    validate_dial_query,
)
from .errors import NotFoundError, ValidationError
from .store import (
    BaseDialbook,
    LocalDialbook,
    LocalState,
    PrivateDialbook,
    ProtocolRegistry,
    PublicDialbook,
    private_index_from_home,
    public_index_from_home,
)

DEFAULT_HOME = "~/.hive-hub"


class HiveHub:
    """Protocol-neutral orchestration over separate bounded local stores."""

    def __init__(self, home: str | os.PathLike[str] | None = None) -> None:
        selected = (
            os.fspath(home) if home is not None else os.environ.get("HIVE_HUB_HOME", DEFAULT_HOME)
        )
        self.home = Path(selected).expanduser().absolute()

    @property
    def registry(self) -> ProtocolRegistry:
        return ProtocolRegistry(self.home / "registry")

    @property
    def local_book(self) -> LocalDialbook:
        return LocalDialbook(self.home / "books" / "local")

    @property
    def public_book(self) -> PublicDialbook:
        return PublicDialbook(self.home / "books" / "public")

    @property
    def private_book(self) -> PrivateDialbook:
        return PrivateDialbook(self.home / "books" / "private")

    @property
    def local_state(self) -> LocalState:
        return LocalState(self.home / "state")

    def learn_protocol(
        self,
        declaration: ProtocolDeclaration,
        bundle: LearningBundle,
    ) -> dict[str, Any]:
        declaration = ProtocolDeclaration.from_dict(declaration.to_dict())
        bundle = LearningBundle.from_dict(bundle.to_dict())
        if bundle.protocol_fingerprint != declaration.fingerprint:
            raise ValidationError("learning bundle protocol fingerprint mismatch")
        if bundle.conformance_contract.address != declaration.conformance_address:
            raise ValidationError("learning bundle conformance contract mismatch")
        registry = self.registry
        plans = [registry.declaration_plan(declaration), registry.bundle_plan(bundle)]
        applied = []
        try:
            for plan in plans:
                if registry.apply(plan):
                    applied.append(plan)
        except Exception:
            for plan in reversed(applied):
                registry.revert(plan)
            raise
        return {
            "kind": "protocol-learning-result",
            "schema_version": 1,
            "protocol_fingerprint": declaration.fingerprint,
            "learning_bundle_address": bundle.address,
            "inert": True,
        }

    def learn_bundle(
        self,
        declaration: ProtocolDeclaration,
        bundle: LearningBundle,
    ) -> dict[str, Any]:
        return self.learn_protocol(declaration, bundle)

    def register_adapter(
        self,
        registration: AdapterRegistration,
        *,
        scope: Visibility = "local",
        registered_at: str | None = None,
    ) -> AdapterRegistrationReceipt:
        registration = AdapterRegistration.from_dict(registration.to_dict())
        declaration = self.registry.get_declaration(registration.protocol_fingerprint)
        if registration.interface_version != declaration.adapter_api_version:
            raise ValidationError("adapter interface version does not match the protocol")
        if registration.conformance_address != declaration.conformance_address:
            raise ValidationError("adapter conformance address does not match the protocol")
        receipt = AdapterRegistrationReceipt.create(
            registration=registration,
            scope=scope,
            registered_at=registered_at,
        )
        registry = self.registry
        plans = [registry.adapter_plan(registration), registry.receipt_plan(receipt)]
        applied = []
        try:
            for plan in plans:
                if registry.apply(plan):
                    applied.append(plan)
        except Exception:
            for plan in reversed(applied):
                registry.revert(plan)
            raise
        return receipt

    def _validate_record_references(self, record: DialRecord) -> None:
        declaration = self.registry.get_declaration(record.protocol_fingerprint)
        bundle = self.registry.get_bundle(record.learning_bundle_address)
        adapter = self.registry.get_adapter(record.adapter_registration_address)
        if bundle.protocol_fingerprint != declaration.fingerprint:
            raise ValidationError("record learning bundle belongs to another protocol")
        if adapter.protocol_fingerprint != declaration.fingerprint:
            raise ValidationError("record adapter belongs to another protocol")
        if bundle.conformance_contract.address != declaration.conformance_address:
            raise ValidationError("record learning bundle conformance mismatch")
        if adapter.conformance_address != declaration.conformance_address:
            raise ValidationError("record adapter conformance mismatch")

    def register_record(
        self,
        record: DialRecord,
        *,
        private_policy: PrivateAccessPolicy | None = None,
    ) -> dict[str, Any]:
        record = DialRecord.from_dict(record.to_dict())
        if private_policy is not None:
            private_policy = PrivateAccessPolicy.from_dict(private_policy.to_dict())
        self._validate_record_references(record)
        if record.visibility == "local":
            if private_policy is not None:
                raise ValidationError("local records cannot carry a private access policy")
            book: BaseDialbook = self.local_book
            record_plan = book.record_plan(record)
            created = book.apply(record_plan)
            policy_address = None
        elif record.visibility == "public":
            if private_policy is not None:
                raise ValidationError("public records cannot carry a private access policy")
            book = self.public_book
            record_plan = book.record_plan(record)
            created = book.apply(record_plan)
            policy_address = None
        else:
            private_book = self.private_book
            policy = private_policy or PrivateAccessPolicy.create(record_id=record.id)
            if policy.record_id != record.id:
                raise ValidationError("private access policy belongs to another record")
            record_plan = private_book.record_plan(record)
            policy_plan = private_book.policy_plan(policy)
            applied = []
            with private_book.registration_transaction(record.id):
                try:
                    if private_book.apply(record_plan):
                        applied.append(record_plan)
                    if private_book.apply(policy_plan):
                        applied.append(policy_plan)
                except Exception:
                    for plan in reversed(applied):
                        private_book.revert(plan)
                    raise
            created = bool(applied)
            policy_address = content_address(policy.to_dict())
        return {
            "kind": "dial-record-registration-result",
            "schema_version": 1,
            "record_id": record.id,
            "visibility": record.visibility,
            "created": created,
            "policy_address": policy_address,
        }

    def register_local_record(self, record: DialRecord) -> dict[str, Any]:
        if record.visibility != "local":
            raise ValidationError("record visibility must be local")
        return self.register_record(record)

    def register_public_record(self, record: DialRecord) -> dict[str, Any]:
        if record.visibility != "public":
            raise ValidationError("record visibility must be public")
        return self.register_record(record)

    def register_private_record(
        self,
        record: DialRecord,
        *,
        policy: PrivateAccessPolicy | None = None,
    ) -> dict[str, Any]:
        if record.visibility != "private":
            raise ValidationError("record visibility must be private")
        return self.register_record(record, private_policy=policy)

    @staticmethod
    def create_join_card(
        *,
        principal: Principal,
        locator: str,
        expected_record_id: str | None = None,
        expected_protocol_fingerprint: str | None = None,
        adapter_plan: AdapterPlan | None = None,
        issued_at: str | None = None,
    ) -> AIJoinCard:
        return AIJoinCard.create(
            principal=principal,
            locator=locator,
            expected_record_id=expected_record_id,
            expected_protocol_fingerprint=expected_protocol_fingerprint,
            adapter_plan=adapter_plan,
            issued_at=issued_at,
        )

    @staticmethod
    def _dial_result(
        query_kind: Literal["id", "url", "chant"],
        records: list[DialRecord],
    ) -> DialResult:
        ordered = sorted(records, key=lambda item: item.id)
        if not ordered:
            return DialResult.unreachable()
        candidates = tuple(DialIndexEntry.from_record(record) for record in ordered)
        if len(ordered) == 1:
            return DialResult("resolved", query_kind, candidates, ordered[0])
        return DialResult("ambiguous", query_kind, candidates, None)

    def _dial_book(self, book: BaseDialbook, query: str) -> DialResult:
        query_kind, records = book.match(query)
        return self._dial_result(query_kind, records)

    def _dial_private(
        self,
        query: str,
        *,
        acl_authorized: bool,
        qr_fragment: str | None,
    ) -> DialResult:
        if not acl_authorized:
            return DialResult.unreachable()
        private_book = self.private_book
        query_kind, records = private_book.match(query)
        authorized: list[DialRecord] = []
        for record in records:
            try:
                policy = private_book.get_policy(record.id)
            except NotFoundError:
                continue
            if policy.permits(
                acl_authorized=acl_authorized,
                qr_fragment=qr_fragment,
            ):
                authorized.append(record)
        return self._dial_result(query_kind, authorized)

    def dial(
        self,
        query: str,
        *,
        scope: Literal["auto", "local", "public", "private"] = "auto",
        acl_authorized: bool = False,
        qr_fragment: str | None = None,
    ) -> DialResult:
        if not isinstance(acl_authorized, bool):
            raise ValidationError("ACL authorization must be a boolean")
        candidate = validate_dial_query(query)
        if scope == "local":
            return self._dial_book(self.local_book, candidate)
        if scope == "public":
            return self._dial_book(self.public_book, candidate)
        if scope == "private":
            return self._dial_private(
                candidate,
                acl_authorized=acl_authorized,
                qr_fragment=qr_fragment,
            )
        if scope != "auto":
            raise ValidationError("dial scope must be auto, local, public, or private")
        local_result = self._dial_book(self.local_book, candidate)
        if local_result.status != "unreachable":
            return local_result
        public_result = self._dial_book(self.public_book, candidate)
        if public_result.status != "unreachable":
            return public_result
        return self._dial_private(
            candidate,
            acl_authorized=acl_authorized,
            qr_fragment=qr_fragment,
        )

    @staticmethod
    def _bootstrap_result(
        *,
        status: Literal["planned", "applied", "blocked", "unreachable"],
        card: AIJoinCard,
        record_id: str | None = None,
        blocker: str | None = None,
        candidate_ids: tuple[str, ...] = (),
        plan: SubscriptionPlan | None = None,
        subscription_address: str | None = None,
    ) -> BootstrapResult:
        result = BootstrapResult(
            status=status,
            card_id=card.card_id,
            record_id=record_id,
            blocker=blocker,
            candidate_ids=tuple(sorted(set(candidate_ids))),
            plan=plan,
            subscription_address=subscription_address,
        )
        return BootstrapResult.from_dict(result.to_dict())

    def bootstrap(
        self,
        card: AIJoinCard,
        *,
        apply: bool = False,
        scope: Literal["auto", "local", "public", "private"] = "auto",
        acl_authorized: bool = False,
        qr_fragment: str | None = None,
    ) -> BootstrapResult:
        card = AIJoinCard.from_dict(card.to_dict())
        dial_result = self.dial(
            card.locator,
            scope=scope,
            acl_authorized=acl_authorized,
            qr_fragment=qr_fragment,
        )
        if dial_result.status == "unreachable":
            return self._bootstrap_result(status="unreachable", card=card)
        if dial_result.status == "ambiguous":
            return self._bootstrap_result(
                status="blocked",
                card=card,
                blocker="ambiguous-dial",
                candidate_ids=tuple(candidate.id for candidate in dial_result.candidates),
            )
        record = cast(DialRecord, dial_result.record)
        if (card.expected_record_id is not None and card.expected_record_id != record.id) or (
            card.expected_protocol_fingerprint is not None
            and card.expected_protocol_fingerprint != record.protocol_fingerprint
        ):
            return self._bootstrap_result(
                status="blocked",
                card=card,
                record_id=record.id,
                blocker="card-expectation-mismatch",
            )
        try:
            declaration = self.registry.get_declaration(record.protocol_fingerprint)
        except NotFoundError:
            return self._bootstrap_result(
                status="blocked",
                card=card,
                record_id=record.id,
                blocker="protocol-declaration-unavailable",
            )
        try:
            bundle = self.registry.get_bundle(record.learning_bundle_address)
        except NotFoundError:
            return self._bootstrap_result(
                status="blocked",
                card=card,
                record_id=record.id,
                blocker="learning-bundle-unavailable",
            )
        if bundle.protocol_fingerprint != record.protocol_fingerprint:
            return self._bootstrap_result(
                status="blocked",
                card=card,
                record_id=record.id,
                blocker="learning-bundle-mismatch",
            )
        if bundle.conformance_contract.address != declaration.conformance_address:
            return self._bootstrap_result(
                status="blocked",
                card=card,
                record_id=record.id,
                blocker="learning-bundle-mismatch",
            )
        try:
            adapter = self.registry.get_adapter(record.adapter_registration_address)
        except NotFoundError:
            return self._bootstrap_result(
                status="blocked",
                card=card,
                record_id=record.id,
                blocker="adapter-registration-unavailable",
            )
        if adapter.protocol_fingerprint != record.protocol_fingerprint:
            return self._bootstrap_result(
                status="blocked",
                card=card,
                record_id=record.id,
                blocker="adapter-registration-mismatch",
            )
        if adapter.conformance_address != declaration.conformance_address:
            return self._bootstrap_result(
                status="blocked",
                card=card,
                record_id=record.id,
                blocker="adapter-registration-mismatch",
            )
        if card.adapter_plan is not None and (
            card.adapter_plan.record_id != record.id
            or card.adapter_plan.adapter_registration_address != record.adapter_registration_address
        ):
            return self._bootstrap_result(
                status="blocked",
                card=card,
                record_id=record.id,
                blocker="adapter-plan-mismatch",
            )
        subscription = LocalSubscription.create(
            record=record,
            locator=card.locator,
            principal=card.principal,
            adapter_plan=card.adapter_plan,
            created_at=card.issued_at,
        )
        plan = SubscriptionPlan.create(
            card_id=card.card_id,
            subscription=subscription,
            adapter_plan=card.adapter_plan,
        )
        if not apply:
            return self._bootstrap_result(
                status="planned",
                card=card,
                record_id=record.id,
                plan=plan,
            )
        _, subscription_address = self.local_state.apply_subscription(plan)
        return self._bootstrap_result(
            status="applied",
            card=card,
            record_id=record.id,
            plan=plan,
            subscription_address=subscription_address,
        )

    def plan_local_subscription(
        self,
        card: AIJoinCard,
        *,
        scope: Literal["auto", "local", "public", "private"] = "auto",
        acl_authorized: bool = False,
        qr_fragment: str | None = None,
    ) -> BootstrapResult:
        return self.bootstrap(
            card,
            apply=False,
            scope=scope,
            acl_authorized=acl_authorized,
            qr_fragment=qr_fragment,
        )

    def bootstrap_one(
        self,
        card: AIJoinCard,
        *,
        apply: bool = False,
        scope: Literal["auto", "local", "public", "private"] = "auto",
        acl_authorized: bool = False,
        qr_fragment: str | None = None,
    ) -> BootstrapResult:
        return self.bootstrap(
            card,
            apply=apply,
            scope=scope,
            acl_authorized=acl_authorized,
            qr_fragment=qr_fragment,
        )

    def apply_subscription(self, plan: SubscriptionPlan) -> dict[str, Any]:
        plan = SubscriptionPlan.from_dict(plan.to_dict())
        created, address = self.local_state.apply_subscription(plan)
        return {
            "kind": "local-subscription-apply-result",
            "schema_version": 1,
            "plan_id": plan.plan_id,
            "subscription_id": plan.subscription.id,
            "subscription_address": address,
            "created": created,
            "adapter_effects_executed": False,
        }

    def revert_subscription(self, plan: SubscriptionPlan) -> dict[str, Any]:
        plan = SubscriptionPlan.from_dict(plan.to_dict())
        removed = self.local_state.revert_subscription(plan)
        return {
            "kind": "local-subscription-revert-result",
            "schema_version": 1,
            "plan_id": plan.plan_id,
            "subscription_id": plan.subscription.id,
            "removed": removed,
            "adapter_effects_executed": False,
        }

    def inspect_protocol(self, query: str) -> dict[str, Any]:
        if not query.startswith("urn:hivehub:sha256:"):
            raise ValidationError("protocol inspection requires a full content address")
        fingerprint = query
        bundle_match: LearningBundle | None = None
        try:
            declaration = self.registry.get_declaration(fingerprint)
        except NotFoundError:
            try:
                bundle_match = self.registry.get_bundle(query)
            except NotFoundError as exc:
                raise NotFoundError("protocol or learning bundle is not registered") from exc
            fingerprint = bundle_match.protocol_fingerprint
            declaration = self.registry.get_declaration(fingerprint)
        bundles = self.registry.bundles_for_protocol(fingerprint)
        adapters = self.registry.adapters_for_protocol(fingerprint)
        return {
            "kind": "protocol-inspection",
            "schema_version": 1,
            "protocol_fingerprint": fingerprint,
            "declaration": declaration.to_dict(),
            "selected_bundle_address": (None if bundle_match is None else bundle_match.address),
            "selected_bundle": (None if bundle_match is None else bundle_match.to_dict()),
            "learning_bundles": [
                {
                    "address": bundle.address,
                    "bundle_version": bundle.bundle_version,
                    "summary": bundle.summary,
                    "artifact_addresses": [
                        artifact.content_address for artifact in bundle.artifacts
                    ],
                }
                for bundle in bundles
            ],
            "adapters": [
                {
                    "address": adapter.address,
                    "name": adapter.name,
                    "version": adapter.adapter_version,
                    "locator": adapter.locator,
                    "effect_kinds": list(adapter.effect_kinds),
                }
                for adapter in adapters
            ],
            "code_executed": False,
        }

    def inspect_bundle(self, address: str) -> dict[str, Any]:
        bundle = self.registry.get_bundle(address)
        declaration = self.registry.get_declaration(bundle.protocol_fingerprint)
        if bundle.conformance_contract.address != declaration.conformance_address:
            raise ValidationError("learning bundle conformance contract mismatch")
        return {
            "kind": "learning-bundle-inspection",
            "schema_version": 1,
            "address": bundle.address,
            "protocol_fingerprint": bundle.protocol_fingerprint,
            "bundle": bundle.to_dict(),
            "code_executed": False,
        }

    def build_public_index(self, *, persist: bool = True) -> dict[str, Any]:
        return public_index_from_home(self.home, persist=persist).to_dict()

    def build_private_index(self, *, persist: bool = True) -> dict[str, Any]:
        return private_index_from_home(self.home, persist=persist).to_dict()

    def status(self) -> dict[str, Any]:
        counts = self.registry.counts()
        local_records = self.local_book.records()
        public_records = self.public_book.records()
        private_records = self.private_book.records()
        for record in local_records + public_records + private_records:
            self._validate_record_references(record)
        private_policies = self.private_book.verify_policies(
            {record.id for record in private_records}
        )
        local_state_counts = self.local_state.verify()
        counts.update(
            {
                "local_records": len(local_records),
                "public_records": len(public_records),
                "private_records": len(private_records),
                "private_policies": private_policies,
                **local_state_counts,
            }
        )
        return {
            "kind": "hive-hub-status",
            "schema_version": 1,
            "version": "0.1.1",
            "home": str(self.home),
            "counts": counts,
            "network_used": False,
        }


def validate_document(value: Any, *, expected_kind: str | None = None) -> dict[str, Any]:
    contract = parse_contract(value, expected_kind=expected_kind)
    document = cast(dict[str, Any], contract.to_dict())
    return {
        "kind": "validation-result",
        "schema_version": 1,
        "valid": True,
        "contract_kind": document["kind"],
        "content_address": content_address(document),
        "canonical_size": len(canonical_bytes(document)),
        "document": document,
    }


Hub = HiveHub
