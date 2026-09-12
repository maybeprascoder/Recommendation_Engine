"""CLI orchestration for the generic evaluator; no changes to existing scoring."""

from __future__ import annotations

import sys
from pathlib import Path

from pydantic import JsonValue, ValidationError

from unihive.llm.provider import CompatibleChatClient, Completion, StructuredClient
from unihive.llm.understanding import analyze_documents
from unihive.models import CoreModel
from unihive.taxonomy import load_taxonomy
from unihive.understanding import SourceDocument, SupportReview, UnderstandingDraft


class RecordedResponses(CoreModel):
    draft: UnderstandingDraft
    review: SupportReview


class RecordedClient:
    provider = "recorded-offline"
    model = "recorded-offline"

    def __init__(self, responses: RecordedResponses) -> None:
        self._responses = iter([responses.draft, responses.review])

    def complete(
        self,
        *,
        instructions: str,
        payload: str,
        schema: dict[str, JsonValue],
        name: str,
    ) -> Completion:
        return Completion(
            text=next(self._responses).model_dump_json(),
            response_id="recorded:" + name,
            model=self.model,
        )


def run_analysis(
    paths: list[Path],
    recorded_path: Path | None,
    output_path: Path | None,
) -> int:
    """Read explicit text inputs; never overwrite sources or existing reports."""
    try:
        if output_path is not None and output_path.exists():
            raise ValueError("Output already exists; choose a new file")
        documents = []
        for index, path in enumerate(paths, start=1):
            if path.suffix.lower() not in {".txt", ".md"}:
                raise ValueError("This milestone accepts UTF-8 .txt/.md inputs")
            if path.stat().st_size > 400_000:
                raise ValueError("Document exceeds input size limit")
            documents.append(
                SourceDocument(
                    id=f"document-{index}",
                    text=path.read_text("utf-8-sig"),
                )
            )
        client: StructuredClient
        if recorded_path is not None:
            client = RecordedClient(
                RecordedResponses.model_validate_json(
                    recorded_path.read_text("utf-8"),
                    strict=True,
                )
            )
        else:
            client = CompatibleChatClient.from_environment()
        taxonomy = load_taxonomy()
        print("Provisional evaluation rubrics in use: 1", file=sys.stderr)
        result = analyze_documents(
            documents,
            client,
            taxonomy_version=taxonomy.understanding_version,
            competency_catalog={
                node.id: node.description for node in taxonomy.competencies
            },
        )
        encoded = result.model_dump_json(indent=2)
        if output_path is None:
            print(encoded)
        else:
            # Exclusive creation avoids overwriting a source, even after a race.
            with output_path.open("x", encoding="utf-8") as output:
                output.write(encoded + "\n")
        return 0
    except ValidationError:
        print(
            "Analysis failed: invalid structured input or recorded responses",
            file=sys.stderr,
        )
        return 2
    except (OSError, ValueError) as exc:
        print(f"Analysis failed: {exc}", file=sys.stderr)
        return 2
