(function (root) {
  "use strict";
  const levels = [
    {name: "Loading Lane", rows: ["#########", "#D..#..o#", "#.#.#.#.#", "#...~...#", "#.#.#.#.#", "#o..#..o#", "#########"]},
    {name: "Greenhouse Loop", rows: ["#########", "#D..#..o#", "#.#.~.#.#", "#o#.#...#", "#.#.~.#.#", "#...#..o#", "#########"]},
    {name: "Evening Annex", rows: ["#########", "#o..#..o#", "#.#.~.#.#", "#...#...#", "###.~.###", "#D..#..o#", "#########"]}
  ];
  const directions = {up: [0, -1], down: [0, 1], left: [-1, 0], right: [1, 0]};
  const events = {
    start: "Your shift begins with one glow cell.",
    moved: "Moved.",
    wait: "Waited one beat.",
    blocked: "Blocked. No beat spent; try another direction or wait.",
    loaded: "Reloaded at the depot.",
    delivered: "Beacon lit! Return to D for another cell.",
    won: "All three greenhouses are lit. Shift complete!",
    undo: "Last successful action undone."
  };
  function bridgeOpen(state) { return state.turn % 4 < 2; }
  function keyAction(key) {
    const keys = {arrowup: "up", w: "up", arrowdown: "down", s: "down", arrowleft: "left", a: "left", arrowright: "right", d: "right", " ": "wait", u: "undo", backspace: "undo", r: "restart"};
    return keys[String(key).toLowerCase()] || null;
  }
  function createState(levelIndex = 0) {
    if (!Number.isInteger(levelIndex) || levelIndex < 0 || levelIndex >= levels.length) throw new RangeError("Unknown board");
    const rows = levels[levelIndex].rows;
    const y = rows.findIndex(row => row.includes("D"));
    return {levelIndex, x: rows[y].indexOf("D"), y, turn: 0, carrying: true, delivered: [], won: false, lastEvent: "start"};
  }
  function advance(state, action) {
    if (state.won || (!directions[action] && action !== "wait")) return state;
    const rows = levels[state.levelIndex].rows;
    const [dx, dy] = directions[action] || [0, 0];
    const x = state.x + dx, y = state.y + dy;
    const tile = rows[y] && rows[y][x];
    if (!tile || tile === "#" || (action !== "wait" && tile === "~" && !bridgeOpen(state))) {
      return {...state, lastEvent: "blocked"};
    }
    const next = {...state, x, y, turn: state.turn + 1, delivered: [...state.delivered], lastEvent: action === "wait" ? "wait" : "moved"};
    if (tile === "D" && !next.carrying) {
      next.carrying = true;
      next.lastEvent = "loaded";
    }
    const target = `${x},${y}`;
    if (tile === "o" && next.carrying && !next.delivered.includes(target)) {
      next.delivered.push(target);
      next.delivered.sort();
      next.carrying = false;
      next.lastEvent = "delivered";
    }
    const targetCount = rows.join("").split("o").length - 1;
    if (next.delivered.length === targetCount) {
      next.won = true;
      next.lastEvent = "won";
    }
    return next;
  }
  function createController(levelIndex = 0) {
    let state = createState(levelIndex), history = [];
    return {
      get state() { return state; },
      get undoCount() { return history.length; },
      setLevel(index) { state = createState(index); history = []; return state; },
      act(action) {
        if (action === "restart") { state = createState(state.levelIndex); history = []; }
        else if (action === "undo") {
          if (history.length) state = {...history.pop(), lastEvent: "undo"};
        } else {
          const next = advance(state, action);
          if (next.turn !== state.turn) {
            history.push(state);
            if (history.length > 256) history.shift();
          }
          state = next;
        }
        return state;
      }
    };
  }
  function summary(state) {
    return `${events[state.lastEvent]} Position row ${state.y + 1}, column ${state.x + 1}. ${state.delivered.length}/3 beacons lit. ${state.carrying ? "Carrying one cell" : "Empty; reload at D"}. ${state.turn} actions. Next action: beat ${state.turn % 4 + 1}/4, bridge ${bridgeOpen(state) ? "OPEN =" : "CLOSED ×"}.`;
  }
  function mount(doc) {
    const board = doc.getElementById("board");
    const status = doc.getElementById("status");
    const selector = doc.getElementById("level");
    const sound = doc.getElementById("sound");
    const controller = createController();
    let audioContext;
    function tone(event) {
      if (!sound.checked) return;
      const Audio = doc.defaultView.AudioContext || doc.defaultView.webkitAudioContext;
      if (!Audio) return;
      try {
        audioContext = audioContext || new Audio();
        if (audioContext.state === "suspended") audioContext.resume().catch(() => {});
        const frequencies = {blocked: 150, loaded: 440, delivered: 660, won: 880};
        if (!frequencies[event]) return;
        const oscillator = audioContext.createOscillator(), gain = audioContext.createGain();
        oscillator.frequency.value = frequencies[event];
        gain.gain.setValueAtTime(0.03, audioContext.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.001, audioContext.currentTime + 0.12);
        oscillator.connect(gain); gain.connect(audioContext.destination);
        oscillator.start(); oscillator.stop(audioContext.currentTime + 0.13);
      } catch (_) { /* Audio is optional; gameplay and text remain available. */ }
    }
    function render() {
      const state = controller.state, fragment = doc.createDocumentFragment();
      levels[state.levelIndex].rows.forEach((row, y) => Array.from(row).forEach((tile, x) => {
        const cell = doc.createElement("span");
        const delivered = state.delivered.includes(`${x},${y}`);
        const names = {"#": "wall", ".": "path", D: "depot", o: delivered ? "lit beacon" : "unlit beacon", "~": bridgeOpen(state) ? "open bridge" : "closed bridge"};
        cell.className = "tile";
        if (tile === "#") cell.classList.add("wall");
        if (tile === "D") cell.classList.add("depot");
        if (tile === "o") cell.classList.add(delivered ? "delivered" : "target");
        if (tile === "~") {
          cell.classList.add("bridge");
          if (!bridgeOpen(state)) cell.classList.add("closed");
        }
        const player = state.x === x && state.y === y;
        if (player) cell.classList.add("player");
        cell.textContent = {"#": "·", ".": "", D: "D", o: delivered ? "★" : "○", "~": bridgeOpen(state) ? "=" : "×"}[tile];
        cell.setAttribute("aria-label", `Row ${y + 1}, column ${x + 1}: ${names[tile]}${player ? ", courier here" : ""}`);
        fragment.appendChild(cell);
      }));
      board.replaceChildren(fragment);
      status.textContent = summary(state);
    }
    function act(action) {
      const before = controller.state;
      controller.act(action);
      if (controller.state !== before) tone(controller.state.lastEvent);
      render();
    }
    levels.forEach((level, index) => {
      const option = doc.createElement("option");
      option.value = String(index); option.textContent = `${index + 1}. ${level.name}`;
      selector.appendChild(option);
    });
    selector.addEventListener("change", () => { controller.setLevel(Number(selector.value)); render(); board.focus(); });
    doc.getElementById("focus").addEventListener("click", () => board.focus());
    board.addEventListener("keydown", event => {
      const action = keyAction(event.key);
      if (!action || event.altKey || event.ctrlKey || event.metaKey) return;
      event.preventDefault();
      if (!event.repeat) act(action);
    });
    doc.querySelectorAll("[data-action]").forEach(button => button.addEventListener("click", () => { act(button.dataset.action); board.focus(); }));
    render();
    return controller;
  }
  const api = {levels, bridgeOpen, keyAction, createState, advance, createController, summary, mount};
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.MosslightCourier = api;
  if (root.document) root.addEventListener("DOMContentLoaded", () => mount(root.document));
}(typeof globalThis === "object" ? globalThis : this));
