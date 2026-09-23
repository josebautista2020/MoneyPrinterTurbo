"""Standalone Streamlit Human Review UI for Content Studio AI."""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import streamlit as st

root_dir = Path(__file__).resolve().parents[2]
if str(root_dir) in sys.path:
    sys.path.remove(str(root_dir))
sys.path.insert(0, str(root_dir))

from extensions.content_studio.domain import DomainValidationError  # noqa: E402
from extensions.content_studio.review import (  # noqa: E402
    ReviewDecision,
    ReviewPackage,
    validate_review_decision,
)
from extensions.human_review_ui.store import JsonlReviewDecisionStore  # noqa: E402

st.set_page_config(
    page_title="Content Studio — Human Review",
    page_icon="✅",
    layout="wide",
)

DEFAULT_AUDIT_DIR = os.getenv(
    "CONTENT_STUDIO_REVIEW_LOG_DIR",
    str(root_dir / "output" / "content_studio" / "review_audit"),
)


def _load_package(uploaded) -> ReviewPackage | None:
    if uploaded is None:
        return None
    try:
        return ReviewPackage.from_json(
            uploaded.getvalue().decode("utf-8")
        )
    except (UnicodeDecodeError, DomainValidationError) as exc:
        st.error(f"Invalid review package: {exc}")
        return None


def _record(
    package: ReviewPackage,
    *,
    reviewer_id: str,
    action: str,
    comments: str,
    target_shot_id: str | None = None,
) -> ReviewDecision:
    decision = ReviewDecision(
        decision_id=f"decision-{uuid4().hex}",
        package_id=package.package_id,
        reviewer_id=reviewer_id,
        action=action,
        decided_at=datetime.now(timezone.utc).isoformat(),
        comments=comments,
        target_shot_id=target_shot_id,
        metadata={
            "source": "streamlit-human-review-ui",
            "publication_performed": False,
        },
    )
    validate_review_decision(package, decision)
    store = JsonlReviewDecisionStore(DEFAULT_AUDIT_DIR)
    store.append(decision)
    return decision


st.title("Content Studio — Human Review")
st.caption(
    "Review Safety + QA evidence and record an explicit human decision. "
    "This UI does not publish content."
)

uploaded = st.file_uploader(
    "Review package JSON",
    type=["json"],
    help="Upload a ReviewPackage produced after Safety and Render QA.",
)
package = _load_package(uploaded)

if package is None:
    st.info("Upload a ReviewPackage JSON to begin.")
    st.stop()

gate = package.gate
status_cols = st.columns(4)
status_cols[0].metric(
    "Safety complete",
    "YES" if gate.safety_complete else "NO",
)
status_cols[1].metric(
    "Safety blocked",
    "YES" if gate.safety_blocked else "NO",
)
status_cols[2].metric(
    "Render QA",
    "PASS" if gate.render_qa_passed else "FAIL",
)
status_cols[3].metric(
    "Human review eligible",
    "YES" if gate.eligible_for_human_review else "NO",
)

if gate.missing_safety_modalities:
    st.warning(
        "Missing safety modalities: "
        + ", ".join(gate.missing_safety_modalities)
    )

left, right = st.columns([2, 1])

with left:
    st.subheader("Render candidate")
    render_path = Path(package.render_uri)
    if package.render_uri.startswith(("https://", "http://")):
        st.video(package.render_uri)
    elif render_path.is_file():
        st.video(str(render_path))
    else:
        st.warning(
            "Render URI is not available on this machine: "
            f"{package.render_uri}"
        )

    st.subheader("Render QA")
    qa_rows = [
        {
            "check": check.check_id,
            "status": "PASS" if check.passed else "FAIL",
            "message": check.message,
        }
        for check in package.render_qa.checks
    ]
    st.dataframe(qa_rows, use_container_width=True, hide_index=True)

with right:
    st.subheader("Safety findings")
    findings = [
        {
            "reviewer": assessment.reviewer,
            "severity": finding.severity,
            "category": finding.category,
            "modality": finding.modality,
            "evidence": finding.evidence,
        }
        for assessment in package.safety_assessments
        for finding in assessment.findings
    ]
    if findings:
        st.dataframe(findings, use_container_width=True, hide_index=True)
    else:
        st.success("No Safety findings were recorded.")

    st.subheader("Safety coverage")
    coverage = [
        {
            "reviewer": assessment.reviewer,
            "modalities": ", ".join(assessment.reviewed_modalities),
            "blocking": assessment.has_blocking_findings,
        }
        for assessment in package.safety_assessments
    ]
    st.dataframe(coverage, use_container_width=True, hide_index=True)

st.divider()
st.subheader("Human decision")

reviewer_id = st.text_input(
    "Reviewer ID",
    placeholder="reviewer-name-or-id",
)
comments = st.text_area(
    "Decision notes",
    placeholder="Explain the approval, rejection, or regeneration request.",
)
selected_shot = st.selectbox(
    "Shot for targeted regeneration",
    options=package.shot_ids,
)

buttons = st.columns(4)
approve = buttons[0].button(
    "Approve",
    type="primary",
    disabled=not gate.eligible_for_human_review,
    use_container_width=True,
)
reject = buttons[1].button(
    "Reject",
    use_container_width=True,
)
regen_shot = buttons[2].button(
    "Regenerate shot",
    use_container_width=True,
)
regen_episode = buttons[3].button(
    "Regenerate episode",
    use_container_width=True,
)

action = None
target = None
if approve:
    action = "approve"
elif reject:
    action = "reject"
elif regen_shot:
    action = "regenerate_shot"
    target = selected_shot
elif regen_episode:
    action = "regenerate_episode"

if action is not None:
    if not reviewer_id.strip() or not comments.strip():
        st.error("Reviewer ID and decision notes are required.")
    else:
        try:
            decision = _record(
                package,
                reviewer_id=reviewer_id.strip(),
                action=action,
                comments=comments.strip(),
                target_shot_id=target,
            )
        except DomainValidationError as exc:
            st.error(f"Decision rejected: {exc}")
        else:
            st.success(
                f"Decision recorded: {decision.action} "
                f"({decision.decision_id})"
            )
            st.download_button(
                "Download decision JSON",
                data=decision.to_json(indent=2),
                file_name=f"{decision.decision_id}.json",
                mime="application/json",
            )

st.divider()
st.subheader("Audit trail")
try:
    trail = JsonlReviewDecisionStore(DEFAULT_AUDIT_DIR).list(
        package.package_id
    )
except DomainValidationError as exc:
    st.error(f"Audit trail error: {exc}")
else:
    if not trail.decisions:
        st.caption("No decisions recorded yet.")
    else:
        rows = [
            {
                "decided_at": item.decided_at,
                "reviewer": item.reviewer_id,
                "action": item.action,
                "target_shot": item.target_shot_id or "",
                "comments": item.comments,
                "decision_id": item.decision_id,
            }
            for item in reversed(trail.decisions)
        ]
        st.dataframe(rows, use_container_width=True, hide_index=True)

st.caption(
    "Human approval creates an auditable review decision only. "
    "Publication remains a separate governed action."
)
