import base64
import os

import requests

base_url = (os.environ.get("ANTHROPIC_BASE_URL") or "https://api.anthropic.com").rstrip("/")
api_key = os.environ["ANTHROPIC_API_KEY"]

resp = requests.get(
    base_url + "/v1/models",
    headers={"Authorization": f"Bearer {api_key}"},
    timeout=30,
)
print(f"GET /v1/models -> status={resp.status_code}")
print(resp.text[:4000])
