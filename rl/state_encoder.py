from preprocessing.normalizer import normalize
from encoder.codebert_encoder import get_embedding
from rl.state import StateBuilder
from rl.error_detector import ErrorDetector


class StateEncoder:

    def __init__(self):
        self.detector = ErrorDetector()
        self.builder = StateBuilder()

    def encode_state(self, code, pass_rate, attempts_left):

        syntax_info = self.detector.detect_syntax_error(code)

        if syntax_info["has_error"]:
           embedding = get_embedding(code)

        else:
          normalized = normalize(code)
          embedding = get_embedding(normalized)


        

        state = self.builder.build_state(
            embedding=embedding,
            error_line=syntax_info["error_line"],
            pass_rate=pass_rate,
            attempts_left=attempts_left
        )

        return state