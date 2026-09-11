"use strict";
const followupPanel = document.querySelector("#followup-panel");
const answerQuestion = document.querySelector("#answer-question");
const skipQuestion = document.querySelector("#skip-question");
let followups = [];
let questionIndex = 0;

async function loadFollowups(selection) {
  followupPanel.hidden = false;
  document.querySelector("#followup-text").textContent = "Checking what information would help next…";
  try {
    const payload = await postReview("/questions", selection);
    followups = payload.questions; questionIndex = 0;
    document.querySelector("#followup-status").textContent = payload.provisional ?
      "Questions use provisional configuration. You can skip any question." : "You can skip any question.";
    renderFollowup();
  } catch (error) {
    followups = []; questionIndex = 0; renderFollowup();
    document.querySelector("#followup-text").textContent = "Questions could not be loaded. Your assessment is still available.";
    document.querySelector("#followup-status").textContent = error.message;
  }
}
function renderFollowup() {
  const item = followups[questionIndex];
  document.querySelector("#followup-text").textContent = item?.question.text ||
    "No more questions to show now. Unassessed information may still remain.";
  document.querySelector("#followup-reason").textContent = item?.question.expected_effect || "";
  document.querySelector("#followup-guidance").textContent = item ?
    item.guidance + (item.evidence_kinds.length ? ` Available evidence kinds: ${item.evidence_kinds.join(", ")}.` : "") : "";
  answerQuestion.hidden = !item; skipQuestion.hidden = !item;
}
skipQuestion.addEventListener("click", () => {
  questionIndex++; renderFollowup();
  document.querySelector("#followup-status").textContent = "Skipped for now. Your profile and assessment are unchanged.";
});
answerQuestion.addEventListener("click", async () => {
  const item = followups[questionIndex];
  const selection = lastSelection;
  if (!item || !selection) return;
  setBusy(true); hideError();
  try {
    const draft = await postReview("/continue-review", {
      ...selection, question_id: item.question.question_id,
    });
    invalidateConfirmation(); reviewDraft = draft;
    renderProfileDetails(draft.profile); renderReview(draft.profile.evidence);
    renderUnderstanding();
    reviewForm.hidden = false;
    const prompt = document.querySelector("#active-question");
    prompt.textContent = `${item.question.text} ${item.guidance}`; prompt.hidden = false;
    const section = profileSections.get(item.editor_section);
    if (section) { section.open = true; section.scrollIntoView({block: "center"}); }
    else reviewItems.scrollIntoView({block: "start"});
    statusText.textContent = "Update the highlighted information, then confirm and score.";
  } catch (error) {
    showError("Could not open this question.", error.message);
  } finally { setBusy(false); }
});
