from preprocessing.normalizer import normalize
from encoder.codebert_encoder import get_embedding
from rl.state import StateBuilder

code = """
def calculate_customer_transaction_total(transactions):
    return sum(transactions)
"""

normalized = normalize(code)
embedding = get_embedding(normalized)

builder = StateBuilder()

state = builder.build_state(
    embedding=embedding,
    error_line=1,
    pass_rate=0.6,
    attempts_left=0.90
)

print(state.shape)