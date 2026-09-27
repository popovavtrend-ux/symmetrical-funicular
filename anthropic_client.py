import os


def get_client():
    import anthropic

    base_url = os.environ.get("ANTHROPIC_BASE_URL")
    if base_url:
        return anthropic.Anthropic(base_url=base_url)
    return anthropic.Anthropic()


def extract_text(response):
    """The first content block isn't always the text - a model can lead
    with a ThinkingBlock (extended thinking), which has no .text attribute.
    Scan for the actual text block instead of assuming content[0] is it."""
    for block in response.content:
        if getattr(block, "type", None) == "text":
            return block.text
    return ""


# The Claude model available through ANTHROPIC_BASE_URL has shifted under
# us before without any change on our side - a model ID that posted fine
# all morning started getting rejected outright a few hours later. Try a
# few IDs, newest/cheapest first, instead of hard-failing over one
# deprecated snapshot. Shared by every module that calls the Claude API
# (translation, stock-photo query generation, move explanations) so a
# model outage is handled the same way everywhere instead of each call
# site hardcoding its own model string.
MODEL_CANDIDATES = (
    "claude-haiku-4-5-20251001",
    "claude-haiku-4-5",
    "claude-3-5-haiku-20241022",
    "claude-sonnet-5",
    "claude-3-5-sonnet-20241022",
)


def create_message(client, **kwargs):
    """Tries each candidate model in turn. Previously this only retried on
    an error whose text literally contained "Unsupported model" - the
    proxy's actual wording for that ("The request contains invalid or
    unsupported input") doesn't match that substring, so a single missing
    model (e.g. every Haiku snapshot got dropped from the account with no
    notice) took down every single call using this function instead of
    silently falling through to a model that still works.

    Checking models.list() up front and only trying candidates it actually
    lists sidesteps guessing the proxy's error wording entirely. If that
    listing call itself fails, fall back to trying every candidate blind -
    a real content error still surfaces correctly (it fails identically on
    every candidate, so the last one's exception is the one raised)."""
    try:
        available = {m.id for m in client.models.list().data}
        candidates = [m for m in MODEL_CANDIDATES if m in available]
        if not candidates:
            print(f"None of our candidate models are in the account's list: {sorted(available)}")
            candidates = list(MODEL_CANDIDATES)
    except Exception as e:
        print(f"Could not list available models, trying every candidate blind: {e}")
        candidates = list(MODEL_CANDIDATES)

    last_error = None
    for model in candidates:
        try:
            return client.messages.create(model=model, **kwargs)
        except Exception as e:
            last_error = e
    raise last_error
