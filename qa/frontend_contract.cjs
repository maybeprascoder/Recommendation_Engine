// Run with Node. Executes the real renderer with a minimal DOM test double.
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const assert = require('node:assert/strict');
class Element {
  constructor(text = '', value = '') { this.children = []; this.textContent = text; this.value = value; this.events = {}; this.classList = {add(){}}; }
  append(...items) { this.children.push(...items); }
  replaceChildren(...items) { this.children = items; }
  addEventListener(name, handler) { (this.events[name] ||= []).push(handler); }
  dispatch(name) { for (const handler of this.events[name] || []) handler({preventDefault(){}}); }
  querySelectorAll() { return this.children.flatMap(child => [child, ...child.querySelectorAll()]); }
  remove() {}
  setAttribute(name, value) { this[name] = value; }
  scrollIntoView() {}
  add(item) { this.children.push(item); }
}
const elements = new Map();
const document = {
  createElement: () => new Element(),
  querySelector: id => {
    if (!elements.has(id)) elements.set(id, new Element());
    return elements.get(id);
  },
};
const context = vm.createContext({document, URL, URLSearchParams,
  window: {location: {search: ''}}, Option: Element,
  fetch: async () => ({ok: true, json: async () => []}),
});
vm.runInContext(fs.readFileSync(path.join(__dirname, '../web/app.js'), 'utf8'), context);
vm.runInContext(fs.readFileSync(path.join(__dirname, '../web/profile.js'), 'utf8'), context);
vm.runInContext(fs.readFileSync(path.join(__dirname, '../web/review.js'), 'utf8'), context);
vm.runInContext(fs.readFileSync(path.join(__dirname, '../web/followup.js'), 'utf8'), context);
vm.runInContext(fs.readFileSync(path.join(__dirname, '../web/understanding.js'), 'utf8'), context);
function allText(el) {
  return el.textContent + ' ' + el.children.map(allText).join(' ');
}
const checks = [
  ['interpretation review separates context and absence and blocks presence edits', () => {
    context.testDraft = {
      understanding: {
        draft: {
          claims: [{id: 'c1', category: 'activity', statement: 'I did not use ETABS.',
            attribution: 'student', presence: 'reported_absent', citations: [], duplicate_of: null}],
          contexts: [{id: 't1', claim_id: 'c1', kind: 'tool', label: 'ETABS',
            rationale: 'Named tool.', citations: [{document_id: 'resume', quote: 'ETABS'}]}],
          academics: [], judgments: [], competencies: [], unassessed: [],
        },
        support_review: {checks: [
          {target_id: 'c1', verdict: 'supported', explanation: 'Explicit absence.'},
          {target_id: 't1', verdict: 'supported', explanation: 'Named tool.'},
        ]}, supported_claim_ids: ['c1'], questions: [], limitations: [], audit: {},
      },
      claim_corrections: [{claim_id: 'c1', statement: 'I did not use ETABS.',
        attribution: 'student', presence: 'reported_absent', decision: 'confirm', notes: ''}],
      academic_corrections: [], judgment_corrections: [],
    };
    vm.runInContext('reviewDraft = testDraft; renderUnderstanding();', context);
    assert.match(allText(elements.get('#understanding-review')), /Recognized tool: ETABS/);
    assert.match(allText(elements.get('#understanding-review')), /Context only; no skill credit/);
    assert.match(allText(elements.get('#understanding-review')), /Will preserve confirmed absence/);
    assert.equal(context.collectClaimCorrections()[0].presence, 'reported_absent');
    elements.get('#evidence-consent').checked = true;
    vm.runInContext('claimEditors[0].controls.presence.value = "reported_present"; claimEditors[0].controls.presence.dispatch("change");', context);
    assert.equal(elements.get('#evidence-consent').checked, false);
    assert.match(allText(elements.get('#understanding-review')), /Will remain in the audit receipt only/);
    assert.equal(context.collectClaimCorrections()[0].presence, 'reported_present');
  }],
  ['legacy interpretations render with present default and empty context', () => {
    delete context.testDraft.understanding.draft.contexts;
    delete context.testDraft.understanding.draft.claims[0].presence;
    delete context.testDraft.claim_corrections[0].presence;
    vm.runInContext('renderUnderstanding();', context);
    assert.equal(context.collectClaimCorrections()[0].presence, 'reported_present');
    assert.match(allText(elements.get('#understanding-review')), /Will import as self-reported/);
  }],
  ['profile controls preserve nested records, false, zero and unknown', () => {
    context.inputProfile = JSON.parse(fs.readFileSync(path.join(__dirname, '../tests/fixtures/cli/profile.json'), 'utf8'));
    context.inputProfile.normalized_gpa = String(context.inputProfile.normalized_gpa);
    context.inputProfile.tests = [{test:'GRE', taken:false, score:0, details:{unresolved:null, tags:['a','b']}}];
    context.renderProfileDetails(context.inputProfile);
    const {evidence, ...details} = context.inputProfile;
    assert.deepEqual(JSON.parse(JSON.stringify(context.collectProfileDetails())), details);
  }],
  ['new evidence keeps edited original claims and requires confirmation', () => {
    const profile = JSON.parse(fs.readFileSync(path.join(__dirname, '../tests/fixtures/cli/profile.json'), 'utf8'));
    context.testDraft = {profile, mapped_kinds: [], quality_ladders: {}, depth_factors: {}};
    vm.runInContext('reviewDraft = testDraft; renderReview(testDraft.profile.evidence); editors[0].controls.raw_text.value = "Preserved edit";', context);
    elements.get('#add-evidence').dispatch('click');
    const corrections = context.collectCorrections();
    assert.equal(corrections.length, 2);
    assert.equal(corrections[0].raw_text, 'Preserved edit');
    assert.equal(corrections[1].state, 'SELF_REPORTED_PRESENT');
    assert.equal(elements.get('#evidence-consent').checked, false);
  }],
  ['follow-ups show one question and skipping leaves profile untouched', () => {
    vm.runInContext('followups = [{question:{text:"First question", expected_effect:"Reason"}, evidence_kinds:[], guidance:"Guide"},{question:{text:"Second question", expected_effect:"Reason"}, evidence_kinds:[], guidance:"Guide"}]; questionIndex = 0; renderFollowup();', context);
    assert.equal(elements.get('#followup-text').textContent, 'First question');
    const before = JSON.stringify(context.collectProfileDetails());
    elements.get('#skip-question').dispatch('click');
    assert.equal(elements.get('#followup-text').textContent, 'Second question');
    assert.equal(JSON.stringify(context.collectProfileDetails()), before);
    elements.get('#skip-question').dispatch('click');
    assert.equal(elements.get('#answer-question').hidden, true);
  }],
  ['evidence editor preserves source and invalidates confirmation after an edit', () => {
    const profile = JSON.parse(fs.readFileSync(path.join(__dirname, '../tests/fixtures/cli/profile.json'), 'utf8'));
    context.testDraft = {profile, mapped_kinds: ['machine_learning_publication'], quality_ladders: {}, depth_factors: {}};
    vm.runInContext('reviewDraft = testDraft; renderReview(testDraft.profile.evidence); lastSelection = {confirmation_id: "saved"};', context);
    elements.get('#evidence-consent').checked = true;
    assert.match(allText(elements.get('#review-items')), /Original source: First-author paper/);
    vm.runInContext('editors[0].controls.raw_text.value = "Corrected"; editors[0].controls.raw_text.dispatch("input");', context);
    assert.equal(elements.get('#evidence-consent').checked, false);
    assert.equal(elements.get('#rescore-button').disabled, true);
    assert.equal(elements.get('#confirm-button').disabled, true);
    assert.equal(elements.get('#results').hidden, true);
    assert.equal(vm.runInContext('editors[0].controls.state.value', context), 'SELF_REPORTED_PRESENT');
    assert.equal(context.collectCorrections()[0].source, undefined);
    assert.equal(context.collectCorrections()[0].raw_text, 'Corrected');
  }],
  ['unknown clears scored labels and unsupported kind is disclosed', () => {
    vm.runInContext('editors[0].controls.state.value = "UNKNOWN"; editors[0].controls.state.dispatch("change"); editors[0].controls.kind.value = "coursework"; editors[0].controls.kind.dispatch("input");', context);
    assert.equal(context.collectCorrections()[0].quality, null);
    assert.equal(context.collectCorrections()[0].depth, null);
    assert.match(allText(elements.get('#review-items')), /no scoring rule/);
  }],
  ['selection changes clear the draft and hide previous review', () => {
    elements.get('#profile-picker').dispatch('change');
    assert.equal(elements.get('#review-form').hidden, true);
    assert.equal(vm.runInContext('reviewDraft', context), null);
    assert.equal(elements.get('#rescore-button').disabled, true);
  }],
  ['API envelope renders evidence, eligibility and explicit limitations', () => {
    const payload = JSON.parse(fs.readFileSync(path.join(__dirname, 'step2-response.json'), 'utf8'));
    context.renderAssessment(payload);
    assert.match(allText(elements.get('#understood-evidence')), /First-author paper/);
    assert.match(allText(elements.get('#strengths')), /machine_learning/);
    assert.match(allText(elements.get('#eligibility-rules')), /Minimum-gpa|Minimum gpa/);
    assert.match(allText(elements.get('#chosen-path')), /MS Machine Learning/);
    assert.match(allText(elements.get('#alternatives')), /not assessed/);
    assert.match(allText(elements.get('#top-actions')), /not assessed/);
    assert.equal(elements.get('#provisional-notice').hidden, false);
  }],
  ['alternative names follow the same backend contract', () => {
    context.renderPathways({report: {chosen_path_and_alternatives: {
      chosen_path: {path_id: 'cyber-ms', field: 'Cybersecurity', readiness_band: 'DEVELOPING'},
      alternatives: [{path_id: 'ds-ms', field: 'Data Science', readiness_band: 'STRONG',
        delta: 'DEVELOPING_TO_STRONG', reasoning: 'Supplied comparison evidence'}],
    }}});
    assert.match(allText(elements.get('#alternatives')), /Data Science/);
  }],
  ['chosen path uses backend field/path_id', () => {
    context.renderPathways({report: {chosen_path_and_alternatives: {
      chosen_path: {path_id: 'cyber-ms', field: 'Cybersecurity', readiness_band: 'DEVELOPING'},
      alternatives: [],
    }}});
    assert.match(allText(elements.get('#chosen-path')), /Cybersecurity|cyber-ms/);
  }],
  ['known below-level evidence remains visible as a gap', () => {
    context.renderEvidence({report: {strengths: [], gaps: [{
      competency_id: 'security', state: 'VERIFIED_PRESENT', kind: 'BELOW_EXPECTED_LEVEL',
      demonstrated_level: 1, expected_level: 3, evidence_ids: ['course'],
    }]}});
    assert.match(allText(elements.get('#gaps')), /security/);
  }],
  ['unknown evidence is not rendered as a gap', () => {
    context.renderEvidence({report: {gaps: [{competency_id: 'networking', state: 'UNKNOWN'}]}});
    assert.doesNotMatch(allText(elements.get('#gaps')), /networking/);
  }],
  ['unknowns cannot bypass filtering through a contradictory gap kind', () => {
    context.renderEvidence({report: {gaps: [{competency_id: 'networking', state: 'UNKNOWN', kind: 'BELOW_EXPECTED_LEVEL'}]}});
    assert.doesNotMatch(allText(elements.get('#gaps')), /networking/);
  }],
];
let failures = 0;
for (const [name, run] of checks) {
  try { run(); console.log('PASS: ' + name); }
  catch (error) { failures++; console.log('FAIL: ' + name + '\n' + error.message); }
}
console.log(`${checks.length - failures} passed, ${failures} failed`);
process.exitCode = failures ? 1 : 0;
