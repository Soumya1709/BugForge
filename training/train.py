"""
BugForge -- Improved Training Script v3
========================================
Run from D:\\BugForge root:
    python training/train.py

What changed vs v2 (which scored 56.7%):
    1. ACTION MASKING    -- agent only picks applicable actions each step
    2. CURRICULUM        -- 1-bug only for ep 1-1000, then 1+2, then all
    3. DOUBLE DQN        -- reduces overestimation bias (in dqn_agent.py)
    4. SIMPLER NETWORK   -- 771->256->128->8 + dropout (in q_network.py)
    5. WARMUP fixed      -- warmup uses valid_actions too
    6. TARGET_UPDATE=50  -- kept from v2
"""

import os
import random
import torch

from environment.debugger_env import DebuggerEnv, load_dataset, split_dataset
from agents.dqn_agent import DQNAgent
from rl.state_encoder import StateEncoder
from rl.action_masker import get_action_mask

os.makedirs("checkpoints", exist_ok=True)

# ── Hyperparameters ───────────────────────────────────────────────────────────
NUM_EPISODES   = 3000
BATCH_SIZE     = 64
TARGET_UPDATE  = 50
WARMUP_STEPS   = 1000   # fill buffer before learning

EPSILON        = 1.0
EPSILON_MIN    = 0.05
EPSILON_DECAY  = 0.9975

VALIDATE_EVERY = 100
VAL_EPISODES   = 30

# Curriculum thresholds (episode numbers)
CURRICULUM_PHASE2 = 1000   # ep 1000: add 2-bug examples
CURRICULUM_PHASE3 = 2000   # ep 2000: add 3-bug examples

# ── Data setup ────────────────────────────────────────────────────────────────
dataset = load_dataset("dataset/examples")
train_examples, val_examples = split_dataset(dataset, train_ratio=0.8, seed=42)

# Split train by bug count for curriculum
train_1bug = [e for e in train_examples if e.get("bug_count", 1) == 1]
train_2bug = [e for e in train_examples if e.get("bug_count", 1) == 2]
train_3bug = [e for e in train_examples if e.get("bug_count", 1) >= 3]

print(f"Train examples: {len(train_examples)} "
      f"(1-bug: {len(train_1bug)}, 2-bug: {len(train_2bug)}, 3-bug: {len(train_3bug)})")
print(f"Val   examples: {len(val_examples)}")

# Start with 1-bug only
env     = DebuggerEnv(train_1bug, max_attempts=15, seed=42)
val_env = DebuggerEnv(val_examples, max_attempts=15, seed=0)

agent   = DQNAgent()
encoder = StateEncoder()

scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
    agent.optimizer, mode='max', factor=0.5, patience=400
)

# ── Helpers ───────────────────────────────────────────────────────────────────

def get_state_vector(state, max_attempts=15):
    attempts_left = 1 - state["attempts"] / max_attempts
    return encoder.encode_state(
        code=state["code"],
        pass_rate=state["pass_rate"],
        error_line=state["error_line"],
        attempts_left=attempts_left,
    )


def run_validation(n=VAL_EPISODES):
    """Greedy evaluation on val set. Returns solve rate."""
    solved = 0
    for _ in range(n):
        state = val_env.reset()
        sv    = get_state_vector(state)
        for _ in range(val_env.max_attempts):
            valid   = get_action_mask(state["code"])
            action  = agent.choose_action(sv, epsilon=0, valid_actions=valid)
            state, _, done = val_env.step(action)
            sv      = get_state_vector(state)
            if done:
                break
        if state["pass_rate"] == 1.0:
            solved += 1
    return solved / n


def update_curriculum(episode):
    """Expand training pool as agent improves."""
    global env
    if episode == CURRICULUM_PHASE2 and len(train_2bug) > 0:
        pool = train_1bug + train_2bug
        env  = DebuggerEnv(pool, max_attempts=15, seed=42)
        print(f"\n[Curriculum] Phase 2: added {len(train_2bug)} 2-bug examples "
              f"(total pool: {len(pool)})\n")
    elif episode == CURRICULUM_PHASE3 and len(train_3bug) > 0:
        pool = train_1bug + train_2bug + train_3bug
        env  = DebuggerEnv(pool, max_attempts=15, seed=42)
        print(f"\n[Curriculum] Phase 3: added {len(train_3bug)} 3-bug examples "
              f"(total pool: {len(pool)})\n")


# ── Warm-up ───────────────────────────────────────────────────────────────────
print(f"\nWarm-up: filling replay buffer ({WARMUP_STEPS} random steps)...")
wu_state = env.reset()
wu_sv    = get_state_vector(wu_state)

for _ in range(WARMUP_STEPS):
    valid    = get_action_mask(wu_state["code"])
    action   = agent.choose_action(wu_sv, epsilon=1.0, valid_actions=valid)
    wu_next, reward, done = env.step(action)
    wu_next_sv = get_state_vector(wu_next)
    agent.remember(wu_sv, action, reward, wu_next_sv, done)
    wu_sv    = wu_next_sv
    wu_state = wu_next
    if done:
        wu_state = env.reset()
        wu_sv    = get_state_vector(wu_state)

print(f"Buffer ready: {agent.memory_size()} experiences\n")

# ── Training loop ─────────────────────────────────────────────────────────────
train_solved  = 0
best_val_rate = 0.0

for episode in range(NUM_EPISODES):

    # Curriculum update
    update_curriculum(episode)

    state = env.reset()
    sv    = get_state_vector(state)
    done  = False
    total_reward = 0.0
    total_loss   = 0.0
    step         = 0
    next_state   = state

    while not done:
        # Action masking -- only pick applicable actions
        valid  = get_action_mask(state["code"])
        action = agent.choose_action(sv, epsilon=EPSILON, valid_actions=valid)

        next_state, reward, done = env.step(action)
        next_sv = get_state_vector(next_state)

        agent.remember(sv, action, reward, next_sv, done)

        loss = agent.learn(batch_size=BATCH_SIZE)
        if loss is not None:
            total_loss += loss

        sv           = next_sv
        state        = next_state
        total_reward += reward
        step         += 1

    # Epsilon decay
    if EPSILON > EPSILON_MIN:
        EPSILON = max(EPSILON * EPSILON_DECAY, EPSILON_MIN)

    # Target network update
    if (episode + 1) % TARGET_UPDATE == 0:
        agent.update_target_network()

    # Track solves
    final_pass_rate = next_state["pass_rate"]
    if done and final_pass_rate == 1.0:
        train_solved += 1

    avg_loss = total_loss / step if step > 0 else 0.0

    print(
        f"Ep {episode+1:04d} | "
        f"Reward: {total_reward:6.2f} | "
        f"PassRate: {final_pass_rate:.2f} | "
        f"Loss: {avg_loss:.4f} | "
        f"e: {EPSILON:.3f} | "
        f"Solved: {train_solved}/{episode+1}"
    )

    # Checkpoint every 100 eps
    if (episode + 1) % 100 == 0:
        torch.save(
            agent.policy_network.state_dict(),
            f"checkpoints/model_ep_{episode+1}.pth"
        )

    # Validation + best model save
    if (episode + 1) % VALIDATE_EVERY == 0:
        val_rate   = run_validation()
        train_rate = train_solved / (episode + 1)
        scheduler.step(val_rate)

        print("\n" + "=" * 65)
        print(f"  Validation @ Episode {episode+1}")
        print(f"  Train Solve Rate : {train_rate*100:.1f}%")
        print(f"  Val   Solve Rate : {val_rate*100:.1f}%")
        print(f"  Best  Val Rate   : {best_val_rate*100:.1f}%")
        print(f"  Epsilon          : {EPSILON:.4f}")
        print(f"  Buffer           : {agent.memory_size()}")

        if val_rate > best_val_rate:
            best_val_rate = val_rate
            torch.save(
                agent.policy_network.state_dict(),
                "bugforge_dqn_best.pth"
            )
            print(f"  BEST MODEL SAVED -- val rate: {val_rate*100:.1f}%")
        else:
            print(f"  No improvement (best: {best_val_rate*100:.1f}%)")
        print("=" * 65 + "\n")

# ── Final save ────────────────────────────────────────────────────────────────
torch.save(agent.policy_network.state_dict(), "bugforge_dqn.pth")

print("\nTraining Finished!")
print(f"Final model -> bugforge_dqn.pth")
print(f"Best model  -> bugforge_dqn_best.pth (val: {best_val_rate*100:.1f}%)")
print("\n========== Training Summary ==========")
print(f"Total Episodes  : {NUM_EPISODES}")
print(f"Train Solved    : {train_solved}")
print(f"Train Solve Rate: {(train_solved / NUM_EPISODES) * 100:.1f}%")
print(f"Best Val Rate   : {best_val_rate * 100:.1f}%")
print("======================================")