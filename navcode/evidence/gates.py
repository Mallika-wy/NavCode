"""Necessary evidence conditions; these checks do not establish semantic truth."""

def transition_gate(report, contract):
    """Necessary conditions only; passing this check does NOT prove correctness."""
    if report["verdict"] != "SUPPORTED":
        return report, None
    if contract["predicate_type"] != "TRANSITION":
        if contract["current_obs_id"] not in report["evidence_obs_ids"]:
            reason = "current-position predicates require current-frame evidence"
            return dict(report, verdict="REFUTED", source_verdict="SUPPORTED",
                        rationale_summary=reason + "; original: " + report["rationale_summary"]), reason
        return report, None
    motion = contract["motion_since_stage"]
    required = {contract["stage_start_obs_id"], contract["current_obs_id"]}
    reason = None
    if motion["forward_commands"] == 0 or motion["forward_with_visual_change"] == 0:
        reason = "transition cannot be established without forward commands and visual change"
    elif len(required) < 2 or not required.issubset(set(report["evidence_obs_ids"])):
        reason = "transition requires both distinct stage-start and current frame evidence"
    if reason:
        return dict(report, verdict="REFUTED", source_verdict="SUPPORTED",
                    rationale_summary=reason + "; original: " + report["rationale_summary"]), reason
    return report, None

def check_stage_order(stage_id, seen_stages, accepted_stages):
    order = list(seen_stages)
    predecessors = order[:order.index(stage_id)] if stage_id in order else order
    missing = [stage for stage in predecessors if stage not in accepted_stages]
    if missing:
        raise ValueError("cannot advance past stages without accepted evidence: " + ", ".join(missing))
