import torch

from environment.debugger_env import (
    DebuggerEnv,
    load_dataset,
    split_dataset,
)

from agents.dqn_agent import DQNAgent
from rl.state_encoder import StateEncoder




NUM_EPISODES = 500          # Change to 500 for actual training
BATCH_SIZE = 32

TARGET_UPDATE = 10

EPSILON = 1.0
EPSILON_MIN = 0.05
EPSILON_DECAY = 0.995



dataset = load_dataset("dataset/examples")

train_examples, val_examples = split_dataset(dataset)

env = DebuggerEnv(train_examples)

agent = DQNAgent()

encoder = StateEncoder()



solved_count = 0

for episode in range(NUM_EPISODES):

    state = env.reset()

    attempts_left = (
        1 - state["attempts"] / env.max_attempts
    )

    state_vector = encoder.encode_state(
        code=state["code"],
        pass_rate=state["pass_rate"],
        error_line=state["error_line"],
        attempts_left=attempts_left,
    )

    done = False

    total_reward = 0
    total_loss = 0
    step = 0

    next_state = state

    while not done:

        action = agent.choose_action(
            state_vector,
            epsilon=EPSILON,
        )

        next_state, reward, done = env.step(action)

        attempts_left = (
            1 - next_state["attempts"] / env.max_attempts
        )

        next_state_vector = encoder.encode_state(
            code=next_state["code"],
            pass_rate=next_state["pass_rate"],
            error_line=next_state["error_line"],
            attempts_left=attempts_left,
        )

        agent.remember(
            state_vector,
            action,
            reward,
            next_state_vector,
            done,
        )

        loss = agent.learn(
            batch_size=BATCH_SIZE
        )

        if loss is not None:
            total_loss += loss

        state_vector = next_state_vector

        total_reward += reward

        step += 1

   

    if (episode + 1) % TARGET_UPDATE == 0:
        agent.update_target_network()

    

    if EPSILON > EPSILON_MIN:
        EPSILON *= EPSILON_DECAY
        EPSILON = max(EPSILON, EPSILON_MIN)

   

    average_loss = (
        total_loss / step
        if step > 0
        else 0
    )

    final_pass_rate = next_state["pass_rate"]

    if done and final_pass_rate == 1.0:
        solved_count += 1

    print(
        f"Episode {episode + 1:03d} | "
        f"Reward: {total_reward:6.2f} | "
        f"PassRate: {final_pass_rate:.2f} | "
        f"Loss: {average_loss:.4f} | "
        f"Epsilon: {EPSILON:.3f} | "
        f"Done: {done}"
    )




torch.save(
    agent.policy_network.state_dict(),
    "bugforge_dqn.pth",
)

print("\nTraining Finished!")
print("Model saved as bugforge_dqn.pth")

print("\n========== Training Summary ==========")
print(f"Total Episodes : {NUM_EPISODES}")
print(f"Solved Episodes: {solved_count}")
print(f"Solve Rate     : {(solved_count / NUM_EPISODES) * 100:.2f}%")
print("======================================")