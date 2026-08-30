import os


def translate_via_claude(title, summary):
    from anthropic_client import get_client

    client = get_client()
    prompt = (
        "You write an original short news post in Russian for a crypto news "
        "Telegram channel, based on the article title/summary below (the "
        "source may already be in Russian, or in English). Rewrite the key "
        "facts in your own words as a journalist summarizing the news for "
        "their own audience - do not translate or copy sentences verbatim, "
        "even if the source is already Russian. Keep crypto terms (Bitcoin, "
        "DeFi, token tickers, etc.) as commonly used in Russian crypto "
        "media. Be accurate - do not invent facts, numbers, or quotes that "
        "aren't in the source. Reply with exactly two lines: the rewritten "
        "title, then the rewritten summary (2-3 sentences max).\n\n"
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
