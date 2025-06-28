from random import choice

def analyze_sentiment(texts):
    """Return a dummy sentiment score for a list of texts."""
    if not texts:
        return {"sentiment": "neutral", "score": 0.0}
    # Placeholder: randomly choose sentiment
    sentiment = choice(["positive", "neutral", "negative"])
    score = {"positive": 0.7, "neutral": 0.0, "negative": -0.7}[sentiment]
    return {"sentiment": sentiment, "score": score}
