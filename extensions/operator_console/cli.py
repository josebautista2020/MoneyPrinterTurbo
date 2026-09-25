"""CLI for governed Content Studio release operations."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any

from extensions.content_studio.domain import DomainValidationError
from extensions.content_studio.consistency import ReferenceCatalog
from extensions.content_studio.orchestration import StageExecutionResult
from extensions.content_studio.publishing import PublishingPolicy, PublishRequest
from extensions.content_studio.runtime import RuntimeProfile
from extensions.content_studio.visual_generation import VisualGenerationPlan
from extensions.operator_console.service import OperatorConsoleService
from extensions.runtime_profiles.reference_preflight import (
    preflight_reference_images,
)

ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_WORKFLOW_DIR = Path(
    os.getenv(
        "CONTENT_STUDIO_WORKFLOW_DIR",
        str(ROOT_DIR / "output" / "content_studio" / "workflows"),
    )
)
DEFAULT_REVIEW_DIR = Path(
    os.getenv(
        "CONTENT_STUDIO_REVIEW_LOG_DIR",
        str(ROOT_DIR / "output" / "content_studio" / "review_audit"),
    )
)
DEFAULT_PUBLICATION_DIR = Path(
    os.getenv(
        "CONTENT_STUDIO_PUBLICATION_LOG_DIR",
        str(ROOT_DIR / "output" / "content_studio" / "publication_audit"),
    )
)


def _read_text(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def _service(args: argparse.Namespace) -> OperatorConsoleService:
    return OperatorConsoleService(
        workflow_dir=args.workflow_dir,
        review_audit_dir=args.review_dir,
        publication_audit_dir=args.publication_dir,
    )


def _print_json(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def _add_storage_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--workflow-dir",
        default=str(DEFAULT_WORKFLOW_DIR),
    )
    parser.add_argument(
        "--review-dir",
        default=str(DEFAULT_REVIEW_DIR),
    )
    parser.add_argument(
        "--publication-dir",
        default=str(DEFAULT_PUBLICATION_DIR),
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="content-studio-operator",
        description=(
            "Governed Content Studio workflow operations. "
            "Live publication is intentionally unsupported."
        ),
    )
    _add_storage_args(parser)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list")

    create = sub.add_parser("create")
    create.add_argument("--workflow-id", required=True)
    create.add_argument("--project-id", required=True)
    create.add_argument("--episode-id", required=True)
    create.add_argument("--max-cost-usd", type=float)

    show = sub.add_parser("show")
    show.add_argument("--workflow-id", required=True)

    artifacts = sub.add_parser("artifacts")
    artifacts.add_argument("--workflow-id", required=True)

    apply_stage = sub.add_parser("apply-stage")
    apply_stage.add_argument("--workflow-id", required=True)
    apply_stage.add_argument("--result", required=True)

    apply_bundle = sub.add_parser("apply-bundle")
    apply_bundle.add_argument("--workflow-id", required=True)
    apply_bundle.add_argument("--results", required=True)

    runtime_matrix = sub.add_parser("runtime-matrix")
    runtime_matrix.add_argument("--profile", required=True)

    references = sub.add_parser("preflight-references")
    references.add_argument("--plan", required=True)
    references.add_argument("--catalog", required=True)

    run_runtime = sub.add_parser("run-runtime")
    run_runtime.add_argument("--workflow-id", required=True)
    run_runtime.add_argument("--profile", required=True)
    run_runtime.add_argument(
        "--confirm-external",
        action="store_true",
    )
    run_runtime.add_argument(
        "--confirm-paid",
        action="store_true",
    )

    review = sub.add_parser("review")
    review.add_argument("--workflow-id", required=True)
    review.add_argument(
        "--action",
        required=True,
        choices=(
            "approve",
            "reject",
            "regenerate_shot",
            "regenerate_episode",
        ),
    )
    review.add_argument("--reviewer-id", required=True)
    review.add_argument("--comments", required=True)
    review.add_argument("--target-shot-id")
    review.add_argument("--decision-id")
    review.add_argument("--decided-at")

    publish = sub.add_parser("publish-dry-run")
    publish.add_argument("--workflow-id", required=True)
    publish.add_argument("--request", required=True)
    publish.add_argument("--policy", required=True)
    publish.add_argument("--recorded-at")

    release = sub.add_parser("release")
    release.add_argument("--workflow-id", required=True)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    service = _service(args)

    try:
        if args.command == "list":
            _print_json({"workflows": service.list_workflow_ids()})
            return 0

        if args.command == "create":
            state = service.create_workflow(
                workflow_id=args.workflow_id,
                project_id=args.project_id,
                episode_id=args.episode_id,
                max_cost_usd=args.max_cost_usd,
            )
            _print_json(state.to_dict())
            return 0

        if args.command == "show":
            _print_json(asdict(service.summarize(args.workflow_id)))
            return 0

        if args.command == "artifacts":
            _print_json(
                {
                    "artifacts": [
                        item.to_dict()
                        for item in service.active_artifacts(args.workflow_id)
                    ]
                }
            )
            return 0

        if args.command == "apply-stage":
            result = StageExecutionResult.from_json(
                _read_text(args.result)
            )
            state = service.apply_stage_result(
                args.workflow_id,
                result,
            )
            _print_json(state.to_dict())
            return 0

        if args.command == "apply-bundle":
            decoded = json.loads(_read_text(args.results))
            if not isinstance(decoded, list):
                raise DomainValidationError(
                    "stage result bundle JSON must be an array"
                )
            results = tuple(
                StageExecutionResult.from_dict(item)
                for item in decoded
            )
            state = service.apply_stage_results(
                args.workflow_id,
                results,
            )
            _print_json(state.to_dict())
            return 0

        if args.command == "runtime-matrix":
            profile = RuntimeProfile.from_json(
                _read_text(args.profile)
            )
            _print_json(service.runtime_capability_matrix(profile))
            return 0

        if args.command == "preflight-references":
            plan = VisualGenerationPlan.from_json(_read_text(args.plan))
            catalog = ReferenceCatalog.from_json(_read_text(args.catalog))
            preflight_reference_images(plan, catalog)
            _print_json({
                "status": "PASS",
                "project_id": plan.project_id,
                "reference_count": len({
                    asset_id
                    for request in plan.requests
                    for asset_id in request.reference_asset_ids
                }),
                "provider_called": False,
            })
            return 0

        if args.command == "run-runtime":
            profile = RuntimeProfile.from_json(
                _read_text(args.profile)
            )
            state = service.run_runtime_stage(
                args.workflow_id,
                profile,
                confirm_external=args.confirm_external,
                confirm_paid=args.confirm_paid,
            )
            _print_json(state.to_dict())
            return 0

        if args.command == "review":
            state = service.record_review_decision(
                args.workflow_id,
                reviewer_id=args.reviewer_id,
                action=args.action,
                comments=args.comments,
                target_shot_id=args.target_shot_id,
                decision_id=args.decision_id,
                decided_at=args.decided_at,
            )
            _print_json(state.to_dict())
            return 0

        if args.command == "publish-dry-run":
            request = PublishRequest.from_json(
                _read_text(args.request)
            )
            policy = PublishingPolicy.from_json(
                _read_text(args.policy)
            )
            state = service.prepare_publish_dry_run(
                args.workflow_id,
                request=request,
                policy=policy,
                recorded_at=args.recorded_at,
            )
            _print_json(state.to_dict())
            return 0

        if args.command == "release":
            candidate = service.build_release_candidate(
                args.workflow_id
            )
            _print_json(candidate.to_dict())
            return 0

    except (DomainValidationError, OSError, UnicodeError, ValueError) as exc:
        parser.exit(2, f"error: {exc}\n")

    parser.error(f"unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
