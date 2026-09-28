"""
NetworkX recovery graph.

This graph represents possible recovery strategies for
different categories of errors.
"""

import networkx as nx


def build_recovery_graph():
    """
    Build the recovery strategy graph.
    """

    graph = nx.DiGraph()

    # --------------------------------------------------------
    # Error categories
    # --------------------------------------------------------

    error_types = [
        "syntax_error",
        "dependency_error",
        "database_error",
        "file_error",
        "port_error",
        "configuration_error",
        "unknown_error",
    ]

    for error_type in error_types:

        graph.add_node(
            error_type,
            node_type="error",
        )

    # --------------------------------------------------------
    # Recovery strategies
    # --------------------------------------------------------

    recovery_strategies = [
        "repair_source_code",
        "repair_dependencies",
        "repair_database",
        "repair_file_paths",
        "repair_port_configuration",
        "repair_configuration",
        "analyze_with_gemini",
        "revalidate_project",
    ]

    for strategy in recovery_strategies:

        graph.add_node(
            strategy,
            node_type="recovery_strategy",
        )

    # --------------------------------------------------------
    # Error → recovery strategy
    # --------------------------------------------------------

    graph.add_edge(
        "syntax_error",
        "repair_source_code",
    )

    graph.add_edge(
        "dependency_error",
        "repair_dependencies",
    )

    graph.add_edge(
        "database_error",
        "repair_database",
    )

    graph.add_edge(
        "file_error",
        "repair_file_paths",
    )

    graph.add_edge(
        "port_error",
        "repair_port_configuration",
    )

    graph.add_edge(
        "configuration_error",
        "repair_configuration",
    )

    graph.add_edge(
        "unknown_error",
        "analyze_with_gemini",
    )

    # --------------------------------------------------------
    # Recovery → Gemini
    # --------------------------------------------------------

    for strategy in [
        "repair_source_code",
        "repair_dependencies",
        "repair_database",
        "repair_file_paths",
        "repair_port_configuration",
        "repair_configuration",
    ]:

        graph.add_edge(
            strategy,
            "analyze_with_gemini",
        )

    # --------------------------------------------------------
    # Gemini → validation
    # --------------------------------------------------------

    graph.add_edge(
        "analyze_with_gemini",
        "revalidate_project",
    )

    return graph


def get_recovery_strategy(error_type):
    """
    Find the first recovery strategy associated
    with the given error type.
    """

    graph = build_recovery_graph()

    if error_type not in graph:

        return "analyze_with_gemini"

    for neighbor in graph.successors(error_type):

        node_data = graph.nodes[neighbor]

        if node_data.get("node_type") == "recovery_strategy":

            return neighbor

    return "analyze_with_gemini"


def get_recovery_path(error_type):
    """
    Return the complete recovery path for an error type.
    """

    graph = build_recovery_graph()

    strategy = get_recovery_strategy(
        error_type
    )

    return [
        error_type,
        strategy,
        "analyze_with_gemini",
        "revalidate_project",
    ]