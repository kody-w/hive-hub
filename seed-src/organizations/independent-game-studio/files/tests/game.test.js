"use strict";
(async function main() {
const assert = (await import("node:assert/strict")).default;
const fs = await import("node:fs");
const path = await import("node:path");
const vm = await import("node:vm");
const testDirectory = path.dirname(path.resolve(process.argv[1]));
const source = fs.readFileSync(path.join(testDirectory, "../game/game.js"), "utf8");
const authoredModule = {exports: {}};
vm.compileFunction(source, ["module"])(authoredModule);
const game = authoredModule.exports;
let checks = 0;
function test(name, fn) { fn(); checks += 1; console.log(`PASS ${name}`); }
function solve(levelIndex) {
  const start = game.createState(levelIndex), queue = [{state: start, path: []}];
  const key = s => [s.x, s.y, s.turn % 4, Number(s.carrying), s.delivered.join(";")].join("|");
  const seen = new Set([key(start)]);
  for (let head = 0; head < queue.length; head += 1) {
    const current = queue[head];
    if (current.state.won) return current.path;
    for (const action of ["up", "down", "left", "right", "wait"]) {
      const state = game.advance(current.state, action), id = key(state);
      if (seen.has(id)) continue;
      seen.add(id); queue.push({state, path: current.path.concat(action)});
    }
  }
  throw new Error(`Unsolvable board ${levelIndex}`);
}
test("fixed maps have one depot, three targets, and valid dimensions", () => {
  game.levels.forEach(level => {
    assert.equal(level.rows.length, 7);
    level.rows.forEach(row => { assert.equal(row.length, 9); assert.match(row, /^[#.Do~]+$/); });
    assert.equal(level.rows.join("").split("D").length - 1, 1);
    assert.equal(level.rows.join("").split("o").length - 1, 3);
  });
});
test("wall collisions and unknown actions do not spend a beat", () => {
  const start = game.createState();
  assert.equal(game.advance(start, "left").turn, 0);
  assert.equal(game.advance(start, "left").x, start.x);
  assert.equal(game.advance(start, "not-an-action"), start);
});
test("bridge gate checks the pre-action phase", () => {
  const state = {...game.createState(), x: 3, y: 3, turn: 2};
  assert.equal(game.advance(state, "right").x, 3);
  const entered = game.advance({...state, turn: 1}, "right");
  assert.equal(entered.x, 4); assert.equal(entered.turn, 2);
  assert.equal(game.bridgeOpen(entered), false);
  assert.equal(game.advance(entered, "right").x, 5);
});
test("waiting cycles the phase and keeps position", () => {
  let state = game.createState();
  for (let i = 0; i < 4; i += 1) state = game.advance(state, "wait");
  assert.equal(state.x, 1); assert.equal(state.y, 1);
  assert.equal(state.turn, 4); assert.equal(game.bridgeOpen(state), true);
});
test("depot reload and delivery are single-capacity and immutable", () => {
  const empty = {...game.createState(), x: 2, carrying: false};
  assert.equal(game.advance(empty, "left").carrying, true);
  assert.equal(empty.carrying, false);
  const near = {...game.createState(), x: 1, y: 4};
  const delivered = game.advance(near, "down");
  assert.deepEqual(delivered.delivered, ["1,5"]); assert.equal(delivered.carrying, false);
  assert.deepEqual(near.delivered, []);
  assert.deepEqual(game.advance(delivered, "wait").delivered, ["1,5"]);
});
test("keyboard map includes arrows WASD space undo and restart", () => {
  for (const [key, action] of Object.entries({ArrowUp: "up", W: "up", ArrowDown: "down", s: "down", ArrowLeft: "left", a: "left", ArrowRight: "right", d: "right", " ": "wait", U: "undo", Backspace: "undo", R: "restart"})) {
    assert.equal(game.keyAction(key), action);
  }
  assert.equal(game.keyAction("Tab"), null);
});
test("controller resets, bounds history, and does not record blocked moves", () => {
  const controller = game.createController();
  controller.act("left"); assert.equal(controller.undoCount, 0);
  for (let i = 0; i < 270; i += 1) controller.act("wait");
  assert.equal(controller.undoCount, 256);
  controller.act("undo"); assert.equal(controller.state.turn, 269);
  controller.act("restart"); assert.equal(controller.state.turn, 0); assert.equal(controller.undoCount, 0);
  controller.setLevel(2); assert.equal(controller.state.levelIndex, 2);
  assert.throws(() => game.createState(3), RangeError);
});
game.levels.forEach((level, index) => test(`solver, win lock, and undo-win: ${level.name}`, () => {
  const route = solve(index), controller = game.createController(index);
  route.forEach(action => controller.act(action));
  assert.equal(controller.state.won, true);
  assert.equal(controller.state.delivered.length, 3);
  const count = controller.state.turn;
  controller.act("wait"); assert.equal(controller.state.turn, count);
  controller.act("undo"); assert.equal(controller.state.won, false);
  assert.equal(controller.state.delivered.length, 2);
  assert.match(game.summary(controller.state), /Next action: beat/);
  console.log(`  shortest route: ${route.length} actions`);
}));
test("mounted keyboard/click handlers can play all boards using a DOM test double", () => {
  let doc;
  class Element {
    constructor() {
      this.children = []; this.listeners = {}; this.attributes = {};
      this.dataset = {}; this.checked = false; this.value = "";
      this.classList = {add: () => {}};
    }
    appendChild(child) { this.children.push(child); return child; }
    replaceChildren(fragment) { this.children = [...fragment.children]; }
    setAttribute(name, value) { this.attributes[name] = value; }
    addEventListener(type, listener) { this.listeners[type] = listener; }
    focus() { doc.activeElement = this; }
    fire(type, event = {}) { this.listeners[type](event); }
  }
  const ids = Object.fromEntries(["board", "status", "level", "sound", "focus"].map(id => [id, new Element()]));
  const buttons = ["up", "down", "left", "right", "wait", "undo", "restart"].map(action => {
    const element = new Element(); element.dataset.action = action; return element;
  });
  doc = {
    defaultView: {}, activeElement: null,
    getElementById: id => ids[id],
    createElement: () => new Element(),
    createDocumentFragment: () => new Element(),
    querySelectorAll: selector => { assert.equal(selector, "[data-action]"); return buttons; }
  };
  const controller = game.mount(doc);
  assert.equal(ids.board.children.length, 63);
  assert.equal(ids.level.children.length, 3);
  ids.focus.fire("click"); assert.equal(doc.activeElement, ids.board);
  function key(keyName, extras = {}) {
    let prevented = false;
    ids.board.fire("keydown", {key: keyName, repeat: false, altKey: false, ctrlKey: false, metaKey: false, preventDefault: () => { prevented = true; }, ...extras});
    return prevented;
  }
  assert.equal(key("ArrowRight"), true); assert.equal(controller.state.x, 2);
  key("ArrowRight", {repeat: true}); assert.equal(controller.state.turn, 1);
  assert.equal(key("Tab"), false);
  assert.equal(key("r", {ctrlKey: true}), false); assert.equal(controller.state.turn, 1);
  buttons.find(button => button.dataset.action === "left").fire("click");
  assert.equal(controller.state.x, 1); assert.equal(controller.state.turn, 2);
  key("Backspace"); assert.equal(controller.state.x, 2); assert.equal(controller.state.turn, 1);
  const actionKeys = {up: "w", down: "s", left: "a", right: "d", wait: " "};
  game.levels.forEach((_, index) => {
    ids.level.value = String(index); ids.level.fire("change");
    assert.equal(controller.state.levelIndex, index); assert.equal(controller.undoCount, 0);
    solve(index).forEach(action => key(actionKeys[action]));
    assert.equal(controller.state.won, true);
    assert.match(ids.status.textContent, /Shift complete/);
    key("u"); assert.equal(controller.state.won, false);
    key("r"); assert.equal(controller.state.turn, 0); assert.equal(controller.state.delivered.length, 0);
  });
});
test("browser shell binds the real engine and only local assets", () => {
  const html = fs.readFileSync(path.join(testDirectory, "../game/index.html"), "utf8");
  assert.match(html, /script defer src="game\.js"/);
  assert.match(html, /id="board" tabindex="0"/);
  assert.match(html, /connect-src 'none'/);
  for (const match of html.matchAll(/(?:src|href)="([^"]+)"/g)) {
    assert.equal(/^(?:https?:)?\/\//.test(match[1]), false);
    assert.equal(fs.existsSync(path.resolve(testDirectory, "../game", match[1])), true);
  }
  assert.equal(/\b(?:fetch|XMLHttpRequest|WebSocket|localStorage|sessionStorage)\b/.test(source), false);
});
console.log(`${checks} game checks passed. Manual browser and player tests are not implied.`);
}()).catch(error => { console.error(error); process.exitCode = 1; });
