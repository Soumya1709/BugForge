import json
import os
import sys
import random
import asyncio
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# ── Path setup — adjust ROOT to your BugForge folder ─────────────────────────
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from test_harness.harness import run_tests, validate_test_code
from fix_executor.executor import apply_fix, ACTION_NAMES
from environment.debugger_env import load_dataset

# ── Agent load ────────────────────────────────────────────────────────────────
try:
    import torch
    from agents.dqn_agent import DQNAgent
    from rl.state_encoder import StateEncoder

    _agent = DQNAgent()
    _ckpt = os.path.join(ROOT, "bugforge_dqn.pth")
    _agent.policy_network.load_state_dict(
        torch.load(_ckpt, map_location="cpu")
    )
    _agent.policy_network.eval()
    _encoder = StateEncoder()
    AGENT_TYPE = "DQN (trained)"
except Exception as e:
    _agent = None
    _encoder = None
    AGENT_TYPE = f"unavailable: {e}"

# ── Dataset load ──────────────────────────────────────────────────────────────
try:
    _dataset = load_dataset(os.path.join(ROOT, "dataset", "examples"))
except Exception:
    _dataset = []

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="BugForge API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Request / Response models ─────────────────────────────────────────────────
class RunRequest(BaseModel):
    code: str
    test_code: str
    max_attempts: int = 15

class ValidateRequest(BaseModel):
    test_code: str

# ── Helpers ───────────────────────────────────────────────────────────────────
def _encode_state(code, pass_rate, error_line, attempt, max_attempts):
    attempts_left = 1 - attempt / max_attempts
    return _encoder.encode_state(
        code=code,
        pass_rate=pass_rate,
        error_line=error_line,
        attempts_left=attempts_left,
    )

def _compute_reward(new_rate, prev_rate, applied, timed_out):
    if timed_out:      return -2.0
    if new_rate == 1.0: return 10.0
    if not applied:    return -0.5
    if new_rate > prev_rate: return 2.0
    if new_rate < prev_rate: return -1.0
    return -0.2

# ─────────────────────────────────────────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "agent": AGENT_TYPE,
        "dataset_size": len(_dataset),
    }


@app.get("/api/examples")
def examples(bug_count: Optional[int] = None, limit: int = 20):
    """Return random examples, optionally filtered by bug_count."""
    pool = _dataset
    if bug_count is not None:
        pool = [e for e in _dataset if e.get("bug_count", 1) == bug_count]
    sample = random.sample(pool, min(limit, len(pool))) if pool else []
    return [
        {
            "id":            ex["id"],
            "function_name": ex["function_name"],
            "bug_count":     ex.get("bug_count", 1),
            "bug_type_names":ex.get("bug_type_names", []),
            "buggy_code":    ex["buggy_code"],
            "test_code":     ex["test_code"],
        }
        for ex in sample
    ]


@app.post("/api/validate")
def validate(req: ValidateRequest):
    return validate_test_code(req.test_code)


@app.post("/api/run")
def run(req: RunRequest):
    """
    Run the agent synchronously.
    Returns all steps + final result in one response.
    Frontend animates steps itself.
    """
    if _agent is None or _encoder is None:
        raise HTTPException(status_code=503, detail=f"Agent not available: {AGENT_TYPE}")

    # Pre-flight: validate tests
    v = validate_test_code(req.test_code)
    hard_issues = [i for i in v["issues"] if "Recommend" not in i]
    if hard_issues:
        raise HTTPException(status_code=400, detail=hard_issues[0])

    # Pre-flight: already passing?
    initial = run_tests(req.code, req.test_code, timeout=5)
    if initial["pass_rate"] == 1.0:
        return {
            "already_passing": True,
            "steps": [],
            "solved": True,
            "final_code": req.code,
            "original_code": req.code,
        }

    current_code = req.code
    steps = []
    prev_rate = initial["pass_rate"]

    for attempt in range(1, req.max_attempts + 1):
        test_result = run_tests(current_code, req.test_code, timeout=5)
        pass_rate = test_result["pass_rate"]

        if pass_rate == 1.0:
            break

        # Encode state → agent chooses action
        state_vector = _encode_state(
            current_code, pass_rate,
            test_result.get("error_line"),
            attempt, req.max_attempts,
        )
        action_id = _agent.choose_action(state_vector, epsilon=0)

        # Apply fix
        fix_result = apply_fix(current_code, action_id)
        new_code = fix_result["modified_code"]

        # Run tests on new code
        new_result = run_tests(new_code, req.test_code, timeout=5)
        new_rate = new_result["pass_rate"]

        reward = _compute_reward(
            new_rate, pass_rate,
            fix_result["applied"],
            new_result.get("timed_out", False),
        )

        steps.append({
            "attempt":     attempt,
            "action_id":   action_id,
            "action_name": ACTION_NAMES.get(action_id, f"action_{action_id}"),
            "applied":     fix_result["applied"],
            "pass_before": round(pass_rate, 4),
            "pass_after":  round(new_rate, 4),
            "reward":      reward,
            "timed_out":   new_result.get("timed_out", False),
        })

        if fix_result["applied"] and not new_result.get("timed_out"):
            current_code = new_code

        prev_rate = new_rate

        if new_rate == 1.0:
            break

    final_result = run_tests(current_code, req.test_code, timeout=5)
    solved = final_result["pass_rate"] == 1.0

    return {
        "already_passing": False,
        "steps":           steps,
        "solved":          solved,
        "final_code":      current_code,
        "original_code":   req.code,
        "final_pass_rate": final_result["pass_rate"],
        "final_passed":    final_result["passed"],
        "final_total":     final_result["total"],
    }