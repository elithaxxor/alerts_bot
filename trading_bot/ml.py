import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline

class PriceDirectionModel:
    """Train a simple logistic regression to predict next bar direction."""

    def __init__(self):
        self.model = make_pipeline(StandardScaler(), LogisticRegression())
        self.is_fitted = False

    def fit(self, df: pd.DataFrame) -> None:
        df = df.dropna().copy()
        df['target'] = (df['close'].shift(-1) > df['close']).astype(int)
        features = df[['ma_20','ma_50','rsi','adx']].values
        self.model.fit(features, df['target'])
        self.is_fitted = True

    def predict_proba(self, df: pd.DataFrame) -> float:
        if not self.is_fitted:
            return 0.5
        last = df.dropna().iloc[-1]
        X = last[['ma_20','ma_50','rsi','adx']].values.reshape(1, -1)
        proba = self.model.predict_proba(X)[0,1]
        return proba
