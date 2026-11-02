import os
from pathlib import Path

from sarvamai import SarvamAI


# Load SARVAM_API_KEY from this project's .env without an extra dependency.
for line in (Path(__file__).parent / ".env").read_text().splitlines():
    name, separator, value = line.partition("=")
    if separator and name.strip() == "SARVAM_API_KEY":
        os.environ.setdefault("SARVAM_API_KEY", value.strip().strip("\"'"))
        break

api_key = os.getenv("SARVAM_API_KEY")
if not api_key:
    raise SystemExit("Add your key to .env as SARVAM_API_KEY=... and run again.")

client = SarvamAI(api_subscription_key=api_key)
response = client.chat.completions(
    model="sarvam-105b-conversations",
    messages=[{"role": "user", "content": "Say hello in one sentence."}],
)
print(response.choices[0].message.content)
