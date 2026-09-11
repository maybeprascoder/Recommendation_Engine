"use strict";

const MISSING = "Not provided";
const isDev = new URLSearchParams(window.location.search).get("dev") === "1";

const form = document.querySelector("#score-form");
const profilePicker = document.querySelector("#profile-picker");
const programPicker = document.querySelector("#program-picker");
const scoreButton = document.querySelector("#score-button");
const rescoreButton = document.querySelector("#rescore-button");
const statusText = document.querySelector("#status");
const results = document.querySelector("#results");
const errorPanel = document.querySelector("#error-panel");
const tracePanel = document.querySelector("#trace-panel");
const traceToggle = document.querySelector("#trace-toggle");
const traceContent = document.querySelector("#trace-content");

let lastSelection = null;

if (isDev) {
  tracePanel.hidden = false;
} else {
  tracePanel.remove();
}

function hasValue(value) {
  return value !== null && value !== undefined && value !== "";
}

function supplied(value) {
  return hasValue(value) ? String(value) : MISSING;
}

function sentenceCase(value) {
  if (!hasValue(value)) {
    return MISSING;
  }
  const words = String(value).replaceAll("_", " ").toLowerCase();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

function textElement(tagName, text, className) {
  const element = document.createElement(tagName);
  element.textContent = text;
  if (className) {
    element.className = className;
  }
  return element;
}

function clearWithMissing(container, message = MISSING) {
  container.replaceChildren(textElement("li", message, "missing"));
}

function asArray(value) {
  return Array.isArray(value) ? value : [];
}

function firstSupplied(...values) {
  return values.find((value) => value !== null && value !== undefined);
}

async function loadOptions(endpoint, picker, emptyLabel) {
  const response = await fetch(endpoint);
  if (!response.ok) {
    throw new Error(`Could not load ${emptyLabel.toLowerCase()}.`);
  }
  const options = await response.json();
  picker.replaceChildren();
  if (options.length === 0) {
    const option = new Option(`No ${emptyLabel.toLowerCase()} found`, "");
    option.disabled = true;
    option.selected = true;
    picker.add(option);
    return;
  }
  for (const item of options) {
    picker.add(new Option(item.label, item.path));
  }
}

async function initialize() {
  scoreButton.disabled = true;
  try {
    await Promise.all([
      loadOptions("/profiles", profilePicker, "Profiles"),
      loadOptions("/programs", programPicker, "Programs"),
    ]);
    const ready = Boolean(profilePicker.value && programPicker.value);
    scoreButton.disabled = !ready;
    statusText.textContent = ready
      ? "Ready to review evidence."
      : "No test inputs available. Start the server with --demo to use synthetic fixtures.";
  } catch (error) {
    showError(error.message, MISSING);
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  startReview({
    profile_path: profilePicker.value,
    program_path: programPicker.value,
  });
});

rescoreButton.addEventListener("click", () => {
  if (lastSelection) {
    runScore(lastSelection);
  }
});

if (isDev) {
  traceToggle.addEventListener("change", () => {
    traceContent.hidden = !traceToggle.checked;
  });
}

async function runScore(selection) {
  setBusy(true);
  hideError();
  try {
    const response = await fetch("/score", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(selection),
    });
    const payload = await response.json();
    if (!response.ok) {
      const error = payload.error || {};
      showError(error.message || "Scoring failed.", error.stderr || MISSING);
      return;
    }
    renderAssessment(payload);
    lastSelection = { ...selection };
    rescoreButton.disabled = false;
    statusText.textContent = "Assessment updated.";
    await loadFollowups(selection);
  } catch (error) {
    showError("The scoring request could not be completed.", error.message);
  } finally {
    setBusy(false);
  }
}

function setBusy(isBusy) {
  scoreButton.disabled = isBusy || !profilePicker.value || !programPicker.value;
  profilePicker.disabled = isBusy;
  programPicker.disabled = isBusy;
  document.querySelector("#understanding-file").disabled = isBusy;
  document.querySelector("#followup-panel").querySelectorAll("button")
    .forEach((control) => { control.disabled = isBusy; });
  document.querySelector("#review-form").querySelectorAll("input, select, textarea, button")
    .forEach((control) => { control.disabled = isBusy || control.dataset.readonly === "true"; });
  document.querySelector("#confirm-button").disabled = isBusy ||
    !document.querySelector("#evidence-consent").checked;
  rescoreButton.disabled = isBusy || lastSelection === null;
  scoreButton.textContent = isBusy ? "Working…" : "Review evidence";
  if (isBusy) {
    statusText.textContent = "Running the deterministic engine…";
  }
}

function showError(message, detail) {
  errorPanel.hidden = false;
  document.querySelector("#error-message").textContent = supplied(message);
  document.querySelector("#error-detail").textContent = supplied(detail);
  statusText.textContent = "Review the error and try again.";
}

function hideError() {
  errorPanel.hidden = true;
}

function renderAssessment(payload) {
  const assessment = payload.assessment
    ? { ...payload.assessment, report: payload.report,
        eligibility_result: payload.eligibility_result, limitations: payload.limitations }
    : payload;
  results.hidden = false;
  const provisional = document.querySelector("#provisional-notice");
  provisional.hidden = !payload.provisional;
  provisional.textContent = payload.provisional
    ? "Provisional configuration: these results have not been validated for real university recommendations."
    : "";
  renderUnderstood(assessment);
  renderReadiness(assessment);
  renderEligibility(assessment);
  renderPathways(assessment);
  renderActions(assessment);
  renderEvidence(assessment);
  renderUnknowns(assessment);
  if (isDev) {
    renderTrace(assessment);
  }
}

function renderUnderstood(assessment) {
  const container = document.querySelector("#understood-evidence");
  container.replaceChildren();
  const evidence = asArray(assessment.report?.what_we_understand_about_you);
  if (evidence.length === 0) {
    clearWithMissing(container, "No evidence supplied yet.");
    return;
  }
  for (const item of evidence) {
    const row = textElement("li", "", "item");
    row.append(
      textElement("p", supplied(item.raw_text), "item-title"),
      textElement("p", `State: ${sentenceCase(item.state)} · Evidence: ${supplied(item.evidence_id)}`, "item-meta"),
      textElement("p", `Source: ${supplied(item.source)}`, "item-meta"),
    );
    container.append(row);
  }
}

function limitationMessage(assessment, code, fallback) {
  return asArray(assessment.limitations).find(item => item.code === code)?.message || fallback;
}

function renderReadiness(assessment) {
  const band = assessment.pathway_readiness;
  document.querySelector("#readiness-band").textContent = hasValue(band)
    ? sentenceCase(band) : "Not yet assessed";
  document.querySelector("#confidence").textContent = sentenceCase(
    assessment.data_confidence,
  );
  const card = document.querySelector("#readiness-card");
  card.className = "state-card";
  const bandClass = hasValue(band)
    ? `band-${String(band).toLowerCase()}`
    : "band-missing";
  card.classList.add(bandClass);
}

function renderEligibility(assessment) {
  const eligibility = assessment.eligibility;
  const status =
    eligibility && typeof eligibility === "object"
      ? eligibility.status
      : eligibility;
  document.querySelector("#eligibility-status").textContent = sentenceCase(status);

  const breakdown = firstSupplied(
    eligibility && typeof eligibility === "object"
      ? eligibility.rule_breakdown
      : undefined,
    assessment.eligibility_result?.rule_breakdown,
  );
  const container = document.querySelector("#eligibility-rules");
  container.replaceChildren();
  if (!Array.isArray(breakdown) || breakdown.length === 0) {
    clearWithMissing(container, "No eligibility rules supplied; eligibility is not yet assessed.");
    return;
  }
  for (const rule of breakdown) {
    const item = textElement("li", "", "detail-item");
    item.append(
      textElement(
        "p",
        sentenceCase(firstSupplied(rule.rule_id, rule.rule_type)),
        "item-title",
      ),
      textElement("p", sentenceCase(rule.outcome), "item-meta"),
    );
    if (asArray(rule.needed_information).length) {
      item.append(textElement("p", `Needed: ${formatList(rule.needed_information)}`, "item-meta"));
    }
    if (hasValue(rule.source_url)) {
      const link = safeSourceLink(rule.source_url);
      if (link) {
        item.append(link);
      }
    }
    container.append(item);
  }
}

function renderPathways(assessment) {
  const report = assessment.report || {};
  const pathways = firstSupplied(
    assessment.chosen_path_and_alternatives,
    report.chosen_path_and_alternatives,
  );
  const chosenContainer = document.querySelector("#chosen-path");
  const alternativesContainer = document.querySelector("#alternatives");
  chosenContainer.replaceChildren();
  alternativesContainer.replaceChildren();
  if (!pathways || typeof pathways !== "object") {
    chosenContainer.append(textElement("p", MISSING, "missing"));
    clearWithMissing(alternativesContainer);
    return;
  }

  const chosen = firstSupplied(pathways.chosen_path, pathways.selected_path);
  if (!chosen || typeof chosen !== "object") {
    chosenContainer.append(textElement("p", MISSING, "missing"));
  } else {
    chosenContainer.append(
      textElement(
        "p",
        supplied(firstSupplied(chosen.field, chosen.path_id, chosen.name, chosen.pathway_id, chosen.program_id)),
        "item-title",
      ),
      textElement(
        "p",
        `Readiness band: ${hasValue(chosen.readiness_band) ? sentenceCase(chosen.readiness_band) : "Not yet assessed"}`,
        "item-meta",
      ),
    );
  }

  const alternatives = asArray(pathways.alternatives);
  if (alternatives.length === 0) {
    clearWithMissing(alternativesContainer, limitationMessage(assessment,
      "ALTERNATIVES_NOT_ASSESSED", "No alternatives supplied for comparison."));
    return;
  }
  for (const alternative of alternatives) {
    const item = textElement("li", "", "item");
    item.append(
      textElement(
        "p",
        supplied(
          firstSupplied(
            alternative.field,
            alternative.path_id,
            alternative.name,
            alternative.pathway_id,
            alternative.program_id,
          ),
        ),
        "item-title",
      ),
      textElement(
        "p",
        `Band: ${sentenceCase(firstSupplied(alternative.readiness_band, alternative.band))} · Delta: ${supplied(firstSupplied(alternative.band_delta, alternative.delta))}`,
        "item-meta",
      ),
      textElement(
        "p",
        supplied(firstSupplied(alternative.reason, alternative.reasoning)),
      ),
    );
    alternativesContainer.append(item);
  }
}

function renderActions(assessment) {
  const actions = firstSupplied(assessment.top_actions, assessment.report?.top_actions);
  const container = document.querySelector("#top-actions");
  container.replaceChildren();
  if (!Array.isArray(actions) || actions.length === 0) {
    clearWithMissing(container, limitationMessage(assessment,
      "ACTIONS_NOT_ASSESSED", "No reviewed action candidates supplied."));
    return;
  }
  for (const action of actions) {
    const item = textElement("li", "", "item");
    item.append(
      textElement(
        "p",
        supplied(firstSupplied(action.title, action.action_id)),
        "item-title",
      ),
      textElement(
        "p",
        `Moves to: ${sentenceCase(firstSupplied(action.projected_band, action.band))} · Effort: ${sentenceCase(action.effort)}`,
        "item-meta",
      ),
      textElement("p", supplied(firstSupplied(action.why, action.reason))),
    );
    container.append(item);
  }
}

function renderEvidence(assessment) {
  const strengths = firstSupplied(assessment.strengths, assessment.report?.strengths);
  const gaps = firstSupplied(assessment.gaps, assessment.report?.gaps);
  renderCompetencyList(document.querySelector("#strengths"), strengths,
    "No demonstrated strengths identified from the assessed evidence.");

  const confirmedGaps = asArray(gaps).filter(
    (gap) =>
      gap?.state === "CONFIRMED_ABSENT" ||
      (["VERIFIED_PRESENT", "SELF_REPORTED_PRESENT"].includes(gap?.state) &&
        gap?.kind === "BELOW_EXPECTED_LEVEL"),
  );
  renderCompetencyList(document.querySelector("#gaps"), confirmedGaps,
    "No confirmed gaps identified from the assessed evidence.");
}

function renderCompetencyList(container, values, emptyMessage = MISSING) {
  container.replaceChildren();
  if (!Array.isArray(values) || values.length === 0) {
    clearWithMissing(container, emptyMessage);
    return;
  }
  for (const value of values) {
    const item = textElement("li", "", "item");
    const title =
      typeof value === "string"
        ? value
        : firstSupplied(value.competency_id, value.name, value.title);
    item.append(textElement("p", supplied(title), "item-title"));
    if (value && typeof value === "object") {
      item.append(
        textElement(
          "p",
          `State: ${sentenceCase(value.state)} · Evidence: ${formatList(value.evidence_ids)}`,
          "item-meta",
        ),
      );
      if (value.kind === "BELOW_EXPECTED_LEVEL") {
        item.append(textElement("p",
          `Demonstrated level: ${supplied(value.demonstrated_level)} · Required level: ${supplied(value.expected_level)}`,
          "item-meta"));
      }
    }
    container.append(item);
  }
}

function renderUnknowns(assessment) {
  const unknowns = firstSupplied(
    assessment.what_we_cannot_assess_yet,
    assessment.report?.what_we_cannot_assess_yet,
    assessment.not_assessed,
  );
  const container = document.querySelector("#not-assessed");
  container.replaceChildren();
  if (!Array.isArray(unknowns) || unknowns.length === 0) {
    clearWithMissing(container, "No unresolved fields in this assessment.");
    return;
  }
  for (const unknown of unknowns) {
    const item = textElement("li", "", "item");
    const field =
      typeof unknown === "string"
        ? unknown
        : firstSupplied(unknown.field, unknown.competency_id);
    item.append(textElement("p", supplied(field), "item-title"));
    if (unknown && typeof unknown === "object") {
      item.append(
        textElement(
          "p",
          supplied(firstSupplied(unknown.needed_to_resolve, unknown.reason)),
          "item-meta",
        ),
      );
    }
    container.append(item);
  }
}

function renderTrace(assessment) {
  const traces = assessment.program_alignment?.competency_trace;
  const container = document.querySelector("#trace-list");
  container.replaceChildren();
  if (!Array.isArray(traces) || traces.length === 0) {
    clearWithMissing(container);
    return;
  }
  for (const trace of traces) {
    const item = textElement("li", "", "trace-item");
    item.append(
      textElement("h3", supplied(trace.competency_id)),
      textElement(
        "p",
        `State: ${sentenceCase(trace.state)} · Demand weight: ${supplied(trace.demand_weight)} · Contribution: ${supplied(trace.contribution)}`,
        "trace-detail",
      ),
      textElement(
        "p",
        `Evidence ids: ${formatList(trace.evidence_ids)}`,
        "trace-detail",
      ),
    );
    if (hasValue(trace.exclusion_reason)) {
      item.append(
        textElement(
          "p",
          `Excluded: ${sentenceCase(trace.exclusion_reason)}`,
          "trace-detail",
        ),
      );
    }
    const evidenceTrace = asArray(trace.evidence_trace);
    if (evidenceTrace.length > 0) {
      const evidenceList = textElement("ul", "", "detail-list");
      for (const evidence of evidenceTrace) {
        evidenceList.append(
          textElement(
            "li",
            `${supplied(evidence.evidence_id)} — contribution: ${supplied(evidence.contribution)}`,
            "detail-item raw-value",
          ),
        );
      }
      item.append(evidenceList);
    }
    container.append(item);
  }
}

function formatList(value) {
  return Array.isArray(value) && value.length > 0 ? value.join(", ") : MISSING;
}

function safeSourceLink(value) {
  try {
    const url = new URL(String(value));
    if (url.protocol !== "http:" && url.protocol !== "https:") {
      return null;
    }
    const link = textElement("a", "Source", "item-meta");
    link.href = url.href;
    link.target = "_blank";
    link.rel = "noreferrer";
    return link;
  } catch {
    return null;
  }
}

initialize();
