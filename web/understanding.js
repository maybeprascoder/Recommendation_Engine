"use strict";
let claimEditors = [];
let savedReceiptId = null;

function renderUnderstanding() {
  const panel = document.querySelector("#understanding-review");
  panel.replaceChildren();
  claimEditors = [];
  const result = reviewDraft?.understanding;
  panel.hidden = !result;
  if (!result) return;
  panel.append(textElement("h3", "Review the document interpretation"));
  panel.append(textElement("p", "Confirm only your own supported claims. Every correction is saved. Duplicates, third-party, unsupported, uncertain and edited statements remain here for further review. Imported claims await approved scoring mappings and contribute no numerical score."));
  panel.append(textElement("p", "Academic records retain their original grades and scales. They do not change your profile fields or normalized GPA. Qualitative judgments and skill suggestions are review notes only."));
  const checks = new Map(result.support_review.checks.map(check => [check.target_id, check]));
  for (const claim of result.draft.claims) {
    const change = reviewDraft.claim_corrections.find(item => item.claim_id === claim.id);
    const card = textElement("fieldset", "", "evidence-editor");
    card.append(textElement("legend", `${sentenceCase(claim.category)}: ${claim.id}`));
    card.append(textElement("p", `Original statement: ${claim.statement}`, "source-span"));
    const duplicate = claim.duplicate_of || result.support_review.duplicate_groups?.find(
      group => group.duplicate_claim_ids.includes(claim.id))?.canonical_claim_id;
    const check = checks.get(claim.id);
    card.append(textElement("p", `Original attribution: ${claim.attribution}. Support: ${check.verdict}. ${check.explanation}${duplicate ? ` Duplicate of ${duplicate}.` : ""}`));
    for (const citation of claim.citations) {
      card.append(textElement("blockquote", `${citation.document_id}: ${citation.quote}`, "source-span"));
    }
    const controls = {};
    for (const [key, label, options] of [
      ["statement", "Corrected statement", null],
      ["attribution", "Who did this work?", ["student", "team", "other", "unknown"]],
      ["decision", "Your decision", ["confirm", "exclude", "uncertain"]],
      ["notes", "Corrections to academic records, judgments or other details", null],
    ]) {
      const wrapper = textElement("label", label, "field");
      const control = document.createElement(options ? "select" : "textarea");
      if (options) for (const option of options) control.add(new Option(sentenceCase(option), option));
      control.value = change[key];
      control.required = key === "statement";
      control.addEventListener("input", invalidateConfirmation);
      control.addEventListener("change", invalidateConfirmation);
      wrapper.append(control); card.append(wrapper); controls[key] = control;
    }
    const disposition = textElement("p", "", "item-meta");
    const updateDisposition = () => {
      const eligible = result.supported_claim_ids.includes(claim.id) &&
        claim.attribution === "student" && controls.attribution.value === "student" &&
        controls.statement.value === claim.statement && controls.decision.value === "confirm";
      disposition.textContent = eligible ? "Will import as self-reported evidence, without a numerical score." :
        "Will remain in the audit receipt only. Changed statements or attribution need another support review before import.";
    };
    for (const control of Object.values(controls)) control.addEventListener("input", updateDisposition);
    updateDisposition(); card.append(disposition);
    const proposals = textElement("details", "");
    proposals.append(textElement("summary", "Academic records, qualitative judgments and skill suggestions"));
    for (const record of result.draft.academics.filter(item => item.claim_id === claim.id)) {
      proposals.append(textElement("p", `Institution: ${record.institution ?? "Unknown"}; qualification: ${record.qualification ?? "Unknown"}; grade: ${record.grade ?? "Unknown"}; scale: ${record.grade_scale ?? "Unknown"}.`));
    }
    for (const item of [...result.draft.judgments, ...result.draft.competencies].filter(item => item.claim_id === claim.id)) {
      proposals.append(textElement("p", `${item.dimension || item.observed_skill}: ${item.label || item.competency_id || "Unmapped"}. ${item.rationale} Support: ${checks.get(item.id).verdict}. ${checks.get(item.id).explanation}`));
      for (const citation of item.citations) proposals.append(textElement("blockquote", `${citation.document_id}: ${citation.quote}`));
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
