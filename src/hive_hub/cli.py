from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from typing import Any, NoReturn, cast

from .canonical import canonical_dumps, loads_json
from .chant import (
    CHANT_PROTOCOL,
    CHANT_VOCABULARY_SHA256,
    normalize_chant,
    verify_chant,
)
from .contracts import (
    AdapterPlan,
    AdapterRegistration,
    AIJoinCard,
    ChantLocator,
    DialRecord,
    LearningBundle,
    Principal,
    PrivateAccessPolicy,
    ProtocolDeclaration,
    SubscriptionPlan,
)
from .errors import HiveHubError, LimitError, ValidationError
from .filesystem import read_external_file
from .hub import HiveHub, validate_document
from .limits import MAX_JSON_BYTES
from .schema_catalog import get_schema, schema_names
from .store import dial_from_public_hub


class JSONArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise ValidationError(message)


def _parser() -> JSONArgumentParser:
    parser = JSONArgumentParser(prog="hive-hub")
    parser.add_argument(
        "--version",
        action="version",
        version='{"kind":"hive-hub-version","schema_version":1,"version":"0.1.1"}',
    )
    parser.add_argument(
        "--home",
        help="local Hive Hub home (default: HIVE_HUB_HOME or ~/.hive-hub)",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    subcommands.add_parser("status", help="verify local state and report counts")

    validate = subcommands.add_parser("validate", help="validate a closed contract")
    validate.add_argument("document")
    validate.add_argument("--kind", dest="expected_kind")

    learn = subcommands.add_parser("learn", help="store an inert protocol declaration and bundle")
    learn.add_argument("declaration")
    learn.add_argument("bundle")

    inspect = subcommands.add_parser("inspect", help="inspect a learned protocol or bundle")
    inspect.add_argument("address")

    adapter = subcommands.add_parser("adapter", help="manage inert adapter registrations")
    adapter_subcommands = adapter.add_subparsers(dest="adapter_command", required=True)
    adapter_register = adapter_subcommands.add_parser("register")
    adapter_register.add_argument("registration")
    adapter_register.add_argument(
        "--scope", choices=["local", "public", "private"], default="local"
    )
    adapter_register.add_argument("--registered-at")
    builtin = adapter_subcommands.add_parser(
        "builtin",
        help="inspect or install optional built-in adapter contracts",
    )
    builtin_subcommands = builtin.add_subparsers(dest="builtin_command", required=True)
    builtin_subcommands.add_parser("list")
    builtin_show = builtin_subcommands.add_parser("show")
    builtin_show.add_argument("adapter_id")
    builtin_install = builtin_subcommands.add_parser("install")
    builtin_install.add_argument("adapter_id")
    builtin_install.add_argument("--apply")
    builtin_install.add_argument("--registered-at")

    register = subcommands.add_parser("register", help="register a dial record")
    register.add_argument("scope", choices=["local", "public", "private"])
    register.add_argument("record")
    register.add_argument("--policy")
    register.add_argument("--access-mode", choices=["acl-only", "acl+qr"], default="acl-only")
    register.add_argument("--policy-scope")
    register.add_argument("--policy-epoch", default="1")
    register.add_argument(
        "--qr-fragment-stdin",
        action="store_true",
        help="read a transient QR factor from stdin; never include it in JSON",
    )

    dial = subcommands.add_parser("dial", help="dial by full id, URL, or chant candidate")
    dial.add_argument("query")
    dial.add_argument("--scope", choices=["auto", "local", "public", "private"], default="auto")
    dial.add_argument("--acl-authorized", action="store_true")
    dial.add_argument("--qr-fragment-stdin", action="store_true")
    dial.add_argument("--from", dest="hub_base_url", help="plan an explicit public Hub fetch")
    dial.add_argument("--apply", metavar="PLAN_ID", help="approve the exact public fetch plan")

    chant = subcommands.add_parser(
        "chant",
        help="derive, parse, or verify a protocol-neutral seven-word chant",
    )
    chant_subcommands = chant.add_subparsers(dest="chant_command", required=True)
    chant_derive = chant_subcommands.add_parser("derive")
    chant_derive.add_argument("dial_record_id")
    chant_parse = chant_subcommands.add_parser("parse")
    chant_parse.add_argument("value")
    chant_verify = chant_subcommands.add_parser("verify")
    chant_verify.add_argument("dial_record_id")
    chant_verify.add_argument("value")

    join_card = subcommands.add_parser("join-card", help="create a human or AI join card")
    join_card.add_argument("--principal-kind", choices=["human", "ai"], required=True)
    join_card.add_argument("--principal-id", required=True)
    join_card.add_argument("--locator", required=True)
    join_card.add_argument("--expected-record-id")
    join_card.add_argument("--expected-protocol-fingerprint")
    join_card.add_argument("--adapter-plan")
    join_card.add_argument("--issued-at")

    subscribe = subcommands.add_parser(
        "subscribe",
        help="plan, apply, or revert local subscription",
    )
    subscribe_subcommands = subscribe.add_subparsers(dest="subscription_command", required=True)
    subscribe_plan = subscribe_subcommands.add_parser("plan")
    subscribe_plan.add_argument("card")
    subscribe_plan.add_argument(
        "--scope", choices=["auto", "local", "public", "private"], default="auto"
    )
    subscribe_plan.add_argument("--acl-authorized", action="store_true")
    subscribe_plan.add_argument("--qr-fragment-stdin", action="store_true")
    subscribe_apply = subscribe_subcommands.add_parser("apply")
    subscribe_apply.add_argument("plan")
    subscribe_revert = subscribe_subcommands.add_parser("revert")
    subscribe_revert.add_argument("plan")

    bootstrap = subcommands.add_parser("bootstrap", help="bootstrap exactly one join card")
    bootstrap.add_argument("card")
    bootstrap.add_argument("--apply", action="store_true")
    bootstrap.add_argument(
        "--scope", choices=["auto", "local", "public", "private"], default="auto"
    )
    bootstrap.add_argument("--acl-authorized", action="store_true")
    bootstrap.add_argument("--qr-fragment-stdin", action="store_true")

    index = subcommands.add_parser("index", help="build a separated dialbook index")
    index.add_argument("scope", choices=["public", "private"])
    index.add_argument("--no-persist", action="store_true")

    schema = subcommands.add_parser("schema", help="list or print bundled JSON Schemas")
    schema_subcommands = schema.add_subparsers(dest="schema_command", required=True)
    schema_subcommands.add_parser("list")
    schema_show = schema_subcommands.add_parser("show")
    schema_show.add_argument("name")
    return parser


def _read_document(path: str) -> Any:
    if path == "-":
        data = sys.stdin.buffer.read(MAX_JSON_BYTES + 1)
        if len(data) > MAX_JSON_BYTES:
            raise LimitError("stdin JSON exceeds the configured byte limit")
    else:
        data = read_external_file(path, max_bytes=MAX_JSON_BYTES)
    return loads_json(data, max_bytes=MAX_JSON_BYTES)


def _read_qr_fragment(enabled: bool) -> str | None:
    if not enabled:
        return None
    data = sys.stdin.buffer.readline(128)
    if len(data) > 64:
        raise ValidationError("QR fragment input exceeds the configured limit")
    try:
        fragment = data.decode("ascii").strip()
    except UnicodeDecodeError as exc:
        raise ValidationError("QR fragment must be ASCII base64url") from exc
    if not fragment:
        raise ValidationError("QR fragment stdin was empty")
    return fragment


def _emit(value: Any, *, stream: Any | None = None) -> None:
    selected = sys.stdout if stream is None else stream
    selected.write(canonical_dumps(value) + "\n")
    selected.flush()


def _handle(args: argparse.Namespace) -> Any:
    hub = HiveHub(args.home)
    if args.command == "status":
        return hub.status()
    if args.command == "validate":
        return validate_document(_read_document(args.document), expected_kind=args.expected_kind)
    if args.command == "learn":
        declaration = ProtocolDeclaration.from_dict(_read_document(args.declaration))
        bundle = LearningBundle.from_dict(_read_document(args.bundle))
        return hub.learn_protocol(declaration, bundle)
    if args.command == "inspect":
        return hub.inspect_protocol(cast(str, args.address))
    if args.command == "adapter" and args.adapter_command == "register":
        registration = AdapterRegistration.from_dict(_read_document(args.registration))
        return hub.register_adapter(
            registration,
            scope=args.scope,
            registered_at=args.registered_at,
        ).to_dict()
    if args.command == "adapter" and args.adapter_command == "builtin":
        from .adapter_runtime import (
            builtin_adapter_contracts,
            builtin_install_plan,
            get_builtin_adapter,
        )

        if args.builtin_command == "list":
            return {
                "kind": "builtin-adapter-list",
                "schema_version": 1,
                "adapters": [
                    item.summary() for item in builtin_adapter_contracts()
                ],
                "adapter_execution": False,
            }
        contracts = get_builtin_adapter(args.adapter_id)
        if args.builtin_command == "show":
            return contracts.to_dict()
        builtin_plan = builtin_install_plan(contracts)
        if args.apply is None:
            return builtin_plan
        if args.apply != builtin_plan["plan_id"]:
            raise ValidationError("built-in adapter approval does not match the current plan")
        learning = hub.learn_protocol(
            contracts.declaration,
            contracts.learning_bundle,
        )
        receipt = hub.register_adapter(
            contracts.registration,
            registered_at=args.registered_at,
        )
        return {
            "kind": "builtin-adapter-install-result",
            "schema_version": 1,
            "status": "installed",
            "adapter_id": contracts.adapter_id,
            "plan_id": contracts.plan_id,
            "protocol_fingerprint": learning["protocol_fingerprint"],
            "learning_bundle_address": learning["learning_bundle_address"],
            "adapter_registration_address": contracts.registration.address,
            "receipt": receipt.to_dict(),
            "adapter_execution": False,
        }
    if args.command == "register":
        record = DialRecord.from_dict(_read_document(args.record))
        if record.visibility != args.scope:
            raise ValidationError("record visibility does not match register scope")
        policy: PrivateAccessPolicy | None = None
        if args.policy is not None:
            if args.scope != "private":
                raise ValidationError("--policy is valid only for private records")
            if args.qr_fragment_stdin:
                raise ValidationError("--policy and --qr-fragment-stdin cannot be combined")
            policy = PrivateAccessPolicy.from_dict(_read_document(args.policy))
        elif args.scope == "private":
            policy = PrivateAccessPolicy.create(
                record_id=record.id,
                scope=args.policy_scope,
                epoch=args.policy_epoch,
                mode=args.access_mode,
                qr_fragment=_read_qr_fragment(args.qr_fragment_stdin),
            )
        elif args.qr_fragment_stdin or args.access_mode != "acl-only":
            raise ValidationError("private access options require a private record")
        return hub.register_record(record, private_policy=policy)
    if args.command == "dial":
        if args.hub_base_url is not None:
            if (
                args.scope not in {"auto", "public"}
                or args.acl_authorized
                or args.qr_fragment_stdin
            ):
                raise ValidationError("--from is public-only and cannot use private access options")
            return dial_from_public_hub(
                hub.home, args.query, args.hub_base_url, apply=args.apply
            )
        if args.apply is not None:
            raise ValidationError("--apply requires an explicit --from public Hub")
        return hub.dial(
            args.query,
            scope=args.scope,
            acl_authorized=args.acl_authorized,
            qr_fragment=_read_qr_fragment(args.qr_fragment_stdin),
        ).to_dict()
    if args.command == "chant":
        if args.chant_command == "parse":
            return {
                "kind": "chant-parse-result",
                "schema_version": 1,
                "protocol": CHANT_PROTOCOL,
                "chant": normalize_chant(args.value),
                "vocabulary_sha256": CHANT_VOCABULARY_SHA256,
                "candidate_locator_only": True,
            }
        if args.chant_command == "verify":
            verify_chant(args.dial_record_id, args.value)
        return ChantLocator.create(args.dial_record_id).to_dict()
    if args.command == "join-card":
        principal = Principal.create(
            kind=args.principal_kind,
            identifier=args.principal_id,
        )
        adapter_plan = (
            None
            if args.adapter_plan is None
            else AdapterPlan.from_dict(_read_document(args.adapter_plan))
        )
        return hub.create_join_card(
            principal=principal,
            locator=args.locator,
            expected_record_id=args.expected_record_id,
            expected_protocol_fingerprint=args.expected_protocol_fingerprint,
            adapter_plan=adapter_plan,
            issued_at=args.issued_at,
        ).to_dict()
    if args.command == "subscribe":
        if args.subscription_command == "plan":
            card = AIJoinCard.from_dict(_read_document(args.card))
            return hub.bootstrap(
                card,
                apply=False,
                scope=args.scope,
                acl_authorized=args.acl_authorized,
                qr_fragment=_read_qr_fragment(args.qr_fragment_stdin),
            ).to_dict()
        plan = SubscriptionPlan.from_dict(_read_document(args.plan))
        if args.subscription_command == "apply":
            return hub.apply_subscription(plan)
        return hub.revert_subscription(plan)
    if args.command == "bootstrap":
        card = AIJoinCard.from_dict(_read_document(args.card))
        return hub.bootstrap(
            card,
            apply=args.apply,
            scope=args.scope,
            acl_authorized=args.acl_authorized,
            qr_fragment=_read_qr_fragment(args.qr_fragment_stdin),
        ).to_dict()
    if args.command == "index":
        if args.scope == "public":
            return hub.build_public_index(persist=not args.no_persist)
        return hub.build_private_index(persist=not args.no_persist)
    if args.command == "schema":
        if args.schema_command == "list":
            return {
                "kind": "schema-list",
                "schema_version": 1,
                "schemas": list(schema_names()),
            }
        return get_schema(cast(str, args.name))
    raise ValidationError("unsupported command")


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
        _emit(_handle(args))
        return 0
    except HiveHubError as exc:
        _emit(exc.as_dict(), stream=sys.stderr)
        return 2
    except (FileNotFoundError, PermissionError, OSError) as exc:
        error = HiveHubError(
            "filesystem operation failed",
            detail={"type": type(exc).__name__},
        )
        _emit(error.as_dict(), stream=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
