import os


def translate_via_claude(title, summary):
    from anthropic_client import get_client

    client = get_client()
    prompt = (
        "You are the owner of a crypto news Telegram channel, writing a short "
        "post in Russian that shares your own take on a piece of news (the "
        "source material below may already be in Russian, or in English). "
        "Write it as your personal opinion/commentary in first person - not "
        "as a news report, not as a translation, and never mention or refer "
        "to 'the article', 'the source', or where the information came from. "
        "Rewrite the key facts in your own words and add a brief personal "
        "take on why it matters. Keep crypto terms (Bitcoin, DeFi, token "
        "tickers, etc.) as commonly used in Russian crypto media. Be "
        "accurate - do not invent facts, numbers, or quotes that aren't in "
        "the source material. Reply with exactly two lines: a short catchy "
        "title, then your commentary (2-3 sentences max).\n\n"
        f"Title: {title}\n"
        f"Summary: {summary}"
    )
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}],
    )
    text = resp.content[0].text.strip()
    lines = text.split("\n", 1)
    translated_title = lines[0].strip()
    translated_summary = lines[1].strip() if len(lines) > 1 else ""
    return translated_title, translated_summary


def _safe_google_translate(tr, text):
    if not text:
        return ""
    try:
        return tr.translate(text)
    except Exception as e:
        print(f"Google Translate failed for a chunk, keeping original text: {e}")
        return text


def translate_via_google(title, summary):
    from deep_translator import GoogleTranslator

    tr = GoogleTranslator(source="en", target="ru")
    translated_title = _safe_google_translate(tr, title)
    translated_summary = _safe_google_translate(tr, summary)
    return translated_title, translated_summary


def translate(title, summary):
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            return translate_via_claude(title, summary)
        except Exception as e:
            print(f"Claude translation failed, falling back to Google Translate: {e}")
    return translate_via_google(title, summary)
