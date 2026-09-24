"""Streamlit Operator Console for governed Content Studio workflows."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import streamlit as st

root_dir = Path(__file__).resolve().parents[2]
if str(root_dir) in sys.path:
    sys.path.remove(str(root_dir))
sys.path.insert(0, str(root_dir))

from extensions.content_studio.domain import DomainValidationError  # noqa: E402
from extensions.content_studio.orchestration import (  # noqa: E402
    StageExecutionResult,
)
from extensions.content_studio.publishing import (  # noqa: E402
    PublishingPolicy,
    PublishRequest,
)
from extensions.content_studio.review import ReviewPackage  # noqa: E402
from extensions.operator_console.service import (  # noqa: E402
    OperatorConsoleService,
)

st.set_page_config(
    page_title="Content Studio — Operator Console",
    page_icon="🎬",
    layout="wide",
)

WORKFLOW_DIR = os.getenv(
    "CONTENT_STUDIO_WORKFLOW_DIR",
    str(root_dir / "output" / "content_studio" / "workflows"),
)
REVIEW_DIR = os.getenv(
    "CONTENT_STUDIO_REVIEW_LOG_DIR",
    str(root_dir / "output" / "content_studio" / "review_audit"),
)
PUBLICATION_DIR = os.getenv(
    "CONTENT_STUDIO_PUBLICATION_LOG_DIR",
    str(root_dir / "output" / "content_studio" / "publication_audit"),
)

service = OperatorConsoleService(
    workflow_dir=WORKFLOW_DIR,
    review_audit_dir=REVIEW_DIR,
    publication_audit_dir=PUBLICATION_DIR,
)


def _rerun() -> None:
    st.rerun()


def _uploaded_text(uploaded) -> str:
    return uploaded.getvalue().decode("utf-8")


st.title("Content Studio — Operator Console")
st.caption(
    "Operate checkpointed episode workflows through governed actions. "
    "Live publication is not available in this console."
)

with st.sidebar:
    st.subheader("Workflow storage")
    st.caption(WORKFLOW_DIR)

    with st.expander("Create workflow"):
        with st.form("create-workflow"):
            workflow_id = st.text_input("Workflow ID")
            project_id = st.text_input("Project ID")
            episode_id = st.text_input("Episode ID")
            max_cost_text = st.text_input(
                "Maximum cost USD",
                placeholder="optional, e.g. 5.00",
            )
            create = st.form_submit_button(
                "Create",
                use_container_width=True,
            )
        if create:
            try:
                max_cost = (
                    float(max_cost_text)
                    if max_cost_text.strip()
                    else None
                )
                service.create_workflow(
                    workflow_id=workflow_id.strip(),
                    project_id=project_id.strip(),
                    episode_id=episode_id.strip(),
                    max_cost_usd=max_cost,
                )
            except (ValueError, DomainValidationError) as exc:
                st.error(str(exc))
            else:
                st.success("Workflow created.")
                _rerun()

    try:
        workflow_ids = service.list_workflow_ids()
    except DomainValidationError as exc:
        st.error(f"Checkpoint error: {exc}")
        st.stop()

    if not workflow_ids:
        st.info("No workflows found.")
        st.stop()

    selected = st.selectbox("Workflow", workflow_ids)

try:
    state = service.load_workflow(selected)
    summary = service.summarize(selected)
except DomainValidationError as exc:
    st.error(str(exc))
    st.stop()

metrics = st.columns(5)
metrics[0].metric("Revision", summary.revision)
metrics[1].metric("Next stage", summary.next_stage or "COMPLETE")
metrics[2].metric("Spent USD", f"{summary.spent_cost_usd:.4f}")
metrics[3].metric(
    "Budget USD",
    "unbounded"
    if summary.max_cost_usd is None
    else f"{summary.max_cost_usd:.4f}",
)
metrics[4].metric(
    "Artifacts",
    summary.active_artifact_count,
)

st.subheader("Pipeline")
st.dataframe(
    list(summary.stage_rows),
    use_container_width=True,
    hide_index=True,
)

if summary.complete:
    st.success(
        "Workflow complete. Release Candidate can be generated below."
    )
elif summary.next_stage == "human_review":
    st.warning("Workflow is waiting for explicit human review.")
elif summary.next_stage == "publish_dry_run":
    st.info("Human review passed. Publish dry-run is ready.")
else:
    st.info(f"Next governed stage: {summary.next_stage}")

tab_actions, tab_artifacts, tab_state = st.tabs(
    ["Actions", "Artifacts", "Raw state"]
)

with tab_actions:
    next_stage = summary.next_stage

    if (
        next_stage is not None
        and next_stage not in {"human_review", "publish_dry_run"}
    ):
        st.subheader("Apply canonical stage result")
        st.caption(
            "Upload a StageExecutionResult for the exact next stage. "
            "The EpisodeOrchestrator will validate cross-stage traceability."
        )
        stage_result_file = st.file_uploader(
            "StageExecutionResult JSON",
            type=["json"],
            key="stage-result",
        )
        stage_bundle_file = st.file_uploader(
            "Optional stage bundle JSON array",
            type=["json"],
            key="stage-bundle",
            help=(
                "Apply sequential canonical results until the bundle ends "
                "or a governed/failed stage stops progress."
            ),
        )
        if st.button(
            "Apply stage bundle",
            disabled=stage_bundle_file is None,
            use_container_width=True,
        ):
            try:
                decoded = __import__("json").loads(
                    _uploaded_text(stage_bundle_file)
                )
                if not isinstance(decoded, list):
                    raise DomainValidationError(
                        "stage bundle JSON must be an array"
                    )
                results = tuple(
                    StageExecutionResult.from_dict(item)
                    for item in decoded
                )
                service.apply_stage_results(selected, results)
            except (
                UnicodeDecodeError,
                ValueError,
                DomainValidationError,
            ) as exc:
                st.error(str(exc))
            else:
                st.success("Stage bundle processed.")
                _rerun()

        if st.button(
            f"Apply result to {next_stage}",
            disabled=stage_result_file is None,
            use_container_width=True,
        ):
            try:
                result = StageExecutionResult.from_json(
                    _uploaded_text(stage_result_file)
                )
                service.apply_stage_result(selected, result)
            except (UnicodeDecodeError, DomainValidationError) as exc:
                st.error(str(exc))
            else:
                st.success("Stage processed and checkpoint saved.")
                _rerun()

    elif next_stage == "human_review":
        package = state.require_one("ReviewPackage")
        if not isinstance(package, ReviewPackage):
            st.error("Active ReviewPackage is invalid.")
            st.stop()

        st.subheader("Human review")
        cols = st.columns(4)
        cols[0].metric(
            "Safety complete",
            "YES" if package.gate.safety_complete else "NO",
        )
        cols[1].metric(
            "Safety blocked",
            "YES" if package.gate.safety_blocked else "NO",
        )
        cols[2].metric(
            "Render QA",
            "PASS" if package.gate.render_qa_passed else "FAIL",
        )
        cols[3].metric(
            "Eligible",
            "YES"
            if package.gate.eligible_for_human_review
            else "NO",
        )

        render_path = Path(package.render_uri)
        if package.render_uri.startswith(("https://", "http://")):
            st.video(package.render_uri)
        elif render_path.is_file():
            st.video(str(render_path))
        else:
            st.caption(
                f"Render URI not available locally: {package.render_uri}"
            )

        reviewer_id = st.text_input("Reviewer ID")
        comments = st.text_area("Decision notes")
        action = st.selectbox(
            "Action",
            (
                "approve",
                "reject",
                "regenerate_shot",
                "regenerate_episode",
            ),
        )
        target_shot = None
        if action == "regenerate_shot":
            target_shot = st.selectbox(
                "Target shot",
                package.shot_ids,
            )

        approval_disabled = (
            action == "approve"
            and not package.gate.eligible_for_human_review
        )
        if approval_disabled:
            st.warning(
                "Approve is disabled because HumanReviewGate is not eligible."
            )

        if st.button(
            "Record human decision",
            type="primary",
            disabled=approval_disabled,
            use_container_width=True,
        ):
            try:
                service.record_review_decision(
                    selected,
                    reviewer_id=reviewer_id.strip(),
                    action=action,
                    comments=comments.strip(),
                    target_shot_id=target_shot,
                )
            except DomainValidationError as exc:
                st.error(str(exc))
            else:
                st.success("Human decision audited and applied.")
                _rerun()

    elif next_stage == "publish_dry_run":
        st.subheader("Publish dry-run")
        st.caption(
            "This action validates publication through the governed gateway. "
            "It cannot call a live publisher."
        )
        request_file = st.file_uploader(
            "PublishRequest JSON",
            type=["json"],
            key="publish-request",
        )
        policy_file = st.file_uploader(
            "PublishingPolicy JSON",
            type=["json"],
            key="publish-policy",
        )
        if st.button(
            "Run publish dry-run",
            type="primary",
            disabled=request_file is None or policy_file is None,
            use_container_width=True,
        ):
            try:
                request = PublishRequest.from_json(
                    _uploaded_text(request_file)
                )
                policy = PublishingPolicy.from_json(
                    _uploaded_text(policy_file)
                )
                service.prepare_publish_dry_run(
                    selected,
                    request=request,
                    policy=policy,
                )
            except (UnicodeDecodeError, DomainValidationError) as exc:
                st.error(str(exc))
            else:
                st.success(
                    "Publish dry-run passed. No live publication occurred."
                )
                _rerun()

    if summary.complete:
        st.subheader("Release Candidate")
        try:
            candidate = service.build_release_candidate(selected)
        except DomainValidationError as exc:
            st.error(str(exc))
        else:
            st.json(candidate.to_dict())
            st.download_button(
                "Download Release Candidate JSON",
                data=candidate.to_json(indent=2),
                file_name=f"{selected}.release-candidate.json",
                mime="application/json",
            )

with tab_artifacts:
    try:
        artifacts = service.active_artifacts(selected)
    except DomainValidationError as exc:
        st.error(str(exc))
    else:
        if not artifacts:
            st.caption("No active PASS artifacts yet.")
        for artifact in artifacts:
            with st.expander(
                f"{artifact.artifact_type} — {artifact.artifact_id}"
            ):
                if artifact.uri:
                    st.caption(artifact.uri)
                st.json(artifact.to_dict())

with tab_state:
    st.json(state.to_dict())

st.caption(
    "Operator Console supports checkpoints, human review, regeneration, "
    "and publish dry-run only. Live publication remains outside this UI."
)
