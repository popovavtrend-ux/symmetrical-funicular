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
