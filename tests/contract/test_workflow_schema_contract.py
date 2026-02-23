import unittest

from eap.protocol import PersistedWorkflowGraph, WorkflowEdgeKind, WorkflowGraphEdge, WorkflowGraphNode


class WorkflowSchemaContractTest(unittest.TestCase):
    def test_persisted_workflow_graph_contract_fields(self) -> None:
        schema = PersistedWorkflowGraph.model_json_schema()
        self.assertEqual(set(schema["required"]), {"workflow_id", "nodes"})
        self.assertSetEqual(
            set(schema["properties"].keys()),
            {
                "workflow_id",
                "version",
                "nodes",
                "edges",
                "created_at_utc",
                "updated_at_utc",
                "metadata",
            },
        )

    def test_workflow_node_contract_fields(self) -> None:
        schema = WorkflowGraphNode.model_json_schema()
        self.assertEqual(set(schema["required"]), {"node_id", "step"})
        self.assertSetEqual(
            set(schema["properties"].keys()),
            {"node_id", "step", "label", "position_x", "position_y"},
        )

    def test_workflow_edge_contract_fields(self) -> None:
        schema = WorkflowGraphEdge.model_json_schema()
        self.assertEqual(set(schema["required"]), {"source_node_id", "target_node_id"})
        self.assertSetEqual(
            set(schema["properties"].keys()),
            {"source_node_id", "target_node_id", "kind"},
        )

    def test_workflow_edge_kind_values_are_stable(self) -> None:
        self.assertEqual(
            [kind.value for kind in WorkflowEdgeKind],
            ["dependency", "branch_true", "branch_false", "branch_fallback"],
        )


if __name__ == "__main__":
    unittest.main()
