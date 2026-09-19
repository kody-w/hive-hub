(function (root, factory) {
  "use strict";
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.AgendaCore = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const sample = {
    classification: "SYNTHETIC",
    title: "Library kit planning reference",
    start: "09:00",
    duration_minutes: 60,
    wrap_minutes: 5,
    topics: [
      { id: "welcome", label: "Confirm the decision to make", minutes: 5, required: true },
      { id: "stock-review", label: "Review fictional kit stock", minutes: 10, required: false },
      { id: "decision", label: "Choose the sample kit scope", minutes: 20, required: true },
      { id: "template-demo", label: "Optional template demonstration", minutes: 15, required: false },
      { id: "risk-check", label: "Check assumptions and open questions", minutes: 10, required: true },
      { id: "roundup", label: "Collect optional follow-up ideas", minutes: 8, required: false }
    ]
  };

  function whole(value, low, high, label) {
    if (!Number.isInteger(value) || value < low || value > high) {
      throw new Error(`${label} must be a whole number from ${low} to ${high}.`);
    }
    return value;
  }

  function text(value, label, limit) {
    if (typeof value !== "string" || !value.trim() || value.length > limit) {
      throw new Error(`${label} must be nonempty text of at most ${limit} characters.`);
    }
    return value.trim();
  }

  function validate(input) {
    if (!input || typeof input !== "object" || Array.isArray(input)) throw new Error("An agenda must be a JSON object.");
    const title = text(input.title, "Title", 120);
    if (typeof input.start !== "string" || !/^([01][0-9]|2[0-3]):[0-5][0-9]$/.test(input.start)) {
      throw new Error("Start must be a same-day HH:MM time.");
    }
    const duration = whole(input.duration_minutes, 1, 480, "Session minutes");
    const wrap = whole(input.wrap_minutes, 0, duration, "Wrap minutes");
    const startMinutes = Number(input.start.slice(0, 2)) * 60 + Number(input.start.slice(3));
    if (startMinutes + duration > 1440) throw new Error("The session must end no later than midnight.");
    if (!Array.isArray(input.topics) || input.topics.length < 1 || input.topics.length > 50) {
      throw new Error("Supply 1 to 50 topics.");
    }
    const seen = new Set();
    const topics = input.topics.map((topic, index) => {
      if (!topic || typeof topic !== "object" || Array.isArray(topic)) throw new Error(`Topic ${index + 1} must be an object.`);
      if (typeof topic.id !== "string" || topic.id.length > 40 || !/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(topic.id)) {
        throw new Error(`Topic ${index + 1} needs a lowercase-hyphenated ID of at most 40 characters.`);
      }
      if (seen.has(topic.id)) throw new Error(`Duplicate topic ID: ${topic.id}.`);
      seen.add(topic.id);
      if (typeof topic.required !== "boolean") throw new Error(`Topic ${index + 1} required must be true or false.`);
      return {
        id: topic.id, label: text(topic.label, `Topic ${index + 1} label`, 120),
        minutes: whole(topic.minutes, 1, 120, `Topic ${index + 1} minutes`),
        required: topic.required
      };
    });
    return {
      classification: input.classification === undefined ? "LOCAL-INPUT" : text(input.classification, "Classification", 80),
      title, start: input.start, startMinutes, duration_minutes: duration, wrap_minutes: wrap, topics
    };
  }

  function clock(minutes) {
    return `${String(Math.floor(minutes / 60)).padStart(2, "0")}:${String(minutes % 60).padStart(2, "0")}`;
  }

  function planAgenda(input) {
    const agenda = validate(input);
    const budget = agenda.duration_minutes - agenda.wrap_minutes;
    const requiredMinutes = agenda.topics.filter(topic => topic.required).reduce((sum, topic) => sum + topic.minutes, 0);
    const result = {
      classification: agenda.classification,
      artifact_kind: "offline-reference-plan-not-a-meeting-outcome",
      title: agenda.title,
      status: requiredMinutes > budget ? "blocked" : "ready",
      start: agenda.start,
      end: clock(agenda.startMinutes + agenda.duration_minutes),
      session_minutes: agenda.duration_minutes,
      required_minutes: requiredMinutes,
      required_overrun_minutes: Math.max(0, requiredMinutes - budget),
      scheduled_minutes: 0,
      slack_minutes: null,
      scheduled: [],
      parked: [],
      wrap: null
    };
    if (result.status === "blocked") {
      result.parked = agenda.topics.map(topic => ({ ...topic, reason: "Session blocked until all required topics fit." }));
      return result;
    }
    let used = 0;
    let remainingRequired = requiredMinutes;
    for (const topic of agenda.topics) {
      if (topic.required || used + topic.minutes + remainingRequired <= budget) {
        const start = agenda.startMinutes + used;
        result.scheduled.push({ ...topic, start: clock(start), end: clock(start + topic.minutes) });
        used += topic.minutes;
        if (topic.required) remainingRequired -= topic.minutes;
      } else {
        result.parked.push({ ...topic, reason: "Optional topic does not fit after reserving required time and wrap." });
      }
    }
    result.scheduled_minutes = used;
    result.slack_minutes = budget - used;
    if (agenda.wrap_minutes > 0) {
      result.wrap = {
        start: clock(agenda.startMinutes + budget),
        end: result.end,
        minutes: agenda.wrap_minutes
      };
    }
    return result;
  }

  return Object.freeze({ sample, validate, planAgenda });
});
