# app.py
import streamlit as st
import asyncio
import json
import os
import re
import time
import pandas as pd
import sqlite3
from pydantic import ValidationError

from eap.protocol import (
    BatchedMacroRequest,
    BranchingRule,
    StateManager,
    ToolCall,
    WorkflowEdgeKind,
    WorkflowGraphEdge,
    WorkflowGraphNode,
    configure_logging,
    load_settings,
)
from eap.environment import AsyncLocalExecutor, ToolRegistry
from eap.environment.tools import (
    read_local_file, READ_FILE_SCHEMA, 
    analyze_data, ANALYZE_SCHEMA,
    scrape_url, SCRAPE_SCHEMA
)
from eap.agent import AgentClient, WorkflowGraphCompiler

# Central logging config for app + runtime modules.
configure_logging()
settings = load_settings()

# --- Page Config ---
st.set_page_config(page_title="EAP Dashboard", layout="wide", page_icon="⚡")

# --- Initialize Backend ---
@st.cache_resource
def get_backend():
    state_manager = StateManager()
    registry = ToolRegistry()
    registry.register("read_local_file", read_local_file, READ_FILE_SCHEMA)
    registry.register("analyze_data", analyze_data, ANALYZE_SCHEMA)
    registry.register("scrape_url", scrape_url, SCRAPE_SCHEMA)
    executor = AsyncLocalExecutor(state_manager, registry)
    return state_manager, registry, executor

state_manager, registry, executor = get_backend()


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_positive_int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def run_pointer_janitor_if_due() -> dict:
    enabled = _env_bool("EAP_POINTER_JANITOR_ENABLED", True)
    if not enabled:
        return {"status": "disabled"}

    interval_seconds = _env_positive_int("EAP_POINTER_JANITOR_INTERVAL_SECONDS", 300)
    max_delete = _env_positive_int("EAP_POINTER_JANITOR_MAX_DELETE", 200)
    now_seconds = time.time()
    last_run = st.session_state.get("pointer_janitor_last_run", 0.0)

    if (now_seconds - last_run) < interval_seconds:
        return st.session_state.get(
            "pointer_janitor_last_report",
            {"status": "skipped", "reason": "interval_not_elapsed"},
        )

    report = state_manager.cleanup_expired_pointers(limit=max_delete)
    report["status"] = "ran"
    report["interval_seconds"] = interval_seconds
    report["max_delete"] = max_delete
    st.session_state["pointer_janitor_last_run"] = now_seconds
    st.session_state["pointer_janitor_last_report"] = report
    return report


janitor_report = run_pointer_janitor_if_due()


def extract_pointer_ids(text: str):
    return sorted(set(re.findall(r"ptr_[a-zA-Z0-9]+", text or "")))


def build_memory_context(session_id: str, max_chars: int = 2500, default_max_turns: int = 8) -> str:
    session = state_manager.get_session(session_id)
    turns = state_manager.list_turns(session_id)
    strategy = session["memory_strategy"]
    selected_turns = turns

    if strategy == "window":
        window_limit = session.get("window_turn_limit") or default_max_turns
        selected_turns = turns[-window_limit:]
    elif strategy == "summary":
        selected_turns = turns[-4:]

    lines = []
    if strategy == "summary" and session.get("summary_text"):
        lines.append(f"[summary] {session['summary_text']}")

    # Keep memory compact by clipping turn content and tail-trimming by max chars.
    for turn in selected_turns:
        clipped = turn["content"][:280]
        line = f"[{turn['role']}] {clipped}"
        if turn.get("pointer_ids"):
            line += f" | pointers: {', '.join(turn['pointer_ids'])}"
        lines.append(line)

    context = "\n".join(lines)
    if len(context) > max_chars:
        context = context[-max_chars:]
    return context


def _parse_csv_step_ids(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def _sync_branch_edges(nodes: list[dict], edges: list[dict]) -> tuple[list[dict], list[str]]:
    """Align branch edges with per-step branching target IDs when targets exist."""
    node_by_step_id = {
        node["step"]["step_id"]: node["node_id"]
        for node in nodes
        if node.get("step", {}).get("step_id")
    }
    non_branch_edges = [
        edge
        for edge in edges
        if edge.get("kind") == WorkflowEdgeKind.DEPENDENCY.value
    ]
    warnings: list[str] = []
    synced_branch_edges: list[dict] = []

    for node in nodes:
        branching = node.get("step", {}).get("branching")
        if not branching:
            continue
        source_node_id = node["node_id"]
        mapping = [
            (WorkflowEdgeKind.BRANCH_TRUE.value, branching.get("true_target_step_ids", [])),
            (WorkflowEdgeKind.BRANCH_FALSE.value, branching.get("false_target_step_ids", [])),
            (WorkflowEdgeKind.BRANCH_FALLBACK.value, branching.get("fallback_target_step_ids", [])),
        ]
        for kind, step_ids in mapping:
            for target_step_id in step_ids:
                target_node_id = node_by_step_id.get(target_step_id)
                if target_node_id is None:
                    warnings.append(
                        f"Branch target step_id `{target_step_id}` has no matching node yet."
                    )
                    continue
                synced_branch_edges.append(
                    {
                        "source_node_id": source_node_id,
                        "target_node_id": target_node_id,
                        "kind": kind,
                    }
                )

    deduped = []
    seen = set()
    for edge in [*non_branch_edges, *synced_branch_edges]:
        key = (edge["source_node_id"], edge["target_node_id"], edge["kind"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(edge)
    return deduped, warnings

# --- Sidebar: History & Control ---
st.sidebar.header("🗄️ Pointer Vault")

def get_vault_data():
    pointers = state_manager.list_pointers(include_expired=True, limit=200)
    if not pointers:
        return pd.DataFrame()
    rows = []
    for item in pointers:
        rows.append(
            {
                "pointer_id": item["pointer_id"],
                "summary": item["summary"],
                "size_bytes": item.get("metadata", {}).get("size_bytes"),
                "created_at_utc": item.get("created_at_utc"),
                "ttl_seconds": item.get("ttl_seconds"),
                "expires_at_utc": item.get("expires_at_utc"),
                "is_expired": item.get("is_expired"),
            }
        )
    return pd.DataFrame(rows)

vault_df = get_vault_data()
if not vault_df.empty:
    st.sidebar.dataframe(vault_df, hide_index=True)
else:
    st.sidebar.info("Vault is currently empty.")

if janitor_report.get("status") == "ran" and janitor_report.get("deleted_count", 0) > 0:
    st.sidebar.success(
        f"Janitor removed {janitor_report['deleted_count']} expired pointer(s)."
    )
elif janitor_report.get("status") == "ran":
    st.sidebar.caption("Janitor ran: no expired pointers deleted.")

if st.sidebar.button("🧹 Cleanup Expired Pointers", help="Manually remove expired pointers from the vault."):
    manual_limit = _env_positive_int("EAP_POINTER_JANITOR_MAX_DELETE", 200)
    manual_report = state_manager.cleanup_expired_pointers(limit=manual_limit)
    st.session_state["pointer_janitor_last_report"] = manual_report
    st.session_state["pointer_janitor_last_run"] = time.time()
    st.sidebar.success(f"Deleted {manual_report['deleted_count']} expired pointer(s).")
    st.rerun()

# --- THE NEW CLEAR BUTTON ---
st.sidebar.markdown("---")
if st.sidebar.button("🗑️ Clear All Data", help="Wipe the SQLite database and clear chat history."):
    state_manager.clear_all()
    st.session_state.messages = []
    st.sidebar.success("Vault Cleared!")
    st.rerun()

# --- Main Layout: Tabs ---
st.title("⚡ Efficient Agent Protocol")
tab1, tab2, tab3, tab4 = st.tabs(
    ["💬 Agent Chat", "🔍 Data Inspector", "📈 Execution Trace", "🧩 DAG Builder"]
)

# --- TAB 1: Agent Chat ---
with tab1:
    sessions = state_manager.list_sessions(limit=100)
    session_ids = [item["session_id"] for item in sessions]
    sessions_by_id = {item["session_id"]: item for item in sessions}
    if not session_ids:
        created = state_manager.create_session()
        session_ids = [created["session_id"]]
        sessions_by_id = {created["session_id"]: created}

    if "active_session_id" not in st.session_state or st.session_state.active_session_id not in session_ids:
        st.session_state.active_session_id = session_ids[0]

    selector_col, create_col, delete_col = st.columns([6, 2, 2])
    with selector_col:
        selected_session_id = st.selectbox(
            "Conversation Session",
            options=session_ids,
            index=session_ids.index(st.session_state.active_session_id),
            format_func=lambda sid: f"{sid} ({sessions_by_id[sid]['memory_strategy']})",
        )
    st.session_state.active_session_id = selected_session_id

    with create_col:
        if st.button("New Session"):
            new_session = state_manager.create_session()
            st.session_state.active_session_id = new_session["session_id"]
            st.rerun()

    with delete_col:
        if st.button("Delete Session"):
            state_manager.delete_session(st.session_state.active_session_id)
            remaining = state_manager.list_sessions(limit=100)
            if not remaining:
                created = state_manager.create_session()
                st.session_state.active_session_id = created["session_id"]
            else:
                st.session_state.active_session_id = remaining[0]["session_id"]
            st.rerun()

    turns = state_manager.list_turns(st.session_state.active_session_id)
    message_history = [
        {"role": turn["role"], "content": turn["content"]}
        for turn in turns
        if turn["role"] in {"user", "assistant"}
    ]
    for message in message_history:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if user_query := st.chat_input("Analyze something..."):
        state_manager.append_turn(
            session_id=st.session_state.active_session_id,
            role="user",
            content=user_query,
            pointer_ids=extract_pointer_ids(user_query),
        )
        with st.chat_message("user"):
            st.markdown(user_query)

        with st.chat_message("assistant"):
            status_col, audit_col = st.columns(2)

            # ARCHITECT
            with status_col:
                with st.status("🏗️ Architect Drafting...", expanded=True) as s:
                    architect = AgentClient(
                        base_url=settings.architect.base_url,
                        model_name=settings.architect.model_name,
                        api_key=settings.architect.api_key,
                        temperature=settings.architect.temperature,
                        timeout_seconds=settings.architect.timeout_seconds,
                        openai_api_mode=settings.architect.openai_api_mode,
                        extra_headers=settings.architect.extra_headers,
                        system_prompt="You are the ARCHITECT. Create efficient tool-calling macros."
                    )
                    hashed_names = registry.get_hashed_manifest()
                    full_schemas = registry.get_full_schemas()
                    agent_manifest = {v: full_schemas[k]["parameters"] for k, v in hashed_names.items()}
                    memory_context = build_memory_context(st.session_state.active_session_id)
                    macro = architect.generate_macro(
                        user_query,
                        agent_manifest,
                        memory_context=memory_context,
                    )
                    st.code(macro.model_dump_json(indent=2), language="json")
                    s.update(label="✅ Macro Ready", state="complete")

            # AUDITOR
            with audit_col:
                with st.status("🛡️ Auditor Reviewing...", expanded=True) as s:
                    auditor = AgentClient(
                        base_url=settings.auditor.base_url,
                        model_name=settings.auditor.model_name,
                        api_key=settings.auditor.api_key,
                        temperature=settings.auditor.temperature,
                        timeout_seconds=settings.auditor.timeout_seconds,
                        openai_api_mode=settings.auditor.openai_api_mode,
                        extra_headers=settings.auditor.extra_headers,
                        system_prompt="Review for safety. Respond APPROVED or DENIED."
                    )
                    review_prompt = f"Review: {macro.model_dump_json()}"
                    streamed = {"text": ""}
                    decision_placeholder = st.empty()

                    def on_audit_token(token: str) -> None:
                        streamed["text"] += token
                        decision_placeholder.markdown(f"**Decision (streaming):** {streamed['text']}")

                    audit_decision = auditor.stream_chat(review_prompt, on_token=on_audit_token)
                    decision_placeholder.markdown(f"**Decision:** {audit_decision}")
                    s.update(label=f"🛡️ Audit: {audit_decision}", state="complete")

            # EXECUTOR
            if "APPROVED" in audit_decision.upper():
                with st.status("🚀 Executing DAG...", expanded=True) as s:
                    result = asyncio.run(executor.execute_macro(macro))
                    st.json(result)
                    s.update(label="✅ Execution Done", state="complete")
                    st.success(f"Final Pointer: `{result['pointer_id']}`")
                    assistant_message = f"Task complete. Result stored in `{result['pointer_id']}`."
                    state_manager.append_turn(
                        session_id=st.session_state.active_session_id,
                        role="assistant",
                        content=assistant_message,
                        pointer_ids=[result["pointer_id"]],
                        macro_run_id=result.get("metadata", {}).get("execution_run_id"),
                    )
                    st.rerun() 
            else:
                st.error("Audit Failed. Execution Blocked.")
                state_manager.append_turn(
                    session_id=st.session_state.active_session_id,
                    role="assistant",
                    content="Audit failed. Execution blocked.",
                )

# --- TAB 2: Data Inspector ---
with tab2:
    st.header("🕵️ Pointer Inspector")
    if not vault_df.empty:
        target_ptr = st.selectbox("Select a Pointer to Inspect:", vault_df["pointer_id"])
        
        if target_ptr:
            with sqlite3.connect("agent_state.db") as conn:
                cursor = conn.execute(
                    """
                    SELECT raw_data, summary, metadata, created_at_utc, ttl_seconds, expires_at_utc
                    FROM state_store
                    WHERE pointer_id = ?
                    """,
                    (target_ptr,),
                )
                row = cursor.fetchone()
                
                if row:
                    raw_content, summary, meta_json, created_at_utc, ttl_seconds, expires_at_utc = row
                    meta = json.loads(meta_json)
                    
                    c1, c2 = st.columns([1, 3])
                    with c1:
                        st.metric("Payload Size", f"{meta.get('size_bytes', 0):,} bytes")
                        st.write(f"**Agent Summary:** {summary}")
                        st.write(f"**Created:** {created_at_utc}")
                        st.write(f"**TTL (seconds):** {ttl_seconds}")
                        st.write(f"**Expires:** {expires_at_utc}")
                    
                    with c2:
                        st.subheader("Persistent Raw Content")
                        st.code(raw_content, language="markdown")

                    actions_col1, actions_col2 = st.columns(2)
                    with actions_col1:
                        if st.button("Delete Selected Pointer", use_container_width=True):
                            state_manager.delete_pointer(target_ptr)
                            st.success(f"Deleted pointer `{target_ptr}`.")
                            st.rerun()
                    with actions_col2:
                        if st.button("Cleanup Expired Now", use_container_width=True):
                            cleanup_report = state_manager.cleanup_expired_pointers(
                                limit=_env_positive_int("EAP_POINTER_JANITOR_MAX_DELETE", 200)
                            )
                            st.info(
                                f"Cleanup deleted {cleanup_report['deleted_count']} expired pointer(s). "
                                f"Remaining expired: {cleanup_report['remaining_expired_count']}."
                            )
                            st.rerun()
    else:
        st.warning("No data found. Run a task to fill the vault.")

# --- TAB 3: Execution Trace ---
with tab3:
    st.header("📈 Execution Trace Explorer")

    def get_trace_runs():
        if not os.path.exists("agent_state.db"):
            return pd.DataFrame()
        with sqlite3.connect("agent_state.db") as conn:
            try:
                return pd.read_sql_query(
                    """
                    SELECT run_id, started_at_utc, completed_at_utc, total_steps, succeeded_steps,
                           failed_steps, total_duration_ms, final_pointer_id
                    FROM execution_run_summaries
                    ORDER BY completed_at_utc DESC
                    """,
                    conn,
                )
            except Exception:
                return pd.DataFrame()

    trace_runs_df = get_trace_runs()
    if trace_runs_df.empty:
        st.info("No trace runs found yet. Execute a macro to generate traces.")
    else:
        selected_run = st.selectbox("Select execution run:", trace_runs_df["run_id"])
        summary_row = trace_runs_df[trace_runs_df["run_id"] == selected_run].iloc[0]
        events = state_manager.list_trace_events(selected_run)

        event_rows = []
        for event in events:
            error_type = event.error.error_type if event.error else None
            error_message = event.error.message if event.error else None
            event_rows.append(
                {
                    "timestamp_utc": event.timestamp_utc.isoformat(),
                    "step_id": event.step_id,
                    "tool_name": event.tool_name,
                    "event_type": event.event_type.value,
                    "attempt": event.attempt,
                    "duration_ms": event.duration_ms,
                    "output_pointer_id": event.output_pointer_id,
                    "error_type": error_type,
                    "error_message": error_message,
                }
            )
        events_df = pd.DataFrame(event_rows)

        completed_df = events_df[events_df["event_type"] == "completed"]
        retry_count = int((events_df["event_type"] == "retried").sum())
        failed_count = int((events_df["event_type"] == "failed").sum())
        total_step_duration_ms = float(completed_df["duration_ms"].fillna(0).sum()) if not completed_df.empty else 0.0
        total_duration_ms = float(summary_row["total_duration_ms"]) if summary_row["total_duration_ms"] else 0.0
        parallelism_ratio = (total_step_duration_ms / total_duration_ms) if total_duration_ms > 0 else 0.0

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Runtime", f"{total_duration_ms:.1f} ms")
        m2.metric("Steps", f"{int(summary_row['succeeded_steps'])}/{int(summary_row['total_steps'])} succeeded")
        m3.metric("Retries", f"{retry_count}")
        m4.metric("Parallelism Ratio", f"{parallelism_ratio:.2f}x")

        st.caption(
            f"Run window: {summary_row['started_at_utc']} -> {summary_row['completed_at_utc']} | "
            f"Final Pointer: {summary_row['final_pointer_id']} | Failed events: {failed_count}"
        )

        event_type_options = sorted(events_df["event_type"].unique().tolist())
        step_options = sorted(events_df["step_id"].unique().tolist())
        selected_event_types = st.multiselect(
            "Filter event types",
            options=event_type_options,
            default=event_type_options,
        )
        selected_steps = st.multiselect(
            "Filter steps",
            options=step_options,
            default=step_options,
        )

        filtered_df = events_df[
            events_df["event_type"].isin(selected_event_types)
            & events_df["step_id"].isin(selected_steps)
        ]

        st.subheader("Event Timeline")
        st.dataframe(filtered_df, hide_index=True, use_container_width=True)

        if not completed_df.empty:
            st.subheader("Per-Step Duration (Completed Events)")
            st.bar_chart(completed_df.set_index("step_id")["duration_ms"])

        failure_rows = filtered_df[filtered_df["event_type"].isin(["retried", "failed"])]
        if not failure_rows.empty:
            st.subheader("Retry / Failure Details")
            st.dataframe(
                failure_rows[
                    ["timestamp_utc", "step_id", "event_type", "attempt", "error_type", "error_message"]
                ],
                hide_index=True,
                use_container_width=True,
            )

# --- TAB 4: DAG Builder ---
with tab4:
    st.header("🧩 Workflow DAG Builder (MVP)")
    st.caption("Create/edit nodes, edges, and tool step parameters, then compile to an executable macro.")

    tool_names = sorted(registry.get_hashed_manifest().keys())
    if "builder_workflow_id" not in st.session_state:
        st.session_state["builder_workflow_id"] = "wf_mvp"
    if "builder_nodes" not in st.session_state:
        st.session_state["builder_nodes"] = []
    if "builder_edges" not in st.session_state:
        st.session_state["builder_edges"] = []

    st.session_state["builder_workflow_id"] = st.text_input(
        "Workflow ID",
        value=st.session_state["builder_workflow_id"],
    )
    return_final_state_only = st.checkbox(
        "Return Final State Only",
        value=True,
        help="Compile the graph into a macro that returns only the final step pointer.",
    )

    with st.expander("Add or Update Node", expanded=True):
        with st.form("builder_node_form"):
            node_id = st.text_input("Node ID", value="")
            step_id = st.text_input("Step ID", value="")
            default_tool = tool_names[0] if tool_names else ""
            if tool_names:
                tool_name = st.selectbox("Tool Name", options=tool_names, index=0)
            else:
                st.caption("No tools available in registry.")
                tool_name = ""
            arguments_raw = st.text_area("Arguments JSON", value="{}", height=120)
            branch_condition = st.text_input("Branch Condition (optional)", value="")
            true_targets_raw = st.text_input("True Target Step IDs (comma-separated)", value="")
            false_targets_raw = st.text_input("False Target Step IDs (comma-separated)", value="")
            fallback_targets_raw = st.text_input("Fallback Target Step IDs (comma-separated)", value="")
            node_label = st.text_input("Node Label (optional)", value="")
            position_x = st.number_input("Canvas X", value=0.0)
            position_y = st.number_input("Canvas Y", value=0.0)
            submit_node = st.form_submit_button("Save Node")

            if submit_node:
                if not tool_names:
                    st.error("No tools registered in the runtime registry.")
                elif not node_id.strip() or not step_id.strip():
                    st.error("Node ID and Step ID are required.")
                else:
                    try:
                        arguments = json.loads(arguments_raw)
                        if not isinstance(arguments, dict):
                            raise ValueError("Arguments JSON must be an object.")

                        true_targets = _parse_csv_step_ids(true_targets_raw)
                        false_targets = _parse_csv_step_ids(false_targets_raw)
                        fallback_targets = _parse_csv_step_ids(fallback_targets_raw)
                        has_branching = bool(
                            branch_condition.strip()
                            or true_targets
                            or false_targets
                            or fallback_targets
                        )
                        branching = None
                        if has_branching:
                            branching = BranchingRule(
                                condition=branch_condition.strip() or "branch_condition",
                                true_target_step_ids=true_targets,
                                false_target_step_ids=false_targets,
                                fallback_target_step_ids=fallback_targets,
                            )

                        node_payload = WorkflowGraphNode(
                            node_id=node_id.strip(),
                            step=ToolCall(
                                step_id=step_id.strip(),
                                tool_name=tool_name or default_tool,
                                arguments=arguments,
                                branching=branching,
                            ),
                            label=node_label.strip() or None,
                            position_x=position_x,
                            position_y=position_y,
                        ).model_dump(mode="json")

                        existing = st.session_state["builder_nodes"]
                        remaining = [node for node in existing if node["node_id"] != node_payload["node_id"]]
                        remaining.append(node_payload)
                        st.session_state["builder_nodes"] = sorted(
                            remaining,
                            key=lambda item: item["node_id"],
                        )
                        st.success(f"Saved node `{node_payload['node_id']}`.")
                    except (json.JSONDecodeError, ValidationError, ValueError) as exc:
                        st.error(f"Node validation failed: {exc}")

    current_nodes = st.session_state["builder_nodes"]
    current_edges = st.session_state["builder_edges"]

    with st.expander("Add Edge", expanded=True):
        if len(current_nodes) < 2:
            st.info("Add at least two nodes before creating edges.")
        else:
            node_options = [node["node_id"] for node in current_nodes]
            with st.form("builder_edge_form"):
                source_node_id = st.selectbox("Source Node", options=node_options)
                target_node_candidates = [item for item in node_options if item != source_node_id]
                target_node_id = st.selectbox("Target Node", options=target_node_candidates)
                edge_kind = st.selectbox(
                    "Edge Kind",
                    options=[kind.value for kind in WorkflowEdgeKind],
                    index=0,
                )
                submit_edge = st.form_submit_button("Save Edge")
                if submit_edge:
                    try:
                        edge_payload = WorkflowGraphEdge(
                            source_node_id=source_node_id,
                            target_node_id=target_node_id,
                            kind=WorkflowEdgeKind(edge_kind),
                        ).model_dump(mode="json")
                        edge_key = (
                            edge_payload["source_node_id"],
                            edge_payload["target_node_id"],
                            edge_payload["kind"],
                        )
                        existing_keys = {
                            (edge["source_node_id"], edge["target_node_id"], edge["kind"])
                            for edge in current_edges
                        }
                        if edge_key in existing_keys:
                            st.info("Edge already exists.")
                        else:
                            st.session_state["builder_edges"] = [*current_edges, edge_payload]
                            st.success("Edge saved.")
                    except (ValidationError, ValueError) as exc:
                        st.error(f"Edge validation failed: {exc}")

    st.subheader("Current Nodes")
    if current_nodes:
        node_rows = [
            {
                "node_id": node["node_id"],
                "step_id": node["step"]["step_id"],
                "tool_name": node["step"]["tool_name"],
                "has_branching": bool(node["step"].get("branching")),
            }
            for node in current_nodes
        ]
        st.dataframe(pd.DataFrame(node_rows), hide_index=True, use_container_width=True)
        node_to_delete = st.selectbox(
            "Delete Node",
            options=[""] + [row["node_id"] for row in node_rows],
            format_func=lambda value: value or "Select a node",
        )
        if node_to_delete and st.button("Delete Selected Node", key="delete_builder_node"):
            st.session_state["builder_nodes"] = [
                node for node in current_nodes if node["node_id"] != node_to_delete
            ]
            st.session_state["builder_edges"] = [
                edge
                for edge in current_edges
                if edge["source_node_id"] != node_to_delete and edge["target_node_id"] != node_to_delete
            ]
            st.success(f"Deleted node `{node_to_delete}` and related edges.")
            st.rerun()
    else:
        st.info("No nodes yet.")

    st.subheader("Current Edges")
    if current_edges:
        st.dataframe(pd.DataFrame(current_edges), hide_index=True, use_container_width=True)
        edge_labels = [
            f"{edge['source_node_id']} -> {edge['target_node_id']} ({edge['kind']})"
            for edge in current_edges
        ]
        edge_to_delete = st.selectbox(
            "Delete Edge",
            options=[""] + edge_labels,
            format_func=lambda value: value or "Select an edge",
        )
        if edge_to_delete and st.button("Delete Selected Edge", key="delete_builder_edge"):
            kept_edges = []
            for edge, label in zip(current_edges, edge_labels):
                if label != edge_to_delete:
                    kept_edges.append(edge)
            st.session_state["builder_edges"] = kept_edges
            st.success(f"Deleted edge `{edge_to_delete}`.")
            st.rerun()
    else:
        st.info("No edges yet.")

    compile_col, run_col, reset_col = st.columns(3)
    with compile_col:
        compile_clicked = st.button("Compile Workflow", use_container_width=True)
    with run_col:
        run_clicked = st.button("Run Compiled Macro", use_container_width=True)
    with reset_col:
        if st.button("Reset Builder", use_container_width=True):
            st.session_state["builder_nodes"] = []
            st.session_state["builder_edges"] = []
            st.session_state.pop("builder_compiled_macro", None)
            st.success("Builder reset.")
            st.rerun()

    if compile_clicked:
        try:
            synced_edges, sync_warnings = _sync_branch_edges(
                st.session_state["builder_nodes"],
                st.session_state["builder_edges"],
            )
            for warning in sync_warnings:
                    st.warning(warning)
            st.session_state["builder_edges"] = synced_edges

            graph_payload = {
                "workflow_id": st.session_state["builder_workflow_id"],
                "nodes": st.session_state["builder_nodes"],
                "edges": st.session_state["builder_edges"],
            }
            macro = WorkflowGraphCompiler.compile_to_macro(
                graph_payload,
                return_final_state_only=return_final_state_only,
            )
            st.session_state["builder_compiled_macro"] = macro.model_dump(mode="json")
            st.success("Workflow compiled successfully.")
            st.code(macro.model_dump_json(indent=2), language="json")
        except (ValidationError, ValueError) as exc:
            st.error(f"Compile failed: {exc}")

    if run_clicked:
        macro_payload = st.session_state.get("builder_compiled_macro")
        if not macro_payload:
            st.error("Compile a workflow first.")
        else:
            try:
                macro = BatchedMacroRequest(**macro_payload)
                result = asyncio.run(executor.execute_macro(macro))
                st.success(f"Execution complete. Final pointer: `{result['pointer_id']}`")
                st.json(result)
            except Exception as exc:  # pragma: no cover - runtime execution failures depend on tool inputs
                st.error(f"Execution failed: {exc}")
