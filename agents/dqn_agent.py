import random
import torch
import torch.nn as nn
import torch.optim as optim
import numpy as np

from models.q_network import QNetwork
from memory.replay_buffer import ReplayBuffer


class DQNAgent:

    def __init__(
        self,
        state_size=771,
        action_size=8,
        learning_rate=0.001,
        buffer_size=10000,
    ):

        self.state_size = state_size
        self.action_size = action_size

        
        self.policy_network = QNetwork(
            state_size=state_size,
            action_size=action_size
        )

       
        self.target_network = QNetwork(
            state_size=state_size,
            action_size=action_size
        )

        
        self.target_network.load_state_dict(
            self.policy_network.state_dict()
        )

        
        self.target_network.eval()

       
        self.memory = ReplayBuffer(capacity=buffer_size)

        
        self.optimizer = optim.Adam(
            self.policy_network.parameters(),
            lr=learning_rate
        )

       
        self.loss_fn = nn.MSELoss()

  

    def remember(
        self,
        state,
        action,
        reward,
        next_state,
        done
    ):
        self.memory.push(
            state,
            action,
            reward,
            next_state,
            done
        )

    

    def choose_action(
        self,
        state,
        epsilon=0.1
    ):

       
        if random.random() < epsilon:
            return random.randint(
                0,
                self.action_size - 1
            )

      
        state = torch.FloatTensor(state).unsqueeze(0)

        with torch.no_grad():

            q_values = self.policy_network(state)

        action = torch.argmax(
            q_values,
            dim=1
        ).item()

        return action
    
    def learn(self, batch_size=32, gamma=0.99):

    
       if len(self.memory) < batch_size:
         return None

    
       batch = self.memory.sample(batch_size)

       states, actions, rewards, next_states, dones = zip(*batch)

       states = torch.FloatTensor(np.array(states))
       actions = torch.LongTensor(actions).unsqueeze(1)
       rewards = torch.FloatTensor(rewards).unsqueeze(1)
       next_states = torch.FloatTensor(np.array(next_states))
       dones = torch.FloatTensor(dones).unsqueeze(1)

    
       current_q = self.policy_network(states).gather(1, actions)

   
       with torch.no_grad():
         max_next_q = self.target_network(next_states).max(1)[0].unsqueeze(1)
         target_q = rewards + gamma * max_next_q * (1 - dones)

    
       loss = self.loss_fn(current_q, target_q)

    
       self.optimizer.zero_grad()
       loss.backward()
       self.optimizer.step()

       return loss.item()

   

    def update_target_network(self):

        self.target_network.load_state_dict(
            self.policy_network.state_dict()
        )

  

    def memory_size(self):

        return len(self.memory)
    
# if __name__ == "__main__":

#     import numpy as np

#     agent = DQNAgent()

#     print("Policy Network")
#     print(agent.policy_network)

#     print("\nTarget Network")
#     print(agent.target_network)

#     print("\nReplay Buffer Size:")
#     print(agent.memory_size())

#     # Dummy state
#     state = np.random.randn(771)

#     action = agent.choose_action(
#         state,
#         epsilon=0
#     )

#     print("\nChosen Action:", action)