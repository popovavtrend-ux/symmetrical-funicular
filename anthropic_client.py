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
# all morning started getting rejected outright with "Unsupported model"
# a few hours later, which silently took down every single call using it.
# Try a few IDs, newest first, instead of hard-failing over one deprecated
# snapshot. Shared by every module that calls the Claude API (translation,
# stock-photo query generation) so a model outage is handled the same way
# everywhere instead of each call site hardcoding its own model string.
MODEL_CANDIDATES = (
    "claude-haiku-4-5-20251001",
    "claude-haiku-4-5",
    "claude-3-5-haiku-20241022",
    "claude-sonnet-5",
    "claude-3-5-sonnet-20241022",
)


def create_message(client, **kwargs):
    last_error = None
    for model in MODEL_CANDIDATES:
        try:
            return client.messages.create(model=model, **kwargs)
        except Exception as e:
            if "Unsupported model" not in str(e):
                raise
            last_error = e
    # Every candidate above was rejected outright - log what the account
    # actually has access to, so the next occurrence of this is a five
    # second fix instead of another round of guessing model ID strings.
    try:
        available = [m.id for m in client.models.list().data]
        print(f"All candidate models unsupported; models.list() reports: {available}")
    except Exception as list_err:
        print(f"All candidate models unsupported, and could not list available models either: {list_err}")
    raise last_error
