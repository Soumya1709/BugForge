import difflib
import json
import os
import random
import sys
import time

import streamlit as st

# ── Path setup ────────────────────────────────────────────────────────────────
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from test_harness.harness import run_tests, validate_test_code
from fix_executor.executor import ACTION_NAMES
from environment.debugger_env import DebuggerEnv, load_dataset

# ── Agent import (graceful fallback to mock) ──────────────────────────────────
try:
    from agent.dqn import DQNAgent
    _agent_instance = DQNAgent.load(
        os.path.join(ROOT, "agent", "checkpoints", "latest.pt")
    )
    AGENT_LABEL = "🤖 DQN Agent (trained)"
except Exception:
    from agent.mock_agent import MockAgent
    _agent_instance = MockAgent()
    AGENT_LABEL = "🎲 Mock Agent (DQN not ready yet)"


# ─────────────────────────────────────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="BugForge",
    page_icon="🔧",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .step-card {
        background: #1e1e2e;
        border-radius: 8px;
        padding: 10px 16px;
        margin: 4px 0;
        font-family: monospace;
        font-size: 14px;
        border-left: 4px solid #444;
    }
    .step-progress  { border-left-color: #4CAF50; }
    .step-noop      { border-left-color: #888; }
    .step-regressed { border-left-color: #f44336; }
    .step-solved    { border-left-color: #00e676; background: #1a2e1a; }

    .result-box {
        border-radius: 10px;
        padding: 20px 24px;
        margin: 12px 0;
    }
    .result-solved   { background: #1a2e1a; border: 1px solid #4CAF50; }
    .result-unsolved { background: #2e1a1a; border: 1px solid #f44336; }

    .badge {
        display: inline-block;
        padding: 2px 10px;
        border-radius: 12px;
        font-size: 12px;
        font-weight: bold;
        margin: 2px 4px;
    }
    .badge-green  { background: #1a3a1a; color: #4CAF50; }
    .badge-red    { background: #3a1a1a; color: #f44336; }
    .badge-gray   { background: #2a2a2a; color: #888; }
    .badge-yellow { background: #2a2a1a; color: #ffc107; }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# SESSION STATE
# ─────────────────────────────────────────────────────────────────────────────

def _init_state():
    defaults = {
        "history":        [],      # list of step dicts from last run
        "result":         None,    # final result dict or None
        "session_solved": 0,
        "session_total":  0,
        "code_input":     "",
        "test_input":     "",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init_state()


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _load_examples():
    """Load dataset examples for the 'Try Example' sidebar feature."""
    examples_dir = os.path.join(ROOT, "dataset", "examples")
    if not os.path.exists(examples_dir):
        return []
    files = sorted(f for f in os.listdir(examples_dir) if f.endswith(".json"))
    examples = []
    for fname in files[:200]:   # cap at 200 for sidebar speed
        try:
            with open(os.path.join(examples_dir, fname)) as f:
                examples.append(json.load(f))
        except Exception:
            pass
    return examples


def _reward_badge(reward: float) -> str:
    if reward >= 10:
        return '<span class="badge badge-green">+10 solved</span>'
    if reward > 0:
        return f'<span class="badge badge-green">+{reward:.1f} progress</span>'
    if reward == -0.5:
        return '<span class="badge badge-gray">-0.5 no-op</span>'
    if reward == -1.0:
        return '<span class="badge badge-red">-1.0 regressed</span>'
    if reward == -2.0:
        return '<span class="badge badge-red">-2.0 timeout</span>'
    return f'<span class="badge badge-yellow">{reward:+.1f}</span>'


def _step_class(reward: float) -> str:
    if reward >= 10:   return "step-card step-solved"
    if reward > 0:     return "step-card step-progress"
    if reward <= -1.0: return "step-card step-regressed"
    return "step-card step-noop"


def _build_diff_html(original: str, fixed: str) -> str:
    """Return side-by-side diff as HTML table."""
    orig_lines = original.splitlines()
    fixed_lines = fixed.splitlines()
    diff = list(difflib.ndiff(orig_lines, fixed_lines))

    orig_html, fixed_html = [], []
    for line in diff:
        tag, content = line[:2], line[2:]
        escaped = content.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        if tag == "- ":
            orig_html.append(f'<div style="background:#3a1a1a;color:#ff6b6b;padding:2px 6px">{escaped}</div>')
            fixed_html.append('<div style="padding:2px 6px;color:#555">&nbsp;</div>')
        elif tag == "+ ":
            orig_html.append('<div style="padding:2px 6px;color:#555">&nbsp;</div>')
            fixed_html.append(f'<div style="background:#1a3a1a;color:#69db7c;padding:2px 6px">{escaped}</div>')
        elif tag == "  ":
            orig_html.append(f'<div style="padding:2px 6px;color:#ccc">{escaped}</div>')
            fixed_html.append(f'<div style="padding:2px 6px;color:#ccc">{escaped}</div>')

    return f"""
    <table style="width:100%;font-family:monospace;font-size:13px;border-collapse:collapse">
      <tr>
        <th style="background:#2a1a1a;color:#ff6b6b;padding:6px;text-align:left;width:50%">
          ❌ Buggy
        </th>
        <th style="background:#1a2a1a;color:#69db7c;padding:6px;text-align:left;width:50%">
          ✅ Fixed
        </th>
      </tr>
      <tr>
        <td style="vertical-align:top;background:#1a1a2a;padding:4px">
          {''.join(orig_html)}
        </td>
        <td style="vertical-align:top;background:#1a1a2a;padding:4px">
          {''.join(fixed_html)}
        </td>
      </tr>
    </table>
    """


def _run_agent(code: str, test_code: str, max_attempts: int = 15):
    """
    Run the agent on the given code + tests.
    Returns (history, final_code, solved).
    """
    agent = _agent_instance
    agent.reset()

    current_code = code
    history = []

    for attempt in range(1, max_attempts + 1):
        # Get current test result
        test_result = run_tests(current_code, test_code, timeout=5)
        pass_rate = test_result["pass_rate"]

        # Build state for agent
        state = {
            "code":       current_code,
            "pass_rate":  pass_rate,
            "error_line": test_result.get("error_line"),
            "attempts":   attempt - 1,
            "timed_out":  test_result.get("timed_out", False),
        }

        if pass_rate == 1.0:
            break

        # Agent picks action
        action_id = agent.choose(state)

        # Apply fix
        from fix_executor.executor import apply_fix
        fix_result = apply_fix(current_code, action_id)
        new_code = fix_result["modified_code"]

        # Run tests on new code
        new_result = run_tests(new_code, test_code, timeout=5)
        new_rate = new_result["pass_rate"]

        # Compute reward
        if new_result.get("timed_out"):
            reward = -2.0
        elif new_rate == 1.0:
            reward = 10.0
        elif not fix_result["applied"]:
            reward = -0.5
        elif new_rate > pass_rate:
            reward = 2.0
        elif new_rate < pass_rate:
            reward = -1.0
        else:
            reward = -0.2

        step = {
            "attempt":     attempt,
            "action_id":   action_id,
            "action_name": ACTION_NAMES.get(action_id, f"action_{action_id}"),
            "applied":     fix_result["applied"],
            "pass_before": pass_rate,
            "pass_after":  new_rate,
            "reward":      reward,
            "timed_out":   new_result.get("timed_out", False),
        }
        history.append(step)

        if fix_result["applied"] and not new_result.get("timed_out"):
            current_code = new_code

        if new_rate == 1.0:
            break

    final_result = run_tests(current_code, test_code, timeout=5)
    solved = final_result["pass_rate"] == 1.0
    return history, current_code, solved


# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## 🔧 BugForge")
    st.caption("RL-powered Python debugger")
    st.divider()

    # Agent status
    st.markdown("**Agent**")
    st.info(AGENT_LABEL)
    st.divider()

    # Session stats
    st.markdown("**Session Stats**")
    total = st.session_state.session_total
    solved = st.session_state.session_solved
    if total > 0:
        rate = solved / total
        st.metric("Solve Rate", f"{solved}/{total}", f"{rate:.0%}")
    else:
        st.metric("Solve Rate", "—", "no runs yet")
    st.divider()

    # Try an example
    st.markdown("**Try an Example**")
    examples = _load_examples()
    if examples:
        filter_bugs = st.selectbox(
            "Bug count",
            ["Any", "1 bug", "2 bugs", "3 bugs"],
            index=0,
        )
        filtered = examples
        if filter_bugs != "Any":
            n = int(filter_bugs[0])
            filtered = [e for e in examples if e.get("bug_count", 1) == n]

        if filtered and st.button("🎲 Load Random Example"):
            ex = random.choice(filtered)
            st.session_state.code_input = ex["buggy_code"]
            st.session_state.test_input = ex["test_code"]
            st.session_state.history = []
            st.session_state.result = None
            st.rerun()

        if filtered:
            st.caption(f"{len(filtered)} examples available")
    else:
        st.caption("Run generate_dataset.py first to load examples")

    st.divider()
    st.markdown("**Docs**")
    st.markdown("📄 [Test Format](docs/TEST_FORMAT.md)")
    st.markdown("🐛 [Bug Types](docs/BUG_TYPES.md)")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN CONTENT
# ─────────────────────────────────────────────────────────────────────────────

st.markdown("# 🔧 BugForge")
st.markdown(
    "Paste your buggy Python function and test cases. "
    "The RL agent will try to fix it — one AST action at a time."
)
st.divider()

# ── INPUT SECTION ─────────────────────────────────────────────────────────────
col_code, col_tests = st.columns(2, gap="large")

with col_code:
    st.markdown("#### 🐛 Buggy Code")
    st.caption("Paste a single Python function with a bug in it.")
    code_input = st.text_area(
        label="code",
        label_visibility="collapsed",
        value=st.session_state.code_input,
        height=260,
        placeholder=(
            "def factorial(n):\n"
            "    result = 0   # bug: should be 1\n"
            "    for i in range(1, n + 1):\n"
            "        result *= i\n"
            "    return result"
        ),
        key="code_area",
    )

with col_tests:
    st.markdown("#### 🧪 Test Cases")
    st.caption("One `assert` per line. At least 2 recommended.")
    test_input = st.text_area(
        label="tests",
        label_visibility="collapsed",
        value=st.session_state.test_input,
        height=260,
        placeholder=(
            "assert factorial(5) == 120\n"
            "assert factorial(0) == 1\n"
            "assert factorial(3) == 6"
        ),
        key="test_area",
    )

# ── VALIDATION + RUN BUTTONS ──────────────────────────────────────────────────
btn_col1, btn_col2, btn_col3 = st.columns([1, 1, 4])

with btn_col1:
    validate_clicked = st.button("🔍 Validate Tests", use_container_width=True)
with btn_col2:
    run_clicked = st.button(
        "▶ Run Agent",
        use_container_width=True,
        type="primary",
        disabled=(not code_input.strip() or not test_input.strip()),
    )

# ── VALIDATION FEEDBACK ───────────────────────────────────────────────────────
if validate_clicked and test_input.strip():
    v = validate_test_code(test_input)
    if v["valid"]:
        st.success(f"✅ Tests look good! Found {v['assert_count']} assert statement(s).")
    else:
        for issue in v["issues"]:
            if "Recommend" in issue:
                st.warning(f"⚠️ {issue}")
            else:
                st.error(f"❌ {issue}")

st.divider()

# ── AGENT RUN ─────────────────────────────────────────────────────────────────
if run_clicked and code_input.strip() and test_input.strip():

    # Pre-flight: validate tests
    v = validate_test_code(test_input)
    hard_issues = [i for i in v["issues"] if "Recommend" not in i]
    if hard_issues:
        for issue in hard_issues:
            st.error(f"❌ Fix test code first: {issue}")
        st.stop()

    # Pre-flight: check if code already passes
    initial = run_tests(code_input, test_input)
    if initial["pass_rate"] == 1.0:
        st.success("✅ Your code already passes all tests — no fix needed!")
        st.stop()

    # ── Live attempts feed ────────────────────────────────────────────────────
    st.markdown("### 🔄 Agent Working...")
    initial_rate = initial["pass_rate"]
    st.caption(
        f"Starting pass rate: **{initial['passed']}/{initial['total']}** "
        f"({initial_rate:.0%}) — agent has 15 attempts"
    )

    feed_placeholder = st.empty()
    progress_bar = st.progress(0)
    steps_display = []

    MAX_ATTEMPTS = 15
    current_code = code_input
    agent = _agent_instance
    agent.reset()
    history = []
    final_code = code_input
    solved = False

    for attempt in range(1, MAX_ATTEMPTS + 1):
        progress_bar.progress(attempt / MAX_ATTEMPTS)

        # Get current state
        test_result = run_tests(current_code, test_input, timeout=5)
        pass_rate = test_result["pass_rate"]

        if pass_rate == 1.0:
            solved = True
            final_code = current_code
            break

        state = {
            "code":       current_code,
            "pass_rate":  pass_rate,
            "error_line": test_result.get("error_line"),
            "attempts":   attempt - 1,
            "timed_out":  test_result.get("timed_out", False),
        }

        action_id = agent.choose(state)

        from fix_executor.executor import apply_fix
        fix_result = apply_fix(current_code, action_id)
        new_code = fix_result["modified_code"]
        new_result = run_tests(new_code, test_input, timeout=5)
        new_rate = new_result["pass_rate"]

        # Reward
        if new_result.get("timed_out"):
            reward = -2.0
        elif new_rate == 1.0:
            reward = 10.0
        elif not fix_result["applied"]:
            reward = -0.5
        elif new_rate > pass_rate:
            reward = 2.0
        elif new_rate < pass_rate:
            reward = -1.0
        else:
            reward = -0.2

        step = {
            "attempt":     attempt,
            "action_id":   action_id,
            "action_name": ACTION_NAMES.get(action_id, f"action_{action_id}"),
            "applied":     fix_result["applied"],
            "pass_before": pass_rate,
            "pass_after":  new_rate,
            "reward":      reward,
            "timed_out":   new_result.get("timed_out", False),
        }
        history.append(step)

        # Build live display
        steps_display.append(step)
        cards_html = ""
        for s in steps_display:
            css = _step_class(s["reward"])
            applied_tag = "" if s["applied"] else " <span style='color:#888'>[no-op]</span>"
            timeout_tag = " ⏱️ timeout" if s["timed_out"] else ""
            rate_arrow = (
                f"<span style='color:#4CAF50'>↑</span>"
                if s["pass_after"] > s["pass_before"] else
                f"<span style='color:#f44336'>↓</span>"
                if s["pass_after"] < s["pass_before"] else "→"
            )
            cards_html += f"""
            <div class="{css}">
              <b>Step {s['attempt']}</b>
              &nbsp;·&nbsp; {s['action_name']}{applied_tag}{timeout_tag}
              &nbsp;·&nbsp; {_reward_badge(s['reward'])}
              &nbsp;·&nbsp; pass rate: {s['pass_before']:.0%} {rate_arrow} {s['pass_after']:.0%}
            </div>"""

        with feed_placeholder.container():
            st.markdown(cards_html, unsafe_allow_html=True)

        if fix_result["applied"] and not new_result.get("timed_out"):
            current_code = new_code

        if new_rate == 1.0:
            solved = True
            final_code = current_code
            break

        time.sleep(0.05)   # small delay so user can see steps

    progress_bar.empty()

    # Save to session state
    st.session_state.history = history
    st.session_state.session_total += 1
    if solved:
        st.session_state.session_solved += 1
    st.session_state.result = {
        "solved":      solved,
        "final_code":  final_code,
        "original":    code_input,
        "steps":       len(history),
    }
    st.session_state.code_input = code_input
    st.session_state.test_input = test_input


# ─────────────────────────────────────────────────────────────────────────────
# RESULT SECTION
# ─────────────────────────────────────────────────────────────────────────────

result = st.session_state.result
if result is not None:
    st.divider()
    st.markdown("### 📋 Result")

    if result["solved"]:
        st.markdown(
            f'<div class="result-box result-solved">'
            f'<h3 style="color:#4CAF50;margin:0">✅ Fixed!</h3>'
            f'<p style="color:#aaa;margin:4px 0 0 0">'
            f'Solved in <b>{result["steps"]}</b> step(s)</p>'
            f'</div>',
            unsafe_allow_html=True,
        )

        # Diff view
        st.markdown("#### What changed")
        diff_html = _build_diff_html(result["original"], result["final_code"])
        st.markdown(diff_html, unsafe_allow_html=True)

        # Fixed code copyable block
        with st.expander("📋 Copy fixed code"):
            st.code(result["final_code"], language="python")

    else:
        st.markdown(
            '<div class="result-box result-unsolved">'
            '<h3 style="color:#f44336;margin:0">❌ Not Solved</h3>'
            '<p style="color:#aaa;margin:4px 0 0 0">'
            'The agent used all its attempts without fixing the bug.</p>'
            '</div>',
            unsafe_allow_html=True,
        )

        st.markdown("**Why this happens:**")
        st.markdown("""
- The bug type may be outside the agent's 8 action space
- Your tests may not be specific enough to guide the agent
- The agent (mock or early DQN) may not be trained well yet

**Try:**
- Add more specific test cases — especially edge cases
- Check that your tests would *fail* on the buggy code and *pass* on a correct version
- Make sure the bug matches one of the 8 supported types (see sidebar → Docs)
        """)

        # Show final code state
        with st.expander("🔍 See code after all attempts"):
            final_result = run_tests(
                result["final_code"], st.session_state.test_input
            )
            st.caption(
                f"Final pass rate: {final_result['passed']}/{final_result['total']} tests passing"
            )
            st.code(result["final_code"], language="python")

    # Clear button
    if st.button("🔄 Clear & Start Over"):
        st.session_state.history = []
        st.session_state.result = None
        st.session_state.code_input = ""
        st.session_state.test_input = ""
        st.rerun()