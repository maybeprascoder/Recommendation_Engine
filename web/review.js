"use strict";
const reviewForm = document.querySelector("#review-form");
const reviewItems = document.querySelector("#review-items");
const consent = document.querySelector("#evidence-consent");
const confirmButton = document.querySelector("#confirm-button");
const confirmationStatus = document.querySelector("#confirmation-status");
let reviewDraft = null;
let editors = [];

function invalidateConfirmation() {
  lastSelection = null;
  consent.checked = false;
  confirmButton.disabled = true;
  rescoreButton.disabled = true;
  results.hidden = true;
  document.querySelector("#followup-panel").hidden = true;
  confirmationStatus.textContent = "Changes require a new confirmation.";
  statusText.textContent = "Review and confirm the current evidence before scoring.";
}
for (const picker of [profilePicker, programPicker]) {
  picker.addEventListener("change", () => {
    invalidateConfirmation();
    reviewDraft = null;
    reviewForm.hidden = true;
  });
}
consent.addEventListener("change", () => {
  confirmButton.disabled = !consent.checked || !reviewDraft;
  if (!consent.checked) {
    lastSelection = null;
    rescoreButton.disabled = true;
    results.hidden = true;
    document.querySelector("#followup-panel").hidden = true;
  }
});
async function postReview(endpoint, body) {
  const response = await fetch(endpoint, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error?.stderr || payload.error?.message ||
    (typeof payload.detail === "string" ? payload.detail : "Review data was rejected."));
  return payload;
}
async function startReview(selection) {
  invalidateConfirmation();
  reviewDraft = null;
  reviewForm.hidden = true;
  hideError();
  setBusy(true);
  try {
    reviewDraft = await postReview("/review", selection);
    document.querySelector("#active-question").hidden = true;
    renderProfileDetails(reviewDraft.profile);
    renderReview(reviewDraft.profile.evidence);
    reviewForm.hidden = false;
    confirmationStatus.textContent = "Review every item before confirming.";
    statusText.textContent = "Evidence loaded. Review and confirm below.";
  } catch (error) {
    showError("Could not load evidence for review.", error.message);
  } finally { setBusy(false); }
}
function renderReview(evidence) {
  reviewItems.replaceChildren();
  editors = [];
  if (!evidence.length) reviewItems.append(textElement("p",
    "This profile contains no evidence items. Confirmation will not fill in missing information."));
  for (const item of evidence) {
    const card = textElement("fieldset", "", "evidence-editor");
    card.append(textElement("legend", `Evidence: ${item.id}`));
    const original = reviewDraft.profile.evidence.find((evidence) => evidence.id === item.id);
    card.append(textElement("p", original ? `Original claim: ${original.raw_text}` : "New student-supplied evidence; not document-verified.", "source-span"));
    card.append(textElement("p", `Original source: ${item.source || "No source provided"}`, "source-span"));
    card.append(textElement("p", `Extraction confidence: ${sentenceCase(item.extraction_confidence)}. Student confirmation does not increase this.`, "item-meta"));
    const controls = {};
    function field(key, label, type = "text", values = null) {
      const wrapper = textElement("label", label, "field");
      const control = document.createElement(values ? "select" : type === "textarea" ? "textarea" : "input");
      if (values) {
        for (const value of values) control.add(new Option(sentenceCase(value), value));
      } else if (type !== "textarea") control.type = type;
      control.value = item[key] || "";
      if (["raw_text", "kind"].includes(key)) control.required = true;
      control.addEventListener("input", invalidateConfirmation);
      control.addEventListener("change", invalidateConfirmation);
      wrapper.append(control);
      card.append(wrapper);
      controls[key] = control;
    }
    field("raw_text", "Claim", "textarea");
    field("kind", "Evidence kind");
    field("state", "Evidence status", "text", [
      ...(item.state === "VERIFIED_PRESENT" ? ["VERIFIED_PRESENT"] : []),
      "SELF_REPORTED_PRESENT", "UNKNOWN", "CONFIRMED_ABSENT", "NOT_APPLICABLE",
    ]);
    field("quality", "Quality label (optional)");
    field("depth", "Contribution label (optional)");
    field("recency", "Evidence date (optional)", "date");
    const previewState = () => {
      if (controls.state.value === "VERIFIED_PRESENT" &&
          (!original || Object.entries(controls).some(([key, control]) => control.value !== (original[key] || "")))) {
        controls.state.value = "SELF_REPORTED_PRESENT";
      }
      if (!["VERIFIED_PRESENT", "SELF_REPORTED_PRESENT"].includes(controls.state.value)) {
        controls.quality.value = "";
        controls.depth.value = "";
      }
    };
    for (const control of Object.values(controls)) {
      control.addEventListener("input", previewState);
      control.addEventListener("change", previewState);
    }
    const mapping = textElement("p", "", "item-meta");
    const updateMapping = () => {
      mapping.textContent = reviewDraft.mapped_kinds.includes(controls.kind.value)
        ? "This evidence kind has a provisional scoring rule."
        : "This evidence kind has no scoring rule and will remain unassessed.";
    };
    controls.kind.addEventListener("input", updateMapping);
    updateMapping();
    card.append(mapping);
    if (!original) {
      const remove = textElement("button", "Remove new evidence", "secondary"); remove.type = "button";
      remove.addEventListener("click", () => {
        const remaining = currentEvidence().filter(evidence => evidence.id !== item.id);
        renderReview(remaining); invalidateConfirmation();
      });
      card.append(remove);
    }
    reviewItems.append(card);
    editors.push({ evidence_id: item.id, controls });
  }
  const labels = textElement("details", "");
  labels.append(textElement("summary", "Available provisional scoring labels"));
  labels.append(textElement("p", `Quality: ${Object.values(reviewDraft.quality_ladders).flatMap(Object.keys).join(", ")}. Contribution: ${Object.keys(reviewDraft.depth_factors).join(", ")}.`));
  reviewItems.append(labels);
}
function collectCorrections() {
  return editors.map(({ evidence_id, controls }) => ({
    evidence_id, ...Object.fromEntries(Object.entries(controls).map(([key, control]) =>
      [key, control.value === "" && !["raw_text", "kind", "state"].includes(key) ? null : control.value])),
  }));
}
function currentEvidence() {
  return collectCorrections().map(({evidence_id, ...fields}) => ({
    ...(reviewDraft.profile.evidence.find(item => item.id === evidence_id) ||
      {source: null, extraction_confidence: "LOW"}), id: evidence_id, ...fields,
  }));
}
document.querySelector("#add-evidence").addEventListener("click", () => {
  const items = currentEvidence();
  let number = 1;
  while (items.some(item => item.id === `student-${number}`)) number++;
  items.push({id: `student-${number}`, raw_text: "", kind: "", state: "SELF_REPORTED_PRESENT",
    quality: null, depth: null, recency: null, source: null, extraction_confidence: "LOW"});
  renderReview(items); invalidateConfirmation();
});
reviewForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!reviewDraft || !consent.checked) return;
  setBusy(true);
  hideError();
  try {
    const changes = collectCorrections();
    const existing = new Set(reviewDraft.profile.evidence.map(item => item.id));
    const confirmed = await postReview("/confirm", {
      review_id: reviewDraft.review_id, confirmed: true,
      corrections: changes.filter(item => existing.has(item.evidence_id)),
      additions: changes.filter(item => !existing.has(item.evidence_id)),
      profile_details: collectProfileDetails(),
    });
    reviewDraft = await postReview("/continue-review", {confirmation_id: confirmed.confirmation_id});
    document.querySelector("#active-question").hidden = true;
    renderProfileDetails(confirmed.profile);
    renderReview(confirmed.profile.evidence);
    confirmationStatus.textContent = `Evidence confirmed at ${confirmed.confirmed_at}. Edited present claims are self-reported. A separate snapshot has been saved.`;
    await runScore({ confirmation_id: confirmed.confirmation_id });
  } catch (error) {
    showError("Evidence could not be confirmed.", error.message);
  } finally { setBusy(false); }
});
