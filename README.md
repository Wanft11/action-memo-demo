# Action Memo Demo

Action Memo is a hackathon MVP for soundcore Work 3200. It turns a meeting recording or pasted transcript into a personal action list with owners, deadlines, confidence, and exact source quotes.

## Features

- Paste a Chinese meeting transcript or upload an audio/video recording
- Extract personal and team action items
- Keep multi-person ownership and cross-sentence deadlines
- Trace every task to its original speaker and timestamp
- Confirm, edit, or ignore tasks in the browser
- Fall back to a local rule-based demo when no OpenAI API key is configured

## Requirements

- Python 3.10 or newer
- An OpenAI API key for real transcription and AI analysis

## Run locally

```bash
git clone https://github.com/Wanft11/action-memo-demo.git
cd action-memo-demo
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Add your own API key to `.env`:

```env
OPENAI_API_KEY="your-api-key"
```

Start the server:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Open <http://127.0.0.1:8000/demo>.

Without an API key, the app still opens and can show its built-in fallback demo. Real audio transcription and AI transcript analysis require the key.

## Run tests

```bash
python -m unittest discover -s tests -v
```

## API

- `GET /api/health` checks server health.
- `POST /api/meetings/analyze` accepts `multipart/form-data` with `current_user`, `transcript`, optional `audio`, and optional `markers` JSON.
- `GET /docs` opens the generated API documentation.

## Privacy

`.env`, local recordings, screenshots, and generated artifacts are excluded from Git. Each teammate must use their own API key and must not commit it.
