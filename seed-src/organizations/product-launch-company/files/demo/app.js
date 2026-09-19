(function () {
  "use strict";
  const core = window.AgendaCore;
  const byId = id => document.getElementById(id);
  const form = byId("agenda-form");
  const list = byId("topic-list");
  const exportButton = byId("export-plan");
  let currentResult = null;
  let classification = "SYNTHETIC";
  let nextId = 1;

  function element(tag, content, className) {
    const node = document.createElement(tag);
    if (content !== undefined) node.textContent = content;
    if (className) node.className = className;
    return node;
  }

  function clearError() {
    byId("error-summary").hidden = true;
    byId("error-summary").textContent = "";
  }

  function showError(error) {
    const box = byId("error-summary");
    box.textContent = error.message || "The agenda could not be read.";
    box.hidden = false;
    box.focus();
  }

  function invalidate() {
    currentResult = null;
    exportButton.disabled = true;
    byId("result-status").textContent = "Inputs changed. Build again before exporting.";
    byId("result-status").className = "";
    byId("result").replaceChildren();
    clearError();
  }

  function addTopic(topic) {
    const row = element("li", undefined, "topic-editor");
    row.dataset.id = topic.id;
    const fields = element("div", undefined, "topic-fields");
    const labelBox = element("div");
    const label = element("label", "Topic label");
    const labelInput = element("input");
    labelInput.type = "text";
    labelInput.maxLength = 120;
    labelInput.required = true;
    labelInput.value = topic.label;
    labelInput.dataset.field = "label";
    labelInput.id = `label-${topic.id}`;
    label.htmlFor = labelInput.id;
    labelBox.append(label, labelInput);
    const minuteBox = element("div");
    const minuteLabel = element("label", "Minutes");
    const minutes = element("input");
    minutes.type = "number";
    minutes.min = "1";
    minutes.max = "120";
    minutes.step = "1";
    minutes.required = true;
    minutes.value = String(topic.minutes);
    minutes.dataset.field = "minutes";
    minutes.id = `minutes-${topic.id}`;
    minuteLabel.htmlFor = minutes.id;
    minuteBox.append(minuteLabel, minutes);
    fields.append(labelBox, minuteBox);
    const controls = element("div", undefined, "topic-controls");
    const requiredLabel = element("label");
    const required = element("input");
    required.type = "checkbox";
    required.checked = topic.required;
    required.dataset.field = "required";
    requiredLabel.append(required, document.createTextNode(" Required topic"));
    const remove = element("button", "Remove topic", "secondary remove");
    remove.type = "button";
    remove.addEventListener("click", () => {
      row.remove();
      invalidate();
      byId("add-topic").focus();
    });
    controls.append(requiredLabel, remove);
    row.append(fields, controls);
    list.append(row);
  }

  function readInput() {
    return {
      classification,
      title: byId("agenda-title").value,
      start: byId("start").value,
      duration_minutes: Number(byId("duration").value),
      wrap_minutes: Number(byId("wrap").value),
      topics: Array.from(list.querySelectorAll(".topic-editor"), row => ({
        id: row.dataset.id,
        label: row.querySelector('[data-field="label"]').value,
        minutes: Number(row.querySelector('[data-field="minutes"]').value),
        required: row.querySelector('[data-field="required"]').checked
      }))
    };
  }

  function populate(input) {
    const checked = core.validate(input);
    classification = checked.classification;
    byId("classification").textContent = `Input classification: ${classification}. Imported text is never evaluated as markup.`;
    byId("agenda-title").value = checked.title;
    byId("start").value = checked.start;
    byId("duration").value = String(checked.duration_minutes);
    byId("wrap").value = String(checked.wrap_minutes);
    list.replaceChildren();
    checked.topics.forEach(addTopic);
    invalidate();
  }

  function render(result) {
    const area = byId("result");
    const status = byId("result-status");
    area.replaceChildren();
    status.className = result.status;
    status.textContent = result.status === "blocked"
      ? `Blocked: required topics exceed available topic time by ${result.required_overrun_minutes} minute(s). Nothing is scheduled.`
      : `Ready to review: ${result.scheduled_minutes} topic minutes within a ${result.session_minutes}-minute session. This is a plan, not an outcome.`;
    area.append(element("p", `Required: ${result.required_minutes} minutes.`, "metric"));
    if (result.status === "ready") {
      area.append(element("p", `Slack before wrap/end: ${result.slack_minutes} minutes.`, "metric"));
      const wrapper = element("div", undefined, "table-wrap");
      const table = element("table");
      table.append(element("caption", `${result.title} · ${result.start}–${result.end}`));
      const head = element("thead");
      const headRow = element("tr");
      ["Topic", "Start", "End", "Minutes", "Kind"].forEach(value => {
        const cell = element("th", value);
        cell.scope = "col";
        headRow.append(cell);
      });
      head.append(headRow);
      const body = element("tbody");
      const rows = result.scheduled.map(topic => [topic.label, topic.start, topic.end, topic.minutes, topic.required ? "Required" : "Optional"]);
      if (result.wrap) rows.push(["Reserved wrap", result.wrap.start, result.wrap.end, result.wrap.minutes, "Wrap"]);
      rows.forEach(values => {
        const row = element("tr");
        values.forEach(value => row.append(element("td", String(value))));
        body.append(row);
      });
      table.append(head, body);
      wrapper.append(table);
      area.append(wrapper);
    }
    area.append(element("h3", "Not scheduled"));
    if (!result.parked.length) area.append(element("p", "Every topic fits."));
    else {
      const parked = element("ul", undefined, "parked-list");
      result.parked.forEach(topic => parked.append(element("li", `${topic.label} (${topic.minutes} min; ${topic.required ? "required" : "optional"}). ${topic.reason}`)));
      area.append(parked);
    }
    currentResult = result;
    exportButton.disabled = false;
  }

  form.addEventListener("input", invalidate);
  form.addEventListener("change", invalidate);
  form.addEventListener("submit", event => {
    event.preventDefault();
    invalidate();
    try {
      render(core.planAgenda(readInput()));
    } catch (error) {
      showError(error);
    }
  });
  byId("load-sample").addEventListener("click", () => {
    populate(core.sample);
    render(core.planAgenda(readInput()));
  });
  byId("add-topic").addEventListener("click", () => {
    if (list.children.length >= 50) {
      showError(new Error("The reference supports at most 50 topics."));
      return;
    }
    const existing = new Set(Array.from(list.children, row => row.dataset.id));
    while (existing.has(`topic-${nextId}`)) nextId += 1;
    addTopic({ id: `topic-${nextId++}`, label: "New topic", minutes: 5, required: false });
    invalidate();
    list.lastElementChild.querySelector("input").focus();
  });
  byId("import-file").addEventListener("change", async event => {
    const file = event.target.files[0];
    if (!file) return;
    try {
      if (file.size > 65_536) throw new Error("Import is limited to 64 KiB.");
      const input = JSON.parse(await file.text());
      const result = core.planAgenda(input);
      populate(input);
      render(result);
    } catch (error) {
      showError(error);
    } finally {
      event.target.value = "";
    }
  });
  exportButton.addEventListener("click", () => {
    if (!currentResult) return;
    const blob = new Blob([JSON.stringify(currentResult, null, 2) + "\n"], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = element("a");
    link.href = url;
    link.download = "agenda-pocket-plan.json";
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
  populate(core.sample);
  render(core.planAgenda(readInput()));
})();
