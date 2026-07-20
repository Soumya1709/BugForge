import random
import torch
import torch.nn as nn
import torch.optim as optim
import numpy as np

from models.q_network import QNetwork
from memory.replay_buffer import ReplayBuffer


class DQNAgent:
    """
    DQN Agent v3 — Double DQN + Action Masking support.

    Changes:
      1. Double DQN: policy net selects action, target net evaluates value
         -> reduces Q-value overestimation bias
      2. choose_action() accepts valid_actions mask
         -> agent never wastes attempt on inapplicable action
      3. Huber loss (SmoothL1) instead of MSE
      4. Gradient clipping (1.0)
      5. eval/train mode switch during inference
      6. buffer 50_000, lr 0.0005
    """

    def __init__(
        self,
        state_size=771,
        action_size=8,
        learning_rate=0.0005,
        buffer_size=50_000,
        grad_clip=1.0,
    ):
        self.state_size  = state_size
        self.action_size = action_size
        self.grad_clip   = grad_clip

        self.policy_network = QNetwork(state_size, action_size)
        self.target_network = QNetwork(state_size, action_size)
        self.target_network.load_state_dict(self.policy_network.state_dict())
        self.target_network.eval()

        self.memory   = ReplayBuffer(capacity=buffer_size)
        self.optimizer = optim.Adam(
            self.policy_network.parameters(), lr=learning_rate
        )
        self.loss_fn = nn.SmoothL1Loss()

    def remember(self, state, action, reward, next_state, done):
        self.memory.push(state, action, reward, next_state, done)

    def choose_action(self, state, epsilon=0.1, valid_actions=None):
        """
        Epsilon-greedy with optional action mask.

        Args:
            state        : numpy array (771,)
            epsilon      : exploration rate
            valid_actions: list of applicable action IDs, or None (= all)
        """
        if valid_actions is None or len(valid_actions) == 0:
            valid_actions = list(range(self.action_size))

        # Explore: pick random from VALID actions only
        if random.random() < epsilon:
            return random.choice(valid_actions)

        # Exploit: pick best Q-value among valid actions
        self.policy_network.eval()
        with torch.no_grad():
            state_t  = torch.FloatTensor(state).unsqueeze(0)
            q_values = self.policy_network(state_t).squeeze(0)  # shape (8,)

            # Mask out invalid actions with large negative value
            mask = torch.full((self.action_size,), float('-inf'))
            for a in valid_actions:
                mask[a] = q_values[a]

            action = torch.argmax(mask).item()
        self.policy_network.train()
        return action

    def learn(self, batch_size=32, gamma=0.99):
        if len(self.memory) < batch_size:
            return None

        batch = self.memory.sample(batch_size)
        states, actions, rewards, next_states, dones = zip(*batch)

        states      = torch.FloatTensor(np.array(states))
        actions     = torch.LongTensor(actions).unsqueeze(1)
        rewards     = torch.FloatTensor(rewards).unsqueeze(1)
        next_states = torch.FloatTensor(np.array(next_states))
        dones       = torch.FloatTensor(dones).unsqueeze(1)

        # Current Q-values
        current_q = self.policy_network(states).gather(1, actions)

        # --- Double DQN ---
        # 1. policy_network picks best action for next state
        with torch.no_grad():
            best_next_actions = self.policy_network(next_states).argmax(1, keepdim=True)
            # 2. target_network evaluates that action's value
            next_q_values = self.target_network(next_states).gather(1, best_next_actions)
            target_q = rewards + gamma * next_q_values * (1 - dones)

        loss = self.loss_fn(current_q, target_q)

        self.optimizer.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(
            self.policy_network.parameters(), self.grad_clip
        )
        self.optimizer.step()

        return loss.item()

    def update_target_network(self):
        self.target_network.load_state_dict(self.policy_network.state_dict())

    def memory_size(self):
        return len(self.memory)