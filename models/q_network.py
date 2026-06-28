import torch
import torch.nn as nn


class QNetwork(nn.Module):

    def __init__(self,
                 state_size=771,
                 action_size=8):

        super().__init__()

        self.fc1 = nn.Linear(state_size,256)

        self.fc2 = nn.Linear(256,128)

        self.fc3 = nn.Linear(128,action_size)

    def forward(self,x):

        x=self.fc1(x)

        x=torch.relu(x)

        x=self.fc2(x)

        x=torch.relu(x)

        x=self.fc3(x)

        return x

# if __name__=="__main__":
#     model=QNetwork()
#     dummy=torch.randn(1,771)
#     output=model(dummy)
    

# print(output)
# print(output.shape)