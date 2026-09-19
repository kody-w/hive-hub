"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const root = path.resolve(__dirname, "..");
const sample = JSON.parse(fs.readFileSync(path.join(root, "data/sample-agenda.json"), "utf8"));
const cases = JSON.parse(fs.readFileSync(path.join(root, "data/acceptance-cases.json"), "utf8")).cases;
const clone = value => JSON.parse(JSON.stringify(value));
// Exercise the browser script independently of any enclosing package's module type.
const browser = {};
vm.runInNewContext(fs.readFileSync(path.join(root, "demo/core.js"), "utf8"), browser, { timeout: 1000 });
const core = {
  sample: clone(browser.AgendaCore.sample),
  planAgenda: input => clone(browser.AgendaCore.planAgenda(input))
};

for (const fixture of cases) {
  test(`numerical case: ${fixture.id}`, () => {
    const input = Object.assign(clone(sample), fixture.patch);
    if (fixture.all_required) input.topics.forEach(topic => { topic.required = true; });
    const result = core.planAgenda(input);
    assert.deepEqual({
      status: result.status,
      scheduled_minutes: result.scheduled_minutes,
      slack_minutes: result.slack_minutes,
      required_overrun_minutes: result.required_overrun_minutes,
      scheduled_ids: result.scheduled.map(topic => topic.id),
      parked_ids: result.parked.map(topic => topic.id),
      wrap_start: result.wrap ? result.wrap.start : null
    }, fixture.expected);
    if (result.status === "ready") {
      assert.equal(result.scheduled_minutes + result.slack_minutes + input.wrap_minutes, input.duration_minutes);
      assert.deepEqual(result.scheduled.filter(topic => topic.required).map(topic => topic.id), input.topics.filter(topic => topic.required).map(topic => topic.id));
    }
  });
}

test("embedded offline sample equals structured source", () => assert.deepEqual(core.sample, sample));
test("planning is deterministic and does not mutate inputs", () => {
  const input = clone(sample);
  const before = JSON.stringify(input);
  assert.deepEqual(core.planAgenda(input), core.planAgenda(input));
  assert.equal(JSON.stringify(input), before);
});
test("reject duplicate IDs", () => {
  const input = clone(sample);
  input.topics[1].id = input.topics[0].id;
  assert.throws(() => core.planAgenda(input), /Duplicate topic ID/);
});
test("reject invalid minute and boolean types", () => {
  for (const value of [0, -1, 1.5, "5", null, Infinity]) {
    const input = clone(sample);
    input.topics[0].minutes = value;
    assert.throws(() => core.planAgenda(input), /whole number/);
  }
  const input = clone(sample);
  input.topics[0].required = "true";
  assert.throws(() => core.planAgenda(input), /true or false/);
});
test("validate top-level objects and topic bounds", () => {
  for (const value of [null, [], "agenda", {}]) assert.throws(() => core.planAgenda(value));
  const input = clone(sample);
  input.topics = [];
  assert.throws(() => core.planAgenda(input), /1 to 50/);
  input.topics = Array.from({ length: 51 }, (_, index) => ({ id: `topic-${index}`, label: "SYNTHETIC", minutes: 1, required: false }));
  assert.throws(() => core.planAgenda(input), /1 to 50/);
});
test("reject crossing midnight and malformed clock", () => {
  assert.throws(() => core.planAgenda({ ...clone(sample), start: "23:01" }), /midnight/);
  for (const start of ["24:00", "9:00", "09:60", "not-time"]) {
    assert.throws(() => core.planAgenda({ ...clone(sample), start }), /HH:MM/);
  }
  assert.equal(core.planAgenda({ ...clone(sample), start: "23:00" }).end, "24:00");
});
test("optional-only agenda may reserve the whole session for wrap", () => {
  const input = clone(sample);
  input.topics.forEach(topic => { topic.required = false; });
  input.wrap_minutes = input.duration_minutes;
  const result = core.planAgenda(input);
  assert.equal(result.status, "ready");
  assert.equal(result.scheduled.length, 0);
  assert.equal(result.wrap.minutes, 60);
});
test("literal angle-bracket text is kept as text in the core", () => {
  const input = clone(sample);
  input.topics[0].label = "<b>SYNTHETIC label</b>";
  assert.equal(core.planAgenda(input).scheduled[0].label, input.topics[0].label);
});
test("all browser assets are relative and present", () => {
  const html = fs.readFileSync(path.join(root, "demo/index.html"), "utf8");
  const assets = [...html.matchAll(/(?:src|href)="([^"]+)"/g)].map(match => match[1]).filter(value => !value.startsWith("#"));
  assert.deepEqual(assets, ["styles.css", "core.js", "app.js"]);
  for (const asset of assets) assert.ok(fs.statSync(path.join(root, "demo", asset)).isFile());
  assert.ok(html.indexOf('src="core.js"') < html.indexOf('src="app.js"'));
});
test("UI uses literal text and no application network or persistence API", () => {
  const app = fs.readFileSync(path.join(root, "demo/app.js"), "utf8");
  assert.ok(app.includes("node.textContent = content"));
  assert.doesNotMatch(app, /innerHTML|outerHTML|insertAdjacentHTML|\beval\s*\(|new\s+Function|fetch\s*\(|XMLHttpRequest|WebSocket|localStorage|sessionStorage/);
  assert.ok(app.includes("exportButton.disabled = true"));
  assert.ok(app.includes("core.planAgenda(input)"));
});
