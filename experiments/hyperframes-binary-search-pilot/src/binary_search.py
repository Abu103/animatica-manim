"""Binary search computation for the HyperFrames explainer.

Computes the actual search steps for finding a target in a sorted array.
All steps are computed deterministically from the input data; nothing is
hard-coded to a particular outcome.
"""
from __future__ import annotations


def binary_search_steps(array: list[int], target: int) -> list[dict]:
    """Compute every step of binary search for ``target`` in ``array``.

    Returns a list of step dicts, each with:
      - low: inclusive lower bound of the current search range
      - high: inclusive upper bound of the current search range
      - mid: midpoint index (floor of (low + high) / 2)
      - mid_value: array[mid]
      - comparison: "too_low", "too_high", or "found"
      - eliminated: list of indices eliminated in this step (may be empty)
      - found_index: set only when comparison == "found"
    """
    steps: list[dict] = []
    low = 0
    high = len(array) - 1
    step_num = 1

    while low <= high:
        mid = (low + high) // 2
        mid_value = array[mid]

        step: dict = {
            "step": step_num,
            "low": low,
            "high": high,
            "mid": mid,
            "mid_value": mid_value,
            "comparison": "",
            "eliminated": [],
            "found_index": None,
        }

        if mid_value == target:
            step["comparison"] = "found"
            step["found_index"] = mid
            steps.append(step)
            break

        if target > mid_value:
            # Target is to the right; discard [low, mid]
            step["comparison"] = "too_low"
            step["eliminated"] = list(range(low, mid + 1))
            low = mid + 1
        else:
            # Target is to the left; discard [mid, high]
            step["comparison"] = "too_high"
            step["eliminated"] = list(range(mid, high + 1))
            high = mid - 1

        steps.append(step)
        step_num += 1

    return steps


def compute_result(array: list[int], target: int) -> dict:
    """Compute the full binary search result from input data.

    Returns a dict with:
      - array: the input array
      - target: the target value
      - steps: list of step dicts from binary_search_steps
      - found: whether the target was found
      - found_index: index where found, or -1
    """
    steps = binary_search_steps(array, target)
    found_index = -1
    for step in steps:
        if step["comparison"] == "found":
            found_index = step["mid"]
            break

    return {
        "array": array,
        "target": target,
        "steps": steps,
        "found": found_index >= 0,
        "found_index": found_index,
    }
