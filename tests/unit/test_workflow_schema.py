import unittest

from eap.protocol import (
    BranchingRule,
    PersistedWorkflowGraph,
    ToolCall,
    WorkflowEdgeKind,
    WorkflowGraphEdge,
    WorkflowGraphNode,
)


class WorkflowSchemaTest(unittest.TestCase):
    def test_graph_compiles_to_macro_request(self) -> None:
        graph = PersistedWorkflowGraph(
            workflow_id="wf_1",
            nodes=[
                WorkflowGraphNode(
                    node_id="node_1",
                    step=ToolCall(step_id="step_1", tool_name="tool_a", arguments={}),
                ),
                WorkflowGraphNode(
                    node_id="node_2",
                    step=ToolCall(
                        step_id="step_2",
                        tool_name="tool_b",
                        arguments={},
                        branching=BranchingRule(
                            condition="result == 'ok'",
                            true_target_step_ids=["step_3"],
                        ),
                    ),
                ),
                WorkflowGraphNode(
                    node_id="node_3",
                    step=ToolCall(step_id="step_3", tool_name="tool_c", arguments={}),
                ),
            ],
            edges=[
                WorkflowGraphEdge(
                    source_node_id="node_1",
                    target_node_id="node_2",
                    kind=WorkflowEdgeKind.DEPENDENCY,
                ),
                WorkflowGraphEdge(
                    source_node_id="node_2",
                    target_node_id="node_3",
                    kind=WorkflowEdgeKind.DEPENDENCY,
                ),
                WorkflowGraphEdge(
                    source_node_id="node_2",
                    target_node_id="node_3",
                    kind=WorkflowEdgeKind.BRANCH_TRUE,
                ),
            ],
        )

        macro = graph.to_batched_macro_request()
        self.assertEqual([step.step_id for step in macro.steps], ["step_1", "step_2", "step_3"])
        self.assertEqual(macro.steps[1].branching.true_target_step_ids, ["step_3"])

    def test_dependency_cycle_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            PersistedWorkflowGraph(
                workflow_id="wf_cycle",
                nodes=[
                    WorkflowGraphNode(
                        node_id="node_a",
                        step=ToolCall(step_id="step_a", tool_name="tool_a", arguments={}),
                    ),
                    WorkflowGraphNode(
                        node_id="node_b",
                        step=ToolCall(step_id="step_b", tool_name="tool_b", arguments={}),
                    ),
                ],
                edges=[
                    WorkflowGraphEdge(
                        source_node_id="node_a",
                        target_node_id="node_b",
                        kind=WorkflowEdgeKind.DEPENDENCY,
                    ),
                    WorkflowGraphEdge(
                        source_node_id="node_b",
                        target_node_id="node_a",
                        kind=WorkflowEdgeKind.DEPENDENCY,
                    ),
                ],
            )

    def test_branch_edge_requires_branching_metadata(self) -> None:
        with self.assertRaises(ValueError):
            PersistedWorkflowGraph(
                workflow_id="wf_branch_missing",
                nodes=[
                    WorkflowGraphNode(
                        node_id="node_a",
                        step=ToolCall(step_id="step_a", tool_name="tool_a", arguments={}),
                    ),
                    WorkflowGraphNode(
                        node_id="node_b",
                        step=ToolCall(step_id="step_b", tool_name="tool_b", arguments={}),
                    ),
                ],
                edges=[
                    WorkflowGraphEdge(
                        source_node_id="node_a",
                        target_node_id="node_b",
                        kind=WorkflowEdgeKind.BRANCH_TRUE,
                    ),
                ],
            )

    def test_branch_edges_must_match_branch_targets(self) -> None:
        with self.assertRaises(ValueError):
            PersistedWorkflowGraph(
                workflow_id="wf_branch_mismatch",
                nodes=[
                    WorkflowGraphNode(
                        node_id="node_a",
                        step=ToolCall(
                            step_id="step_a",
                            tool_name="tool_a",
                            arguments={},
                            branching=BranchingRule(
                                condition="x > 0",
                                true_target_step_ids=["step_b"],
                            ),
                        ),
                    ),
                    WorkflowGraphNode(
                        node_id="node_b",
                        step=ToolCall(step_id="step_b", tool_name="tool_b", arguments={}),
                    ),
                ],
                edges=[],
            )


if __name__ == "__main__":
    unittest.main()
