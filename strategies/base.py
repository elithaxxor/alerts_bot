class Strategy:
    """Abstract strategy interface."""
    def run(self, prices):
        raise NotImplementedError
