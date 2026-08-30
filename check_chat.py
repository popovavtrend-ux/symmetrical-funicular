import base64
import os

import requests

base_url = (os.environ.get("ANTHROPIC_BASE_URL") or "https://api.anthropic.com").rstrip("/")
api_key = os.environ["ANTHROPIC_API_KEY"]

url = base_url + "/v1/images/generations"
for model in ("dall-e-2", "gpt-image-1", "stable-diffusion-3", "flux-1", "flux-schnell", "sdxl"):
    resp = requests.post(
        url,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"model": model, "prompt": "a small orange bitcoin coin icon, minimal flat design", "n": 1, "size": "1024x1024"},
        timeout=60,
    )
    print(f"model={model!r} -> status={resp.status_code}")
    print(resp.text[:500])
    print("---")
