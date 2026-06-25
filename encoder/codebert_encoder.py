from transformers import AutoTokenizer,AutoModel
import torch

tokenizer = AutoTokenizer.from_pretrained(
    "microsoft/codebert-base"
)

model= AutoModel.from_pretrained(
    "microsoft/codebert-base"
)

def get_embedding(code):
    """
    Returns a 768-dimensional embedding for a single code snippet.
    """
    

    inputs = tokenizer(
      code,
      return_tensors="pt",
      truncation=True,
      padding=True
    )

    with torch.no_grad():
      outputs = model(**inputs)

    embedding = outputs.last_hidden_state[:,0,:]

    return embedding.squeeze(0).numpy()