import json
import random
from pathlib import Path
from typing import Optional
 
from fix_executor.executor import apply_fix, available_actions
from test_harness.harness import run_tests
 
 
# ─────────────────────────────────────────────────────────────────────────────
# REWARDS
# ─────────────────────────────────────────────────────────────────────────────
 
REWARD_SOLVED        =  10.0
REWARD_PROGRESS      =   2.0
REWARD_NO_CHANGE     =  -0.2
REWARD_NOOP          =  -0.5
REWARD_REGRESSED     =  -1.0
REWARD_TIMEOUT       =  -2.0
 
 
# ─────────────────────────────────────────────────────────────────────────────
# ENVIRONMENT
# ─────────────────────────────────────────────────────────────────────────────
 
class DebuggerEnv:
    """
    Gym-style environment for the BugForge RL agent.
 
    Parameters
    ----------
    dataset : list[dict]
        List of example dicts loaded from dataset/examples/*.json.
        Each must have keys: buggy_code, test_code, bug_count, bug_types.
    max_attempts : int
        Maximum fix actions per episode before forced termination.
    timeout : int
        Seconds allowed per test run (passed to harness).
    seed : int | None
        Random seed for reproducible episode ordering.
 
    Usage
    -----
    Load the dataset once, then create the env:
 
        import json, glob
        dataset = [json.load(open(f)) for f in glob.glob("dataset/examples/*.json")]
        env = DebuggerEnv(dataset)
 
        state = env.reset()
        state, reward, done = env.step(0)
    """
 
    MAX_ATTEMPTS_DEFAULT = 15
 
    def __init__(
        self,
        dataset: list,
        max_attempts: int = MAX_ATTEMPTS_DEFAULT,
        timeout: int = 5,
        seed: Optional[int] = None,
    ):
        if not dataset:
            raise ValueError("dataset must not be empty")
 
        self.dataset = dataset
        self.max_attempts = max_attempts
        self.timeout = timeout
        self._rng = random.Random(seed)
 
        # Episode state — populated on reset()
        self._example: Optional[dict] = None
        self._current_code: str = ""
        self._test_code: str = ""
        self._attempts: int = 0
        self._prev_pass_rate: float = 0.0
        self._episode_done: bool = True   # forces reset() before first step()
 
        # Logging / diagnostics
        self.last_test_result: Optional[dict] = None
        self.last_fix_result: Optional[dict] = None
        self.history: list = []           # list of (action_id, reward, pass_rate)
 
    # ── Public interface ──────────────────────────────────────────────────────
 
    def reset(self, example: Optional[dict] = None) -> dict:
        """
        Start a new episode.
 
        Args:
            example: Specific dataset example to use. If None, picks randomly.
 
        Returns:
            Initial state dict.
        """
        self._example = example or self._rng.choice(self.dataset)
        self._current_code = self._example["buggy_code"]
        self._test_code = self._example["test_code"]
        self._attempts = 0
        self._episode_done = False
        self.history = []
 
        test_result = run_tests(
            self._current_code,
            self._test_code,
            timeout=self.timeout,
        )
        self.last_test_result = test_result
        self._prev_pass_rate = test_result["pass_rate"]
 
        return self._make_state(test_result)
 
    def step(self, action_id: int) -> tuple:
        """
        Apply a fix action to the current code, run tests, return results.
 
        Args:
            action_id: Integer 0–7 selecting the fix action.
 
        Returns:
            (state_dict, reward, done)
            state_dict : new state after the action
            reward     : float reward signal
            done       : True if episode is over (solved or out of attempts)
 
        Raises:
            RuntimeError if called before reset() or after episode is done.
        """
        if self._episode_done:
            raise RuntimeError(
                "Episode is done. Call reset() before stepping again."
            )
 
        self._attempts += 1
 
        # Apply the fix
        fix_result = apply_fix(self._current_code, action_id)
        self.last_fix_result = fix_result
 
        # Run tests on the (possibly modified) code
        candidate_code = fix_result["modified_code"]
        test_result = run_tests(
            candidate_code,
            self._test_code,
            timeout=self.timeout,
        )
        self.last_test_result = test_result
 
        # Compute reward
        reward = self._compute_reward(test_result, fix_result)
 
        # Only persist code change if it didn't timeout and action applied
        if fix_result["applied"] and not test_result["timed_out"]:
            self._current_code = candidate_code
 
        # Check done conditions
        solved = test_result["pass_rate"] == 1.0
        out_of_attempts = self._attempts >= self.max_attempts
        done = solved or out_of_attempts or test_result["timed_out"]
 
        if done:
            self._episode_done = True
 
        # Update tracking
        self._prev_pass_rate = test_result["pass_rate"]
        state = self._make_state(test_result)
        self.history.append((action_id, reward, test_result["pass_rate"]))
 
        return state, reward, done
 
    def render(self) -> str:
        """Return a human-readable summary of the current episode state."""
        if self._example is None:
            return "No episode in progress. Call reset() first."
 
        lines = [
            f"Episode: {self._example.get('id', 'unknown')}",
            f"  Bug count  : {self._example.get('bug_count', '?')}",
            f"  Bug types  : {self._example.get('bug_type_names', [])}",
            f"  Attempts   : {self._attempts}/{self.max_attempts}",
            f"  Pass rate  : {self._prev_pass_rate:.2f}",
            f"  Done       : {self._episode_done}",
        ]
        if self.history:
            lines.append("  History    :")
            for step_i, (act, rew, pr) in enumerate(self.history, 1):
                lines.append(f"    step {step_i}: action={act}  reward={rew:+.1f}  pass_rate={pr:.2f}")
        return "\n".join(lines)
 
    # ── Properties ────────────────────────────────────────────────────────────
 
    @property
    def current_code(self) -> str:
        return self._current_code
 
    @property
    def action_space_size(self) -> int:
        return len(available_actions())
 
    @property
    def is_done(self) -> bool:
        return self._episode_done
 
    # ── Internal helpers ──────────────────────────────────────────────────────
 
    def _make_state(self, test_result: dict) -> dict:
        """Build the state dict that Person A's encoder receives."""
        return {
            "code":       self._current_code,
            "pass_rate":  test_result["pass_rate"],
            "error_line": test_result.get("error_line",-1),
            "attempts":   self._attempts,
            "timed_out":  test_result.get("timed_out", False),
        }
 
    def _compute_reward(self, test_result: dict, fix_result: dict) -> float:
        """
        Compute the reward for this step.
 
        Priority order (highest wins):
          1. Timeout          → heavy penalty
          2. Solved           → big positive
          3. No-op action     → mild penalty (agent wasted an attempt)
          4. Pass rate up     → positive (progress on multi-bug example)
          5. Pass rate down   → negative (fix broke something)
          6. Pass rate same   → tiny penalty (applied but no improvement)
        """
        if test_result.get("timed_out"):
            return REWARD_TIMEOUT
 
        current_rate = test_result["pass_rate"]
 
        if current_rate == 1.0:
            return REWARD_SOLVED
 
        if not fix_result["applied"]:
            return REWARD_NOOP
 
        if current_rate > self._prev_pass_rate:
            return REWARD_PROGRESS
 
        if current_rate < self._prev_pass_rate:
            return REWARD_REGRESSED
 
        return REWARD_NO_CHANGE
 
 
# ─────────────────────────────────────────────────────────────────────────────
# DATASET LOADER  (convenience helper)
# ─────────────────────────────────────────────────────────────────────────────
 
def load_dataset(examples_dir: str) -> list:
    """
    Load all JSON example files from the dataset/examples/ directory.
 
    Args:
        examples_dir: Path to the folder containing *.json example files.
 
    Returns:
        List of example dicts, sorted by id for reproducibility.
    """
    examples_path = Path(examples_dir)
    if not examples_path.exists():
        raise FileNotFoundError(f"Dataset directory not found: {examples_dir}")
 
    examples = []
    for json_file in sorted(examples_path.glob("*.json")):
        try:
            with open(json_file, encoding="utf-8") as f:
                examples.append(json.load(f))
        except Exception as e:
            print(f"  Warning: could not load {json_file.name}: {e}")
 
    if not examples:
        raise ValueError(f"No JSON files found in {examples_dir}")
 
    return examples
 
 
def split_dataset(
    dataset: list,
    train_ratio: float = 0.8,
    seed: int = 42,
) -> tuple:
    """
    Split dataset into train and validation sets.
 
    Returns:
        (train_examples, val_examples)
    """
    rng = random.Random(seed)
    shuffled = list(dataset)
    rng.shuffle(shuffled)
    split = int(len(shuffled) * train_ratio)
    return shuffled[:split], shuffled[split:]