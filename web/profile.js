"use strict";

const profileContainer = document.querySelector("#profile-details");
const profileSections = new Map();
let profileReaders = {};
const recordSeeds = {
  academic_history: {degree: "", completed: null},
  courses: {name: "", completed: null},
  projects: {name: "", description: ""}, research: {name: "", description: ""},
  work: {description: "", months: null}, tests: {test: "", score: null, taken: null},
};

// Typed controls retain existing nested values, booleans, numbers and unknowns.
function detailEditor(value, label) {
  const box = textElement("div", "", "detail-editor");
  const title = textElement("label", label, "field");
  const type = document.createElement("select");
  type.setAttribute("aria-label", `${label} value type`);
  for (const [key, name] of [["null", "Unknown"], ["string", "Text"], ["number", "Number"],
    ["boolean", "Yes / no"], ["array", "List"], ["object", "Details"]]) type.add(new Option(name, key));
  type.value = value === null ? "null" : Array.isArray(value) ? "array" : typeof value;
  title.append(type);
  const body = textElement("div", "");
  box.append(title, body);
  let read = () => null;
  function render(current) {
    body.replaceChildren();
    if (type.value === "null") { read = () => null; return; }
    if (["string", "number", "boolean"].includes(type.value)) {
      const control = document.createElement(type.value === "boolean" ? "select" : "input");
      control.setAttribute("aria-label", label);
      if (type.value === "boolean") {
        control.add(new Option("Unknown", ""));
        control.add(new Option("Yes", "true")); control.add(new Option("No", "false"));
      } else control.type = type.value === "number" ? "number" : "text";
      if (type.value === "number") control.step = "any";
      control.value = current === null ? "" : String(current);
      control.addEventListener("input", invalidateConfirmation);
      control.addEventListener("change", invalidateConfirmation);
      read = () => type.value === "string" ? control.value : control.value === "" ? null :
        type.value === "boolean" ? control.value === "true" : Number(control.value);
      body.append(control);
      return;
    }
    const rows = [];
    const list = type.value === "array";
    function add(key, entry) {
      const row = textElement("div", "", "detail-row");
      const editor = detailEditor(entry, list ? "Item" : key);
      const remove = textElement("button", "Remove", "secondary"); remove.type = "button";
      const item = {key, editor, removed: false};
      remove.addEventListener("click", () => { item.removed = true; row.remove(); invalidateConfirmation(); });
      row.append(editor.element, remove); body.append(row); rows.push(item);
    }
    for (const [key, entry] of Object.entries(current || {})) add(key, entry);
    const addButton = textElement("button", list ? "Add item" : "Add detail", "secondary"); addButton.type = "button";
    const name = document.createElement("input");
    name.placeholder = "Detail name"; name.setAttribute("aria-label", `${label} new detail name`);
    if (!list) body.append(name);
    addButton.addEventListener("click", () => {
      const key = list ? String(rows.length) : name.value.trim();
      if (!key || rows.some(row => !row.removed && row.key === key)) return;
      add(key, ""); name.value = ""; invalidateConfirmation();
    });
    body.append(addButton);
    read = () => list ? rows.filter(row => !row.removed).map(row => row.editor.read()) :
      Object.fromEntries(rows.filter(row => !row.removed).map(row => [row.key, row.editor.read()]));
  }
  type.addEventListener("change", () => {
    render(type.value === "array" ? [] : type.value === "object" ? {} : null);
    invalidateConfirmation();
  });
  render(value);
  return {element: box, read: () => read()};
}

function renderProfileDetails(profile) {
  profileContainer.replaceChildren(); profileSections.clear(); profileReaders = {};
  for (const [key, value] of Object.entries(profile)) {
    if (key === "evidence") continue;
    const section = textElement("details", "", "profile-section");
    section.append(textElement("summary", sentenceCase(key)));
    profileSections.set(key, section); profileContainer.append(section);
    if (recordSeeds[key]) {
      const rows = [];
      const holder = textElement("div", ""); section.append(holder);
      function add(record) {
        const row = textElement("div", "", "profile-record");
        const editor = detailEditor(record, sentenceCase(key) + " record");
        const item = {editor, removed: false}; rows.push(item);
        const remove = textElement("button", "Remove record", "secondary"); remove.type = "button";
        remove.addEventListener("click", () => { item.removed = true; row.remove(); invalidateConfirmation(); });
        row.append(editor.element, remove); holder.append(row);
      }
      value.forEach(add);
      const button = textElement("button", "Add record", "secondary"); button.type = "button";
      button.addEventListener("click", () => { add(recordSeeds[key]); invalidateConfirmation(); });
      section.append(button);
      profileReaders[key] = () => rows.filter(row => !row.removed).map(row => row.editor.read());
    } else {
      const label = textElement("label", key === "normalized_gpa" ?
        "Normalized GPA (leave blank if unknown; no automatic conversion)" :
        ["skills", "goals", "constraints"].includes(key) ? "One item per line; blank means unknown" : "Leave blank if unknown", "field");
      const lines = Array.isArray(value);
      const input = document.createElement(lines ? "textarea" : "input");
      input.setAttribute("aria-label", sentenceCase(key));
      if (key === "normalized_gpa") { input.type = "number"; input.step = "any"; input.min = "0"; }
      input.value = lines ? value.join("\n") : String(value ?? "");
      input.addEventListener("input", invalidateConfirmation);
      label.append(input); section.append(label);
      profileReaders[key] = () => lines ? input.value.split("\n").map(v => v.trim()).filter(Boolean) :
        input.value.trim() || null;
    }
  }
}
function collectProfileDetails() {
  return Object.fromEntries(Object.entries(profileReaders).map(([key, read]) => [key, read()]));
}
