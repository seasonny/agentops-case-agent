"""Case Agent domain — collection, bundle, investigation workflow steps."""

from domain.case.collection_flow import (
    build_file_upload_action,
    build_must_gather_action,
    extract_explicit_file_paths,
    extract_must_gather_artifact_path,
    infer_explicit_upload_analysis,
    infer_must_gather_analysis,
    is_must_gather_request,
    is_sosreport_request,
    is_upload_request,
    process_post_execute_collection,
)
from domain.case.diag_bundle import (
    build_bundle_content,
    build_upload_action,
    bundle_settings,
    is_exec_diag_action,
    should_bundle_outputs,
    write_output_bundle,
)
from domain.case.hooks import CaseDomainHooks
from domain.case.investigation import (
    filter_follow_up_actions,
    investigation_settings,
    serialize_actions,
    should_continue_investigation,
)

__all__ = [
    "CaseDomainHooks",
    "build_bundle_content",
    "build_file_upload_action",
    "build_must_gather_action",
    "build_upload_action",
    "bundle_settings",
    "extract_explicit_file_paths",
    "extract_must_gather_artifact_path",
    "filter_follow_up_actions",
    "infer_explicit_upload_analysis",
    "infer_must_gather_analysis",
    "investigation_settings",
    "is_exec_diag_action",
    "is_must_gather_request",
    "is_sosreport_request",
    "is_upload_request",
    "process_post_execute_collection",
    "serialize_actions",
    "should_bundle_outputs",
    "should_continue_investigation",
    "write_output_bundle",
]
