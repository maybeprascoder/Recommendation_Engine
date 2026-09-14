"use strict";
let claimEditors = [];
let academicEditors = [];
let judgmentEditors = [];
let savedReceiptId = null;

function renderUnderstanding() {
  const panel = document.querySelector("#understanding-review");
  panel.replaceChildren();
  claimEditors = [];
  academicEditors = [];
  judgmentEditors = [];
  const result = reviewDraft?.understanding;
  panel.hidden = !result;
  if (!result) return;
  panel.append(textElement("h3", "Review the document interpretation"));
  panel.append(textElement("p", "Recognized tools and domain context are retained in the receipt and do not earn skill credit. Confirmed absence applies only to the stated activity; it does not establish that an entire competency is absent."));
    panel.append(textElement("p", "Confirm only your own supported claims. Every correction is saved. Duplicates, third-party, unsupported, uncertain and edited statements remain here for further review. Supported judgments and skills can contribute to scoring through configured mappings after confirmation. These mappings are provisional until calibrated."));
    panel.append(textElement("p", "Academic records retain their original grades and scales. They do not change your profile fields or normalized GPA. Source support does not independently verify an accomplishment. Confirmed activities remain self-reported; explicit absence retains its separate state."));
  const checks = new Map(result.support_review.checks.map(check => [check.target_id, check]));
  for (const claim of result.draft.claims) {
    const change = reviewDraft.claim_corrections.find(item => item.claim_id === claim.id);
    const card = textElement("fieldset", "", "evidence-editor");
    card.append(textElement("legend", `${sentenceCase(claim.category)}: ${claim.id}`));
    card.append(textElement("p", `Original statement: ${claim.statement}`, "source-span"));
    const duplicate = claim.duplicate_of || result.support_review.duplicate_groups?.find(
      group => group.duplicate_claim_ids.includes(claim.id))?.canonical_claim_id;
    const check = checks.get(claim.id);
    const presence = claim.presence || "reported_present";
    card.append(textElement("p", `Original presence: ${sentenceCase(presence)}.`));
    card.append(textElement("p", `Original attribution: ${claim.attribution}. Support: ${check.verdict}. ${check.explanation}${duplicate ? ` Duplicate of ${duplicate}.` : ""}`));
    for (const citation of claim.citations) {
      card.append(textElement("blockquote", `${citation.document_id}: ${citation.quote}`, "source-span"));
    }
    const controls = {};
    for (const [key, label, options] of [
      ["statement", "Corrected statement", null],
      ["attribution", "Who did this work?", ["student", "team", "other", "unknown"]],
      ["presence", "Was this activity reported?", ["reported_present", "reported_absent", "unknown"]],
      ["decision", "Your decision", ["confirm", "exclude", "uncertain"]],
      ["notes", "Corrections to academic records, judgments or other details", null],
    ]) {
      const wrapper = textElement("label", label, "field");
      const control = document.createElement(options ? "select" : "textarea");
      if (options) for (const option of options) control.add(new Option(sentenceCase(option), option));
      control.value = key === "presence" ? (change[key] || presence) : change[key];
      control.required = key === "statement";
      control.addEventListener("input", invalidateConfirmation);
      control.addEventListener("change", invalidateConfirmation);
      wrapper.append(control); card.append(wrapper); controls[key] = control;
    }
    const disposition = textElement("p", "", "item-meta");
    const updateDisposition = () => {
      const eligible = result.supported_claim_ids.includes(claim.id) &&
        claim.attribution === "student" && controls.attribution.value === "student" &&
        controls.presence.value === presence &&
        controls.statement.value === claim.statement && controls.decision.value === "confirm";
      disposition.textContent = eligible ? (presence === "reported_absent" ?
        "Will preserve confirmed absence of this stated activity. It will not activate a scoring mapping." :
        presence === "unknown" ? "Will preserve unknown presence without scoring credit." :
        "Will import as self-reported evidence. Supported judgments and skills may qualify for configured scoring mappings.") :
        "Will remain in the audit receipt only. Changed statements, attribution or presence need another support review before import.";
    };
    for (const control of Object.values(controls)) {
      control.addEventListener("input", updateDisposition);
      control.addEventListener("change", updateDisposition);
    }
    updateDisposition(); card.append(disposition);
    const proposals = textElement("details", "");
    proposals.append(textElement("summary", "Academic records, qualitative judgments and skill suggestions"));
    for (const item of (result.draft.contexts || []).filter(item => item.claim_id === claim.id)) {
      proposals.append(textElement("p",
        `Recognized ${item.kind}: ${item.label}. ${item.rationale} Support: ${checks.get(item.id).verdict}. ${checks.get(item.id).explanation} Context only; no skill credit.`));
      for (const citation of item.citations) {
        proposals.append(textElement("blockquote", `${citation.document_id}: ${citation.quote}`));
      }
    }
    for (const record of result.draft.academics.filter(item => item.claim_id === claim.id)) {
      const academic = reviewDraft.academic_corrections.find(
        item => item.claim_id === claim.id);
      const academicBox = textElement("fieldset", "", "detail-editor");
      academicBox.append(textElement("legend", "Academic record"));
      const academicControls = {};
      for (const [key, label, options] of [
        ["institution", "Institution", null],
        ["qualification", "Qualification or degree", null],
        ["grade", "Original grade", null],
        ["grade_scale", "Original grade scale", null],
        ["decision", "Academic record decision", ["confirm", "exclude", "uncertain"]],
        ["notes", "Academic correction notes", null],
      ]) {
        const wrapper = textElement("label", label, "field");
        const control = document.createElement(options ? "select" : "input");
        if (options) for (const option of options) {
          control.add(new Option(sentenceCase(option), option));
        }
        control.value = academic[key] ?? "";
        control.addEventListener("input", invalidateConfirmation);
        control.addEventListener("change", invalidateConfirmation);
        wrapper.append(control); academicBox.append(wrapper);
        academicControls[key] = control;
      }
      academicBox.append(textElement("p",
        "The profile keeps this grade and scale exactly as shown. It does not populate normalized GPA or assume degree completion.",
        "item-meta"));
      proposals.append(academicBox);
      academicEditors.push({claim_id: claim.id, controls: academicControls});
    }
    for (const item of result.draft.judgments.filter(
      item => item.claim_id === claim.id)) {
      const correction = reviewDraft.judgment_corrections.find(
        change => change.judgment_id === item.id);
      proposals.append(textElement("p",
        `${item.dimension}: ${item.label}. ${item.rationale} Support: ${checks.get(item.id).verdict}. ${checks.get(item.id).explanation}`));
      for (const citation of item.citations) {
        proposals.append(textElement("blockquote",
          `${citation.document_id}: ${citation.quote}`));
      }
      const controls = {};
      const dimension = result.audit.rubric_snapshot.dimensions.find(
        value => value.id === item.dimension);
      for (const [key, label, options] of [
        ["label", `${sentenceCase(item.dimension)} label`, Object.keys(dimension.labels)],
        ["decision", "Qualitative judgment decision", ["confirm", "exclude", "uncertain"]],
        ["notes", "Qualitative judgment correction notes", null],
      ]) {
        const wrapper = textElement("label", label, "field");
        const control = document.createElement(options ? "select" : "input");
        if (options) for (const option of options) {
          control.add(new Option(sentenceCase(option), option));
        }
        control.value = correction[key];
        control.addEventListener("input", invalidateConfirmation);
        control.addEventListener("change", invalidateConfirmation);
        wrapper.append(control); proposals.append(wrapper); controls[key] = control;
      }
      judgmentEditors.push({judgment_id: item.id, controls});
    }
    for (const item of result.draft.competencies.filter(
      item => item.claim_id === claim.id)) {
      proposals.append(textElement("p",
        `${item.observed_skill}: ${item.competency_id || "Unmapped"}. ${item.rationale} Support: ${checks.get(item.id).verdict}. ${checks.get(item.id).explanation}`));
      for (const citation of item.citations) {
        proposals.append(textElement("blockquote",
          `${citation.document_id}: ${citation.quote}`));
      }
    }
    card.append(proposals); panel.append(card);
    claimEditors.push({claim_id: claim.id, controls});
  }
  for (const question of result.questions) panel.append(textElement("p", `${question.claim_id || "General"}: ${question.question} ${question.reason}`));
  for (const limitation of [...result.limitations, ...result.draft.unassessed]) panel.append(textElement("p", limitation, "item-meta"));
  const audit = textElement("details", "");
  audit.append(textElement("summary", "Complete original interpretation and source audit"));
  audit.append(textElement("pre", JSON.stringify(result, null, 2), "raw-value"));
  panel.append(audit);
}

function collectClaimCorrections() {
  return claimEditors.map(({claim_id, controls}) => ({claim_id,
    ...Object.fromEntries(Object.entries(controls).map(([key, control]) => [key, control.value])),
  }));
}

function collectAcademicCorrections() {
  return academicEditors.map(({claim_id, controls}) => ({claim_id,
    ...Object.fromEntries(Object.entries(controls).map(([key, control]) =>
      [key, control.value === "" && key !== "notes" ? null : control.value])),
  }));
}

function collectJudgmentCorrections() {
  return judgmentEditors.map(({judgment_id, controls}) => ({judgment_id,
    ...Object.fromEntries(Object.entries(controls).map(([key, control]) =>
      [key, control.value])),
  }));
}

document.querySelector("#download-receipt").addEventListener("click", async () => {
  if (!savedReceiptId) return;
  try {
    const receipt = await postReview("/receipt", {confirmation_id: savedReceiptId});
    const url = URL.createObjectURL(new Blob([JSON.stringify(receipt, null, 2)], {type: "application/json"}));
    const link = document.createElement("a");
    link.href = url; link.download = `unihive-receipt-${savedReceiptId}.json`; link.click();
    URL.revokeObjectURL(url);
  } catch (error) { showError("Could not download audit receipt.", error.message); }
});
