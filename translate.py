import os
import re


def _parse_response(text):
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


def translate_via_claude_opinion(title, summary):
    """Personal-opinion rewrite in first person, concise, no financial-advice
    guardrails - alternates with translate_via_claude_explainer so FreshLive
    posts don't all read like the same template."""
    from anthropic_client import extract_text, get_client

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
        "so posts don't all sound the same. Also vary your word choice "
        "*within* the paragraph, not just the opening - don't lean on "
        "'это' or any other single word as a crutch every sentence; use "
        "the range of Russian phrasing (referring back to the specific "
        "thing by name, a synonym, restructuring the sentence, etc.)>\n\n"
        f"Title: {title}\n"
        f"Summary: {summary}"
    )
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=800,
        messages=[{"role": "user", "content": prompt}],
    )
    return _parse_response(extract_text(resp).strip())


def translate_via_claude_explainer(title, summary):
    """Full, thorough rewrite for a total-beginner audience, no financial
    advice - alternates with translate_via_claude_opinion."""
    from anthropic_client import extract_text, get_client

    client = get_client()
    prompt = (
        "You are the editor of a Russian-language crypto news AND education "
        "Telegram channel for a broad general audience - write for readers "
        "with no finance or tech background at all, from a schoolkid to a "
        "pensioner. Do a full, thorough rewrite in your own words and your "
        "own structure - do not just swap synonyms or lightly reword "
        "sentences, genuinely re-explain the story so it reads as original "
        "writing, not a paraphrase (the source material below may already "
        "be in Russian, or in English). Never mention or refer to 'the "
        "article', 'the source', or where the information came from.\n\n"
        "Write in very simple, plain Russian - short sentences, no jargon. "
        "If you must use a crypto/finance term (Bitcoin, DeFi, staking, a "
        "ticker, etc.), briefly explain what it means in plain words right "
        "where it first appears, as if to someone who has never heard of "
        "it before. Be accurate - do not invent facts, numbers, or quotes "
        "that aren't in the source material.\n\n"
        "This is strictly NOT financial advice: never suggest buying, "
        "selling, holding, or investing; never predict prices or call "
        "something a good/bad investment; never use phrases like 'стоит "
        "купить', 'выгодно', 'не упустите шанс'. Explain what happened and "
        "why it matters as information, not as a recommendation.\n\n"
        "Reply in exactly this format, and nothing else:\n"
        "Title: <a short catchy title>\n"
        "Context: <explain what happened and why, in your own words, in "
        "enough detail that a complete beginner understands it - 2-4 plain "
        "sentences, explaining any term you use>\n"
        "Opinion: <your own perspective on why this matters or what it "
        "helps readers understand about crypto in general, in first "
        "person, 2-3 sentences - explanation/context, never a buy/sell "
        "recommendation. Sound like a real person talking, not a template: "
        "do NOT open with 'Я считаю', 'По-моему' or any other fixed phrase "
        "- vary how each post starts (a reaction, a comparison, a "
        "question, straight commentary, etc.) so posts don't all sound "
        "the same. Also vary your word choice *within* the paragraph, not "
        "just the opening - don't lean on 'это' or any other single word "
        "as a crutch every sentence; use the range of Russian phrasing "
        "(referring back to the specific thing by name, a synonym, "
        "restructuring the sentence, etc.)>\n\n"
        f"Title: {title}\n"
        f"Summary: {summary}"
    )
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}],
    )
    return _parse_response(extract_text(resp).strip())


def explain_topic(topic):
    """Write a standalone educational post about a crypto/finance concept -
    not tied to any news story. Same beginner-friendly, no-financial-advice
    voice as translate_via_claude_explainer."""
    from anthropic_client import extract_text, get_client

    client = get_client()
    prompt = (
        "You are the editor of a Russian-language crypto/finance educational "
        "Telegram channel for a broad general audience - readers with zero "
        "background, from a schoolkid to a pensioner. Write a short "
        f"educational post in Russian explaining this concept: '{topic}'. "
        "Explain it in the simplest possible way, using a simple real-world "
        "analogy if it helps, as if teaching someone who has never heard the "
        "term before. Do not assume any prior crypto/finance knowledge. Be "
        "accurate - do not invent facts or numbers.\n\n"
        "This is purely educational, NOT financial advice: never suggest "
        "buying, investing, or that using/owning this makes financial "
        "sense - describe only what it is and how it works.\n\n"
        "Reply in exactly this format, and nothing else:\n"
        "Title: <a short catchy title>\n"
        "Explanation: <the full explanation in simple Russian, 4-6 "
        "sentences, with an analogy if it helps>"
    )
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=800,
        messages=[{"role": "user", "content": prompt}],
    )
    text = extract_text(resp).strip()

    title_m = re.search(r"Title:\s*(.+)", text)
    explanation_m = re.search(r"Explanation:\s*(.+)", text, re.DOTALL)

    if title_m:
        title = title_m.group(1).strip()
        explanation = explanation_m.group(1).strip() if explanation_m else ""
    else:
        lines = text.split("\n", 1)
        title = lines[0].strip()
        explanation = lines[1].strip() if len(lines) > 1 else ""

    return title, explanation


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


STYLES = ("opinion", "explainer")

CYRILLIC_RE = re.compile(r"[а-яёА-ЯЁ]")


def _looks_russian(title, summary):
    return bool(CYRILLIC_RE.search(f"{title} {summary}"))


def translate(title, summary, style="explainer"):
    """style picks the voice for this one post - "opinion" (personal take,
    first person, no beginner explanations) or "explainer" (full beginner
    rewrite, no financial advice). Callers alternate between the two across
    posts so the channel doesn't read as one repetitive template.

    Both Claude and the Google Translate fallback occasionally return the
    source text unchanged (Claude ignoring the "write in Russian"
    instruction; deep-translator swallowing its own errors and handing back
    the original) with no exception raised - silently posting the source
    language instead of failing loudly. Checking for actual Cyrillic output
    catches that so the caller can skip/retry the entry instead of
    publishing an English post.
    """
    claude_fn = translate_via_claude_opinion if style == "opinion" else translate_via_claude_explainer
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            title_ru, summary_ru = claude_fn(title, summary)
            if _looks_russian(title_ru, summary_ru):
                return title_ru, summary_ru
            print("Claude translation returned no Russian text, falling back to Google Translate")
        except Exception as e:
            print(f"Claude translation failed, falling back to Google Translate: {e}")

    title_ru, summary_ru = translate_via_google(title, summary)
    if not _looks_russian(title_ru, summary_ru):
        raise RuntimeError("Translation produced no Russian text (Claude and Google Translate both failed)")
    return title_ru, summary_ru
