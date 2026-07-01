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

        
        if error_line is None:
            normalized_error_line = -1.0
        elif error_line == -1:
            normalized_error_line = -1.0
        else:
            normalized_error_line = min(error_line / 100.0, 1.0)

       
        if normalized_error_line == -1.0:
            
            normalized_code = normalize(code)
            embedding = get_embedding(normalized_code)
        else:
            
            embedding = get_embedding(code)

        
        state = self.builder.build_state(
            embedding=embedding,
            error_line=normalized_error_line,
            pass_rate=pass_rate,
            attempts_left=attempts_left
        )

        return state