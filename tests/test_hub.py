from __future__ import annotations

from hive_hub import (
    AdapterEffect,
    AdapterPlan,
    AIJoinCard,
    DialRecord,
    Principal,
    SubscriptionPlan,
    canonical_bytes,
    content_address,
    derive_chant,
)
from hive_hub.limits import MAX_ARRAY_ITEMS
from hive_hub.store import PublicDialbook

from .helpers import FIXED_TIME, WorkspaceTestCase, make_record, make_stack


class HubFlowTests(WorkspaceTestCase):
    def test_generic_non_rapp_record_dials_by_id_url_and_chant(self) -> None:
        stack = make_stack(self.work)
        record = make_record(stack)
        stack.hub.register_public_record(record)

        for query in (record.id, record.urls[0], "  FIREFLY   COMMONS  "):
            result = stack.hub.dial(query, scope="public")
            self.assertEqual(result.status, "resolved")
            self.assertEqual(result.record, record)
        inspection = stack.hub.inspect_protocol(stack.declaration.fingerprint)
        self.assertEqual(inspection["protocol_fingerprint"], stack.declaration.fingerprint)
        self.assertFalse(inspection["code_executed"])
        serialized = str(inspection).lower()
        self.assertNotIn("github", serialized)
        self.assertNotIn("rapp", serialized)
        bundle_inspection = stack.hub.inspect_bundle(stack.bundle.address)
        self.assertEqual(
            bundle_inspection["bundle"]["artifacts"][1]["content"],
            "Firefly Mesh documents are inert UTF-8 data.",
        )
        self.assertFalse(bundle_inspection["code_executed"])

    def test_chant_collisions_remain_candidate_arrays(self) -> None:
        stack = make_stack(self.work)
        alpha = make_record(
            stack,
            name="Firefly Alpha",
            url="https://firefly.invalid/hives/alpha",
            chant="shared glow",
        )
        beta = make_record(
            stack,
            name="Firefly Beta",
            url="https://firefly.invalid/hives/beta",
            chant="shared glow",
        )
        stack.hub.register_public_record(alpha)
        stack.hub.register_public_record(beta)
        result = stack.hub.dial("shared glow", scope="public")
        self.assertEqual(result.status, "ambiguous")
        self.assertEqual([item.id for item in result.candidates], sorted([alpha.id, beta.id]))
        index = stack.hub.build_public_index(persist=False)
        collision = next(
            item for item in index["chant_candidates"] if item["candidate"] == "shared glow"
        )
        self.assertEqual(collision["record_ids"], sorted([alpha.id, beta.id]))

    def test_derived_lookup_preserves_a_full_legacy_label_array(self) -> None:
        stack = make_stack(self.work)
        record = DialRecord.create(
            name="Full legacy label array",
            description="Derived lookup must not enlarge persisted legacy arrays.",
            visibility="public",
            protocol_fingerprint=stack.declaration.fingerprint,
            learning_bundle_address=stack.bundle.address,
            adapter_registration_address=stack.adapter.address,
            urls=["https://firefly.invalid/full-labels"],
            chants=[f"label{index:03d}" for index in range(MAX_ARRAY_ITEMS)],
        )
        stack.hub.register_public_record(record)
        for query in (record.chants[0], derive_chant(record.dial_id)):
            result = stack.hub.dial(query, scope="public")
            self.assertEqual(result.record, record)
            self.assertEqual(result.candidates[0].chants, record.chants)
            canonical_bytes(result.to_dict())
        index = stack.hub.build_public_index(persist=False)
        self.assertEqual(len(index["chant_candidates"]), MAX_ARRAY_ITEMS)

    def test_human_and_ai_bootstrap_are_plan_first_and_local(self) -> None:
        stack = make_stack(self.work)
        record = make_record(stack)
        stack.hub.register_public_record(record)
        for kind, identifier in (("human", "person:ada"), ("ai", "agent:beacon")):
            subscriptions_before_plan = stack.hub.local_state.count()
            card = stack.hub.create_join_card(
                principal=Principal.create(kind=kind, identifier=identifier),  # type: ignore[arg-type]
                locator=record.id,
                expected_record_id=record.id,
                expected_protocol_fingerprint=record.protocol_fingerprint,
                issued_at=FIXED_TIME,
            )
            planned = stack.hub.plan_local_subscription(card)
            self.assertEqual(planned.status, "planned")
            self.assertIsNotNone(planned.plan)
            self.assertEqual(
                stack.hub.local_state.count(),
                subscriptions_before_plan,
            )
            applied = stack.hub.apply_subscription(
                SubscriptionPlan.from_dict(planned.plan.to_dict())  # type: ignore[union-attr]
            )
            self.assertTrue(applied["created"])
            self.assertFalse(applied["adapter_effects_executed"])
        self.assertEqual(stack.hub.local_state.count(), 2)

    def test_adapter_effects_remain_explicit_inert_plans(self) -> None:
        stack = make_stack(self.work, effect_kinds=("clone", "execute"))
        record = make_record(stack)
        stack.hub.register_public_record(record)
        adapter_plan = AdapterPlan.create(
            adapter_registration_address=record.adapter_registration_address,
            record_id=record.id,
            effects=[
                AdapterEffect.create(
                    effect_id="clone-source",
                    kind="clone",
                    description="Adapter may clone after separate approval.",
                    locator=record.urls[0],
                ),
                AdapterEffect.create(
                    effect_id="execute-tool",
                    kind="execute",
                    description="Adapter may execute after separate approval.",
                ),
            ],
        )
        card = AIJoinCard.create(
            principal=Principal.create(kind="ai", identifier="agent:beacon"),
            locator=record.id,
            adapter_plan=adapter_plan,
            issued_at=FIXED_TIME,
        )
        result = stack.hub.bootstrap_one(card, apply=True)
        self.assertEqual(result.status, "applied")
        self.assertEqual(
            result.plan.subscription.adapter_effects_status,  # type: ignore[union-attr]
            "not-executed",
        )
        self.assertEqual(result.plan.adapter_plan, adapter_plan)  # type: ignore[union-attr]

    def test_bootstrap_returns_only_highest_precedence_blocker(self) -> None:
        stack = make_stack(self.work)
        missing_bundle = content_address({"missing": "bundle"})
        missing_adapter = content_address({"missing": "adapter"})
        record = DialRecord.create(
            name="Incomplete Firefly",
            description="Intentionally incomplete for precedence.",
            visibility="public",
            protocol_fingerprint=stack.declaration.fingerprint,
            learning_bundle_address=missing_bundle,
            adapter_registration_address=missing_adapter,
            urls=["https://firefly.invalid/hives/incomplete"],
            chants=["incomplete firefly"],
        )
        book = PublicDialbook(self.work / "books" / "public")
        book.apply(book.record_plan(record))
        card = AIJoinCard.create(
            principal=Principal.create(kind="ai", identifier="agent:beacon"),
            locator=record.id,
            issued_at=FIXED_TIME,
        )
        result = stack.hub.bootstrap(card)
        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.blocker, "learning-bundle-unavailable")
        self.assertEqual(result.candidate_ids, ())
        self.assertIsNone(result.plan)

    def test_adapter_blocker_follows_learning_bundle(self) -> None:
        stack = make_stack(self.work, register_adapter=False)
        record = make_record(stack)
        book = PublicDialbook(self.work / "books" / "public")
        book.apply(book.record_plan(record))
        card = AIJoinCard.create(
            principal=Principal.create(kind="human", identifier="person:ada"),
            locator=record.id,
            issued_at=FIXED_TIME,
        )
        result = stack.hub.bootstrap(card)
        self.assertEqual(result.blocker, "adapter-registration-unavailable")
