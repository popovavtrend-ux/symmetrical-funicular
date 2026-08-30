import base64
import os

import requests

base_url = (os.environ.get("ANTHROPIC_BASE_URL") or "https://api.anthropic.com").rstrip("/")
api_key = os.environ["ANTHROPIC_API_KEY"]

for path in ("/v1/images/generations",):
    url = base_url + path
    resp = requests.post(
        url,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"model": "dall-e-3", "prompt": "a small orange bitcoin coin icon, minimal flat design", "n": 1, "size": "1024x1024"},
        timeout=60,
    )
    print(f"POST {url} -> status={resp.status_code}")
    print(resp.text[:2000])
