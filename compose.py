import os


def compose_post_via_claude(author, text, url):
    from anthropic_client import get_client

    client = get_client()
    prompt = (
        "You write short Telegram news posts in Russian for a crypto news "
        "channel, based on a single X (Twitter) post by a known crypto "
        "figure. Faithfully convey what the person actually said or "
        "announced - do not invent facts, numbers, or quotes that aren't in "
        "the original text. Keep crypto terms as commonly used in Russian "
        "crypto media. Write 2-4 sentences, in a neutral news tone (e.g. "
        f'"{author} заявил, что...").\n\n'
        f"Author: {author}\n"
        f"Post text: {text}\n\n"
        "Reply with only the Russian post text, nothing else."
    )
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text.strip()


def compose_post_via_translation(author, text, url):
    from deep_translator import GoogleTranslator

    translated = text
    if text:
        try:
            translated = GoogleTranslator(source="en", target="ru").translate(text)
        except Exception as e:
            print(f"Google Translate failed, posting original text: {e}")
    return f"{author} написал(а):\n{translated}"


def compose_post(author, text, url):
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            return compose_post_via_claude(author, text, url)
        except Exception as e:
            print(f"Claude composition failed, falling back to plain translation: {e}")
    return compose_post_via_translation(author, text, url)
