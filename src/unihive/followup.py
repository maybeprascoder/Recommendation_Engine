"""Experience Phase 2: connect ranked uncertainty to explicit profile edits."""

from unihive.models import CoreModel
from unihive.questions import (
    LoadedQuestionBank,
    QuestionBankEntry,
    QuestionResolutionType,
    RankedQuestion,
    rank_questions,
)
from unihive.response import ScoringResponse
from unihive.taxonomy import Taxonomy


class FollowupQuestion(CoreModel):
    question: RankedQuestion
    editor_section: str
    evidence_kinds: list[str]
    guidance: str


class FollowupQuestions(CoreModel):
    question_bank_version: str
    provisional: bool
    questions: list[FollowupQuestion]


def build_followup_questions(
    response: ScoringResponse,
    taxonomy: Taxonomy,
    bank: LoadedQuestionBank,
) -> FollowupQuestions:
    """Rank known bank questions and neutral prompts for uncovered missing fields.

    Prompts never infer a competency mapping or invent a university requirement.
    The supplied assessment is not mutated or re-scored here.
    """
    assessment = response.assessment
    profile = assessment.audit.profile_snapshot
    if profile is None:
        raise ValueError("Follow-up questions require a profile snapshot")
    missing = set(assessment.audit.missing_fields)
    for rule in response.eligibility_result.rule_breakdown:
        missing.update(rule.needed_information)
    for field in ("goals", "constraints"):
        if not getattr(profile, field):
            missing.add(field)
    entries = list(bank.values.questions)
    competency_ids = {
        trace.competency_id for trace in assessment.program_alignment.competency_trace
    }
    for target in sorted(missing):
        if target.startswith("program."):
            # Missing catalog facts cannot be answered by editing a student profile.
            continue
        kind = (
            QuestionResolutionType.COMPETENCY
            if target in competency_ids
            else QuestionResolutionType.FIELD
        )
        if any(
            item.resolves_type == kind and item.resolves_id == target
            for item in entries
        ):
            continue
        label = target.replace("_", " ").replace(".", " / ")
        entries.append(
            QuestionBankEntry(
                id=f"missing:{kind.value}:{target}",
                text=f"What can you tell us about {label}?",
                resolves_type=kind,
                resolves_id=target,
            )
        )
    enriched = assessment.model_copy(
        update={
            "audit": assessment.audit.model_copy(
                update={"missing_fields": sorted(missing)}
            )
        }
    )
    ranked = rank_questions(
        enriched,
        question_bank=bank.model_copy(
            update={
                "values": bank.values.model_copy(update={"questions": tuple(entries)})
            }
        ),
    )
    questions: list[FollowupQuestion] = []
    for question in ranked:
        competency = question.resolves_type == QuestionResolutionType.COMPETENCY
        kinds = (
            sorted(
                {
                    rule.evidence_kind
                    for rule in taxonomy.evidence_rules
                    if rule.competency_id == question.resolves_id
                }
            )
            if competency
            else []
        )
        section = "evidence" if competency else question.resolves_id.split(".")[0]
        guidance = (
            (
                "Add or correct evidence, then confirm your profile. "
                "Only configured evidence kinds can affect readiness."
                if kinds
                else "No reviewed evidence mapping is available for this competency. "
                "You can record evidence; readiness will remain unassessed."
            )
            if competency
            else "Update this profile section, then confirm to reassess. "
            "Leave unknown details blank."
        )
        questions.append(
            FollowupQuestion(
                question=question,
                editor_section=section,
                evidence_kinds=kinds,
                guidance=guidance,
            )
        )
    return FollowupQuestions(
        question_bank_version=bank.version,
        provisional=bank.values.provisional,
        questions=questions,
    )
