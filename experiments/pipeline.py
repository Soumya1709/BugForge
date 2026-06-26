from preprocessing.normalizer import normalize
from encoder.codebert_encoder import get_embedding
from rl.state import StateBuilder
from rl.error_detector import ErrorDetector

code = """
def add(a,b):
    return a+b
"""

detector = ErrorDetector()
syntax_info = detector.detect_syntax_error(code)
normalized = normalize(code)
embedding = get_embedding(normalized)

builder = StateBuilder()

state = builder.build_state(
    embedding=embedding,
    error_line=syntax_info["error_line"],
    pass_rate=0.75,
    attempts_left=0.90
)

print(state.shape)