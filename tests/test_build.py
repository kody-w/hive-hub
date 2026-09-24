"""Tests for tools/build.py: card validation, determinism, chants and starter templates."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "tools" / "build.py"


def load_builder() -> ModuleType:
    spec = importlib.util.spec_from_file_location("hub_build", BUILDER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


build = load_builder()

COMMIT = "2bd7c95152ede719b6418b80e2bdc2cd457bf711"
DIGEST = "a" * 64
FOUNDER = "SHA256:q18VTrWDieC+Sc25wpbcIHm4/gUotkmUJpyFgDeOdyY"
PROTOCOL = {
    "card": "protocol", "id": "hive-md", "name": "Test protocol", "status": "experimental",
    "spec": f"https://example.org/specs/{COMMIT}/SPEC.md", "spec_sha256": DIGEST,
    "checker": "python check.py <hive>", "checker_sha256": DIGEST,
    "agent": f"https://example.org/agents/{COMMIT}/hive_agent.py", "agent_sha256": DIGEST,
}
HIVE = {
    "card": "hive", "name": "Model", "protocol": "hive-md", "status": "experimental",
    "hive": "0123456789abcdef0123456789abcdef", "root": "f934db89e0c73d71843d634b8ddbd53154732735",
    "founder": FOUNDER, "channel": "Ask a member in person.",
}
ORG = {"card": "organization", "name": "Acme", "status": "specified", "hive": "template",
       "starter": "team"}
STARTER = {"card": "starter", "name": "Team starter", "status": "experimental",
           "template": "starters/team/", "org": "acme"}
TEMPLATE = {
    "starters/team/HIVE.md": "---\nhive: <filled at create time>\nversion: 1\napprovals: 2\n"
                             "fields: id=id; status=status\n---\n\n# Team\n",
    "starters/team/.gitattributes": "* text eol=lf\n",
    "starters/team/README.md": "# Team starter\n\nPull it down, then create a Hive from it.\n",
    "starters/team/shared/tasks/T-1.md": "---\nid: T-1\nstatus: open\n---\n\nFirst task.\n",
    "starters/team/shared/tasks/T-2.md": "---\nid: T-2\nstatus: blocked\ndepends_on: T-1\n---\n\n"
                                         "Needs [[T-1]].\n",
}
Files = dict[str, "str | bytes | None"]


def card(fields: dict[str, str], body: str = "One public paragraph.") -> str:
    return str(build.card_text(fields, body + "\n" if body else ""))


def base_files() -> Files:
    return {
        "HUB.md": "# Test hub\n\nA hub for tests.\n",
        "cards/protocols/hive-md.md": card(PROTOCOL, "A test protocol."),
        "cards/hives/model.md": card(HIVE),
    }


def with_starter() -> Files:
    files = base_files()
    files["cards/orgs/acme.md"] = card(ORG, "")
    files["cards/starters/team.md"] = card(STARTER, "")
    files.update(TEMPLATE)
    return files


class Hub:
    """A throwaway hub folder built from a dictionary of files."""

    def __init__(self, files: Files) -> None:
        self._folder = tempfile.TemporaryDirectory()
        self.root = Path(self._folder.name) / "hub"
        self.root.mkdir()
        self.write(files)

    def write(self, files: Files) -> None:
        for relative, content in files.items():
            path = self.root / relative
            if content is None:
                path.unlink()
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content if isinstance(content, bytes) else content.encode("utf-8"))

    def problems(self) -> list[str]:
        try:
            build.build(self.root)
        except build.BuildError as error:
            return list(error.problems)
        return []

    def close(self) -> None:
        self._folder.cleanup()


class HubCase(unittest.TestCase):
    def hub(self, files: Files | None = None) -> Hub:
        hub = Hub(base_files() if files is None else files)
        self.addCleanup(hub.close)
        return hub

    def assertRefused(self, hub: Hub, fragment: str) -> None:
        problems = hub.problems()
        self.assertTrue(any(fragment in problem for problem in problems),
                        f"expected {fragment!r} in {problems}")

    def refused_with(self, fields: dict[str, str], fragment: str,
                     path: str = "cards/hives/model.md",
                     body: str = "One public paragraph.") -> None:
        hub = self.hub()
        hub.write({path: card(fields, body)})
        self.assertRefused(hub, fragment)


class RepositoryTests(unittest.TestCase):
    def test_views_are_current_and_check_passes(self) -> None:
        self.assertEqual(build.differences(ROOT, build.build(ROOT)), [])
        result = subprocess.run([sys.executable, "-B", str(BUILDER), "--check"],
                                capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_every_card_json_rebuilds_its_exact_file(self) -> None:
        index = json.loads((ROOT / "views/api/v2/index.json").read_text("utf-8"))
        self.assertEqual(index["api"], "hub/v2")
        for entry in index["cards"]:
            with self.subTest(card=entry["path"]):
                data = json.loads((ROOT / "views" / entry["json"]).read_text("utf-8"))
                text = build.card_text(data["frontmatter"], data["body"]).encode("utf-8")
                self.assertEqual(text, (ROOT / entry["path"]).read_bytes())
                self.assertEqual(hashlib.sha256(text).hexdigest(), entry["sha256"])
                self.assertEqual(data["sha256"], entry["sha256"])
                self.assertEqual(entry["chant"], build.chant(bytes.fromhex(entry["sha256"])))

    def test_protocol_cards_pin_their_sources(self) -> None:
        index = json.loads((ROOT / "views/api/v2/index.json").read_text("utf-8"))
        cards = {entry["slug"]: json.loads((ROOT / "views" / entry["json"]).read_text("utf-8"))
                 for entry in index["cards"] if entry["kind"] == "protocol"}
        self.assertEqual(sorted(cards), ["hive-md", "rapp-hive/1", "rapp-hive/2"])
        hive_md = cards["hive-md"]["frontmatter"]
        self.assertEqual(hive_md["status"], "experimental")
        self.assertIn(f"/{COMMIT}/HIVE-MD.md", hive_md["spec"])
        self.assertEqual(hive_md["spec_sha256"],
                         "f3186e0d88cc36e18582171fff4ed9a68feddc4ae316f66fb8acc2982892fd96")
        self.assertEqual(hive_md["checker"], "python agents/hive_agent.py check <hive>")
        self.assertIn(f"/{COMMIT}/agents/hive_agent.py", hive_md["agent"])
        agent = "e9a2d7243da31fd2388f140bb8138c3d8d2db428ad09075530eb049a0355e8dd"
        self.assertEqual((hive_md["agent_sha256"], hive_md["checker_sha256"]), (agent, agent))
        rapp_hive_1 = cards["rapp-hive/1"]["frontmatter"]
        self.assertEqual(rapp_hive_1["status"], "in force")
        self.assertIn("/29ead23b21645f8d7682ee00414930ffa9ce0ca6/protocols/rapp-hive/1/SPEC.md",
                      rapp_hive_1["spec"])
        frozen = cards["rapp-hive/2"]["frontmatter"]
        self.assertEqual(frozen["status"], "frozen")
        self.assertTrue(frozen["spec"].endswith("/protocols/rapp-hive/2/FROZEN.md"))
        self.assertNotIn("agent", frozen)

    def test_contoso_card_says_it_has_no_live_shared_copy(self) -> None:
        path = ROOT / "views/api/v2/hives/contoso-model-hive.json"
        fields = json.loads(path.read_text("utf-8"))["frontmatter"]
        self.assertNotIn("address", fields)
        self.assertIn("no live shared copy", fields["channel"])
        self.assertIn(f"/rapp-model-hive/tree/{COMMIT}/example/contoso-onboarding-public",
                      fields["public_copy"])
        self.assertEqual((fields["root"], fields["founder"]),
                         ("f934db89e0c73d71843d634b8ddbd53154732735", FOUNDER))


def view_files(root: Path) -> dict[str, bytes]:
    return {path.relative_to(root).as_posix(): path.read_bytes()
            for path in sorted((root / "views").rglob("*")) if path.is_file()}


class DeterminismTests(HubCase):
    def test_build_is_deterministic_and_matches_the_shipped_views(self) -> None:
        self.assertEqual(build.build(ROOT), build.build(ROOT))
        hub = self.hub({})
        shutil.copy2(ROOT / "HUB.md", hub.root / "HUB.md")
        shutil.copytree(ROOT / "cards", hub.root / "cards")
        build.write(hub.root, build.build(hub.root))
        first = view_files(hub.root)
        build.write(hub.root, build.build(hub.root))
        self.assertEqual(view_files(hub.root), first)
        self.assertEqual(first, view_files(ROOT))

    def test_check_reports_drift_missing_and_extra_files(self) -> None:
        hub = self.hub()
        views = build.build(hub.root)
        build.write(hub.root, views)
        self.assertEqual(build.differences(hub.root, views), [])
        (hub.root / "views/chants.txt").write_bytes(b"edited\n")
        (hub.root / "views/site/extra.html").write_bytes(b"<p>stale</p>\n")
        (hub.root / "views/api/v2/index.json").unlink()
        found = "\n".join(build.differences(hub.root, views))
        self.assertIn("views/chants.txt: differs", found)
        self.assertIn("views/site/extra.html: not generated", found)
        self.assertIn("views/api/v2/index.json: missing", found)
        result = subprocess.run([sys.executable, "-B", str(BUILDER), "--check", "--root",
                                 str(hub.root)], capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 1)
        self.assertIn("out of date", result.stderr)
        build.write(hub.root, views)
        self.assertEqual(build.differences(hub.root, views), [])
        self.assertFalse((hub.root / "views/site/extra.html").exists())


class ValidationTests(HubCase):
    def test_base_fixtures_build(self) -> None:
        self.assertEqual(self.hub().problems(), [])
        self.assertEqual(self.hub(with_starter()).problems(), [])

    def test_unknown_fields_are_refused(self) -> None:
        self.refused_with({**HIVE, "color": "blue"}, "unknown field(s): color")
        self.refused_with({**PROTOCOL, "homepage": "x"}, "unknown field(s): homepage",
                          path="cards/protocols/hive-md.md")

    def test_missing_pins_are_refused(self) -> None:
        for pin in ("hive", "root", "founder"):
            with self.subTest(pin=pin):
                fields = {key: value for key, value in HIVE.items() if key != pin}
                self.refused_with(fields, f"missing pin(s) or field(s): {pin}")
        for dropped in ("spec_sha256", "agent_sha256", "checker"):
            with self.subTest(dropped=dropped):
                fields = {key: value for key, value in PROTOCOL.items() if key != dropped}
                self.refused_with(fields, f"missing pin(s) or field(s): {dropped}",
                                  path="cards/protocols/hive-md.md")

    def test_planned_hive_may_omit_all_pins_but_not_some(self) -> None:
        planned = {key: value for key, value in HIVE.items() if key not in build.PINS}
        planned["status"] = "planned"
        hub = self.hub()
        hub.write({"cards/hives/model.md": card(planned)})
        self.assertEqual(hub.problems(), [])
        hub.write({"cards/hives/model.md": card({**planned, "root": HIVE["root"]})})
        self.assertRefused(hub, "missing pin(s) or field(s): hive, founder")

    def test_bad_fingerprints_are_refused(self) -> None:
        body = FOUNDER[len("SHA256:"):]
        for value in (body, "sha256:" + body, FOUNDER + "=", FOUNDER[:-1] + "Z", FOUNDER[:-1],
                      FOUNDER.replace("+", "-").replace("/", "_"),
                      "MD5:16:27:ac:a5:76:28:2d:36:63:1b:56:4d:eb:df:a6:48"):
            with self.subTest(founder=value):
                self.refused_with({**HIVE, "founder": value}, "founder ")

    def test_bad_commit_ids_are_refused(self) -> None:
        for value in (HIVE["root"].upper(), HIVE["root"][:10], "0" * 40, "g" + HIVE["root"][1:]):
            with self.subTest(root=value):
                self.refused_with({**HIVE, "root": value}, "root must be the full commit id")
        for key, value in (("spec", "https://example.org/specs/main/SPEC.md"),
                           ("agent", f"https://example.org/agents/{COMMIT[:7]}/hive_agent.py")):
            with self.subTest(key=key):
                self.refused_with({**PROTOCOL, key: value}, f"{key} must be pinned",
                                  path="cards/protocols/hive-md.md")
        self.refused_with({**PROTOCOL, "spec_sha256": DIGEST.upper()}, "spec_sha256 must be 64",
                          path="cards/protocols/hive-md.md")

    def test_duplicate_slugs_are_refused(self) -> None:
        hub = self.hub()
        hub.write({"cards/hives/team/model.md": card(HIVE)})
        self.assertRefused(hub, "duplicate slug model")

    def test_credentials_in_urls_are_refused(self) -> None:
        for key, value in (
                ("address", "https://avery:secret@hives/team/model.git"),
                ("address", "ssh://git@hives/team/model.git"),
                ("address", "https://hives.example.org/team/model.git?access_token=abc"),
                ("public_copy", "https://reader:secret@copies/copy"),
                ("public_copy", "https://example.org/copy?token=abc")):
            with self.subTest(key=key, value=value):
                self.refused_with({**HIVE, key: value}, "credentials")
        self.refused_with({**PROTOCOL, "spec": f"https://user@specs/{COMMIT}/SPEC.md"},
                          "credentials", path="cards/protocols/hive-md.md")

    def test_absolute_paths_are_refused(self) -> None:
        self.refused_with(HIVE, "absolute path", body="The Hive sits in /srv/hives/model.")
        self.refused_with(HIVE, "absolute path", body="The Hive sits in D:\\hives\\model.")
        for value in ("/srv/hives/model.git", "file:///srv/hives/model.git", "D:/hives/model.git"):
            with self.subTest(address=value):
                self.refused_with({**HIVE, "address": value}, "absolute path")
        self.refused_with({**HIVE, "address": "../model.git"}, "local path")

    def test_addresses_and_statuses_are_checked(self) -> None:
        self.refused_with({**HIVE, "address": "http://hives.example.org/model.git"}, "address")
        self.refused_with({**HIVE, "address": "hives.example.org:team/model.git"}, "address")
        self.refused_with({**HIVE, "status": "live"}, "status must be one of")
        self.refused_with({**PROTOCOL, "status": "planned"}, "status must be one of",
                          path="cards/protocols/hive-md.md")
        hub = self.hub()
        address = "ssh://hives.example.org:2222/team/model.git"
        hub.write({"cards/hives/model.md": card({**HIVE, "address": address})})
        self.assertEqual(hub.problems(), [])

    def test_card_form_is_exact(self) -> None:
        text = card(HIVE)
        for changed, fragment in (
                (text.replace("\n", "\r\n"), "LF line endings"),
                (text.replace("status: experimental", "status: experimental "), "trailing spaces"),
                (text.replace("status: experimental", "status:experimental"), "`key: value`"),
                (text.replace("---\n\nOne", "---\nOne"), "one blank line"),
                (text + "\n", "exactly one newline"),
                (text.replace("One public", "One\tpublic"), "tabs"),
                (text.replace("One public", "One pu\u0301blic"), "NFC"),
                ("\ufeff" + text, "byte-order mark"),
                (text.replace("One public", "One \u202epublic"), "bidi"),
                (text.replace("card: hive\n", "card: hive\ncard: hive\n"), "appears twice")):
            with self.subTest(fragment=fragment):
                hub = self.hub()
                hub.write({"cards/hives/model.md": changed})
                self.assertRefused(hub, fragment)

    def test_card_location_and_kind_must_agree(self) -> None:
        self.refused_with(PROTOCOL, "card must be hive")
        self.refused_with({**PROTOCOL, "id": "other"}, "cards/protocols/<id>.md",
                          path="cards/protocols/hive-md.md")
        hub = self.hub()
        hub.write({"cards/hives/notes.txt": "notes\n", "cards/hives/.draft.md": card(HIVE),
                   "cards/extras/x.md": card(HIVE), "cards/hives/Model2.md": card(HIVE)})
        problems = "\n".join(hub.problems())
        for fragment in ("a card is a .md file", "hidden files are refused",
                         "cards live in cards/", "lowercase letters, digits"):
            self.assertIn(fragment, problems)

    def test_hive_body_is_one_short_public_paragraph(self) -> None:
        self.refused_with(HIVE, "exactly one short public paragraph", body="One.\n\nTwo.")
        self.refused_with(HIVE, "at most 1000 characters", body=" ".join(["word"] * 250))
        self.refused_with(HIVE, "exactly one short public paragraph", body="")

    def test_cross_references_must_resolve(self) -> None:
        self.refused_with({**HIVE, "protocol": "nope"}, "no protocol card nope")
        self.refused_with({**HIVE, "org": "nobody"}, "no organization card nobody")
        files = with_starter()
        files["cards/orgs/acme.md"] = card({**ORG, "hive": "missing"}, "")
        self.assertRefused(self.hub(files), "no hive card missing")
        files = with_starter()
        files["cards/starters/team.md"] = card({**STARTER, "org": "other"}, "")
        hub = self.hub(files)
        self.assertRefused(hub, "no organization card other")
        self.assertRefused(hub, "its starter names another org")

    def test_links_are_refused(self) -> None:
        hub = self.hub()
        try:
            os.symlink(hub.root / "cards/hives/model.md", hub.root / "cards/hives/copy.md")
        except (OSError, NotImplementedError):
            self.skipTest("this system does not allow creating symlinks")
        self.assertRefused(hub, "links are refused")


class ChantTests(HubCase):
    def test_vocabulary_is_the_frozen_list(self) -> None:
        self.assertEqual(len(build.WORDS), 128)
        self.assertEqual(len(set(build.WORDS)), 128)
        self.assertEqual(hashlib.sha256("\n".join(build.WORDS).encode()).hexdigest(),
                         "325f47d38851721f16cf111f80114d8d9146e84813fa6822fe2ad38dd18dbb36")

    def test_chant_is_the_first_seven_digest_bytes_modulo_128(self) -> None:
        digest = bytes([0, 1, 2, 127, 128, 255, 64]) + bytes(25)
        words = build.WORDS
        expected = (words[0], words[1], words[2], words[127], words[0], words[127], words[64])
        self.assertEqual(build.chant(digest), "-".join(expected))

    def test_chant_collisions_are_shown(self) -> None:
        same = "-".join([build.WORDS[0]] * 7)
        hub = self.hub()
        with mock.patch.object(build, "chant", return_value=same):
            views = build.build(hub.root)
        index = json.loads(views["views/api/v2/index.json"])
        self.assertEqual(index["collisions"],
                         [{"chant": same, "cards": ["protocol/hive-md", "hive/model"]}])
        chants = views["views/chants.txt"].decode()
        marked = [line for line in chants.splitlines() if line.endswith("  COLLISION")]
        self.assertEqual(len(marked), 2)
        self.assertIn("Chant collisions", views["views/site/index.html"].decode())
        self.assertIn("Chant collision:", views["views/site/hives/model.html"].decode())


class TemplateTests(HubCase):
    """Starter templates obey the hive-md file rules (HIVE-MD.md at rapp-model-hive@2bd7c95)."""

    def test_valid_template_builds_starter_and_org_views(self) -> None:
        views = build.build(self.hub(with_starter()).root)
        self.assertIn("views/api/v2/starters/team.json", views)
        self.assertIn("views/site/orgs/acme.html", views)
        self.assertIn("npx degit", views["views/site/starters/team.html"].decode())

    def test_template_violations_are_refused(self) -> None:
        long_name = "starters/team/shared/tasks/" + "x" * 110 + ".md"
        cases: list[tuple[Files, str]] = [
            ({"starters/team/shared/tasks/AGENTS.md": "x\n"}, "instruction file names"),
            ({"starters/team/shared/tasks/Claude.md": "x\n"}, "instruction file names"),
            ({"starters/team/shared/tasks/.notes.md": "x\n"}, "no hidden files"),
            ({"starters/team/shared/tasks/run.py": "print(1)\n"}, "end in .md"),
            ({"starters/team/shared/loose.md": "x\n"}, "sit in a folder under shared/"),
            ({"starters/team/members/avery/MEMBER.md": "x\n"}, "holds no members/"),
            ({"starters/team/NOTES.md": "x\n"}, "template root holds only"),
            ({"starters/team/.gitattributes": "* text=auto\n"}, "exactly `* text eol=lf`"),
            ({"starters/team/README.md": None}, "needs README.md"),
            ({"starters/team/HIVE.md": "---\nhive: x\nversion: 1\n---\n"}, "approvals"),
            ({"starters/team/HIVE.md": "---\nhive: x\nversion: 2\napprovals: 2\n---\n"},
             "version: 1"),
            ({"starters/team/HIVE.md": "---\nhive: x\nversion: 1\napprovals: 2\nowner: a\n---\n"},
             "holds only"),
            ({"starters/team/HIVE.md": "---\nversion: 1\napprovals: 2\n---\n"},
             "hive: placeholder"),
            ({"starters/team/shared/tasks/T-3.md": "```dataviewjs\nrun()\n```\n"}, "dataviewjs"),
            ({"starters/team/shared/tasks/T-3.md": "Data lives in /srv/data.\n"}, "absolute paths"),
            ({"starters/team/shared/tasks/T-3.md": "a\u202eb\n"}, "control, bidi"),
            ({"starters/team/shared/tasks/con.md": "x\n"}, "work on every system"),
            ({long_name: "x\n"}, "within 120 characters"),
            ({"starters/orphan/README.md": "x\n"}, "no starter card names this template"),
            ({"starters/README.md": "x\n"}, "holds only template folders"),
            ({"cards/starters/team.md": card({**STARTER, "template": "starters/gone/"}, "")},
             "no template folder starters/gone/"),
        ]
        for change, fragment in cases:
            with self.subTest(fragment=fragment, change=list(change)):
                hub = self.hub(with_starter())
                hub.write(change)
                self.assertRefused(hub, fragment)

    def test_names_that_differ_only_by_case_are_refused(self) -> None:
        hub = self.hub(with_starter())
        if (hub.root / "starters/team/shared/TASKS").exists():
            self.skipTest("this filesystem ignores case")
        hub.write({"starters/team/shared/Tasks/T-9.md": "x\n"})
        self.assertRefused(hub, "differ only by case")

    @unittest.skipIf(os.name == "nt", "Windows has no executable bit")
    def test_executables_are_refused(self) -> None:
        hub = self.hub(with_starter())
        (hub.root / "starters/team/shared/tasks/T-1.md").chmod(0o755)
        self.assertRefused(hub, "executables are refused")


class CommandLineTests(HubCase):
    def test_refusal_lists_problems_without_a_traceback(self) -> None:
        hub = self.hub()
        hub.write({"cards/hives/model.md": card({**HIVE, "color": "blue"})})
        result = subprocess.run([sys.executable, "-B", str(BUILDER), "--root", str(hub.root)],
                                capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 1)
        self.assertIn("cards/hives/model.md: unknown field(s): color", result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertFalse((hub.root / "views").exists())


if __name__ == "__main__":
    unittest.main()
