import os

from anthropic_client import get_client

client = get_client()
resp = client.messages.create(
    model="claude-haiku-4-5-20251001",
    max_tokens=200,
    messages=[
        {
            "role": "user",
            "content": (
                "Reply with only the Russian translation, nothing else: "
                "'The quick brown fox jumps over the lazy dog.'"
            ),
        }
    ],
)
print("RAW RESPONSE:")
print(resp)
print("---")
print("TEXT:", resp.content[0].text)
