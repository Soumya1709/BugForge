from transformers import AutoTokenizer,AutoModel
import torch.nn.functional as F

tokenizer = AutoTokenizer.from_pretrained(
    "microsoft/codebert-base"
)

model= AutoModel.from_pretrained(
    "microsoft/codebert-base"
)

code1 = """
def calculate_customer_transaction_total(transactions):
    return sum(transactions)
"""

code2 = """
def c(x):
    return sum(x)
"""
codes=[code1,code2]

inputs = tokenizer(
    codes,
    return_tensors="pt",
    truncation=True,
    padding=True
)

outputs = model(**inputs)

embedding = outputs.last_hidden_state[:,0,:]
similarity = F.cosine_similarity(
    embedding[0].unsqueeze(0),
    embedding[1].unsqueeze(0)
)
print("Similarity:", similarity.item())