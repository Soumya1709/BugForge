from rl.state_encoder import StateEncoder

encoder = StateEncoder()

code = """def add(a,b)
    return a+b"""

state = encoder.encode_state(
    code=code,
    pass_rate=0.75,
    error_line=-1,
    attempts_left=0.90
)

print(state.shape)