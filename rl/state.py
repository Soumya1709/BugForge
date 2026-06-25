import numpy as np

class StateBuilder:
    """
    Builds the RL state vector.

    State Layout:
    ----------------------------------------------------
    [768 CodeBERT embedding |
     Error Line |
     Test Pass Rate |
     Attempts Remaining]
    ----------------------------------------------------

    Total Dimensions = 771
    """
    
    def __init__(self):
        self.embedding_size = 768
        self.state_size = 771
        
    def build_state(self,embedding,error_line,pass_rate,attempts_left):
        """
        Build a complete RL state vector.

        Parameters
        ----------
        embedding : np.ndarray
            CodeBERT embedding (768 dimensions)

        error_line : float
            Normalized error-line indicator.
            Use -1 if unknown.

        pass_rate : float
            Fraction of passed test cases.
            Value between 0 and 1.

        attempts_left : float
            Remaining debugging budget.
            Value between 0 and 1.

        Returns
        -------
        np.ndarray
            Complete state vector (771 dimensions)
        """
        
        if embedding.shape[0] != self.embedding_size:
            raise ValueError(
                f"Expected embedding size {self.embedding_size}, "
                f"got {embedding.shape[0]}"
            )
        extra_features = np.array(
            [
                error_line,
                pass_rate,
                attempts_left
            ],
            dtype=np.float32
        )
        
        state = np.concatenate(
            [
                embedding.astype(np.float32),
                extra_features
            ]
        )
        
        return state