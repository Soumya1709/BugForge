from preprocessing.normalizer import normalize
from encoder.codebert_encoder import get_embedding
from rl.state import StateBuilder


class StateEncoder:

    def __init__(self):
        self.builder = StateBuilder()

    def encode_state(
        self,
        code,
        pass_rate,
        error_line,
        attempts_left
    ):

        
        if error_line != -1:
            embedding = get_embedding(code)

        else:
            normalized = normalize(code)
            embedding = get_embedding(normalized)
            
        normalized_error_line = error_line / 100.0

        state = self.builder.build_state(
            embedding=embedding,
            error_line=normalized_error_line,
            pass_rate=pass_rate,
            attempts_left=attempts_left
        )

        return state