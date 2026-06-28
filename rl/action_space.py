"""
Defines the action space for the RL debugging agent.

These IDs MUST remain synchronized with Person B's
bug injector and action executor.
"""

ACTION_NAMES = {
    0: "swap_comparison_operator",
    1: "off_by_one",
    2: "flip_boolean_return",
    3: "swap_variable_reference",
    4: "invert_conditional",
    5: "wrong_initial_value",
    6: "wrong_arithmetic_operator",
    7: "wrong_return_value",
}

NUM_ACTIONS = len(ACTION_NAMES)


def get_action_name(action_id):
    return ACTION_NAMES.get(action_id, "Unknown Action")


def available_actions():
    return list(ACTION_NAMES.keys())