import random
from collections import deque


class ReplayBuffer:

    def __init__(self, capacity=10000):

        self.memory = deque(maxlen=capacity)

    def push(
            self,
            state,
            action,
            reward,
            next_state,
            done):

        self.memory.append(
            (
                state,
                action,
                reward,
                next_state,
                done
            )
        )

    def sample(self, batch_size):

        return random.sample(
            self.memory,
            batch_size
        )

    def __len__(self):

        return len(self.memory)

# if __name__ == "__main__":

#     import torch

#     buffer = ReplayBuffer()

#     for i in range(20):

#         state = torch.randn(771)

#         next_state = torch.randn(771)

#         buffer.push(
#             state,
#             i % 8,
#             1,
#             next_state,
#             False
#         )

#     print("Buffer Size:", len(buffer))

#     batch = buffer.sample(5)

#     print("Batch Size:", len(batch))