import os
import re


def translate_via_claude(title, summary):
    from anthropic_client import get_client

    client = get_client()
    prompt = (
        "You are the owner of a crypto news Telegram channel, writing a short "
        "post in Russian about a piece of news (the source material below may "
        "already be in Russian, or in English). Never mention or refer to "
        "'the article', 'the source', or where the information came from. "
        "Keep crypto terms (Bitcoin, DeFi, token tickers, etc.) as commonly "
        "used in Russian crypto media. Be accurate - do not invent facts, "
        "numbers, or quotes that aren't in the source material. Write in "
        "short, plain sentences so the post is easy to scan on a phone "
        "screen - avoid long, dense run-on sentences.\n\n"
        "Reply in exactly this format, and nothing else:\n"
        "Title: <a short catchy title>\n"
        "Context: <1-2 plain sentences stating the news itself - what "
        "happened, in your own words, not a translation>\n"
        "Opinion: <your personal opinion/commentary on it in first person - "
        "why it matters, what you think it means, 2-3 sentences. Sound like "
        "a real person talking, not a template: do NOT open with 'Я считаю', "
        "'По-моему' or any other fixed phrase - vary how each post starts "
        "(a reaction, a comparison, a question, straight commentary, etc.) "
        "so posts don't all sound the same>\n\n"
        f"Title: {title}\n"
        f"Summary: {summary}"
    )
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}],
    )
    text = resp.content[0].text.strip()

    title_m = re.search(r"Title:\s*(.+)", text)
    context_m = re.search(r"Context:\s*(.+?)(?=\n\s*Opinion:|\Z)", text, re.DOTALL)
    opinion_m = re.search(r"Opinion:\s*(.+)", text, re.DOTALL)

    if title_m:
        translated_title = title_m.group(1).strip()
        context = context_m.group(1).strip() if context_m else ""
        opinion = opinion_m.group(1).strip() if opinion_m else ""
        # Keep context and opinion as two visually separate paragraphs
        # instead of one dense wall of text.
        parts = [p for p in (context, f"\U0001f4ad {opinion}" if opinion else "") if p]
        translated_summary = "\n\n".join(parts)
    else:
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
