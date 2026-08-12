# AI Fax Assistant

Ingest a scanned fax, extract required fields with Anthropic Claude vision against a single markdown requirements template, optionally place an ElevenLabs outbound voice call for missing data, and write one `case.md` artifact per case.

## Stack

- **Backend**: Python 3.11+, FastAPI, SQLite (users + call history), Redis sessions, Anthropic, ElevenLabs, PyMuPDF
- **Frontend**: React + Vite + TypeScript
- **Local runtime**: Docker Compose (`api`, `web`, `redis`)

## Roles

| Role | Access |
| --- | --- |
| `admin` | Users, requirements, all cases, all call history |
| `operator` | Upload/cases, place calls, own call history |

Default admin is seeded from `ADMIN_USERNAME` / `ADMIN_PASSWORD` on first boot. Change `ADMIN_PASSWORD` before any shared deploy.

## Quick start (Docker)

```bash
cp .env.example .env
# fill ANTHROPIC_* / ELEVENLABS_* as needed; change SESSION_SECRET and ADMIN_PASSWORD
docker compose up --build
```

- UI: http://localhost:8080
- API: http://localhost:8000
- Redis: localhost:6379
- Data (cases + `app.db`): `./data`

## Hybrid local (no full Compose)

```bash
docker compose up -d redis
cp .env.example .env

cd backend
uv sync
uv run uvicorn app.main:app --reload --port 8000

cd ../frontend
npm install
npm run dev
```

Open http://localhost:5173 — Vite proxies `/api` to the backend. Redis must be reachable at `REDIS_URL`.

## Environment

| Variable | Purpose |
| --- | --- |
| `ANTHROPIC_API_KEY` | Claude vision extraction |
| `ANTHROPIC_MODEL` | Defaults to `claude-sonnet-4-20250514` |
| `ELEVENLABS_API_KEY` | Outbound Conversational AI calls |
| `ELEVENLABS_AGENT_ID` | Agent configured in ElevenLabs |
| `ELEVENLABS_AGENT_PHONE_NUMBER_ID` | Phone number ID from ElevenLabs dashboard |
| `ELEVENLABS_WEBHOOK_SECRET` | HMAC secret for `/api/webhooks/elevenlabs` (required unless insecure flag) |
| `ALLOW_INSECURE_WEBHOOKS` | Local-only; accept unsigned webhooks when secret unset (default `false`) |
| `API_KEY` | Optional service bypass (`X-API-Key` / Bearer). Empty for normal session auth |
| `REDIS_URL` | Session store (default `redis://localhost:6379/0`) |
| `DATABASE_PATH` | SQLite path (default `./data/app.db`) |
| `SESSION_SECRET` | Reserved for signed-session hardening; change in shared envs |
| `SESSION_TTL_SECONDS` | Session lifetime (default 7 days) |
| `SESSION_COOKIE_SECURE` | Set `true` behind HTTPS |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | Seeded admin on first boot |
| `MIN_PASSWORD_LENGTH` | Password policy for create/reset (default 8) |
| `LOGIN_RATE_LIMIT` / `LOGIN_RATE_WINDOW_SECONDS` | Login attempt throttle (Redis) |
| `DATA_DIR` | Case storage (default `./data`) |
| `WEBHOOK_BASE_URL` | Public base URL for webhooks (ngrok in local dev) |
| `MAX_UPLOAD_BYTES` | Upload size cap (default 20 MiB) |

## ElevenLabs phone setup (one-time)

1. Create a Conversational AI agent in [ElevenLabs Agents](https://elevenlabs.io/app/agents).
2. Import a Twilio number (or SIP trunk / verified caller ID) under **Phone Numbers**.
3. Link that number to your agent.
4. Copy `agent_id` and the phone number’s `agent_phone_number_id` into `.env`.
5. Configure agent dynamic variables (optional but recommended): `missing_fields`, `known_facts`, `patient_name`, `call_reason`, `case_id`.
6. For local webhooks, expose the API with ngrok and point ElevenLabs post-call webhook to:
   `{WEBHOOK_BASE_URL}/api/webhooks/elevenlabs`

If the webhook is unavailable, the backend also polls the conversation for a transcript after a call is placed.

## Workflow

1. Sign in (admin edits **Requirements** under Admin).
2. **Upload** a PDF or image fax.
3. Claude vision extracts fields into `data/cases/{id}/case.json` and `case.md`.
4. If required fields are missing and a phone number is present → status `awaiting_call`.
5. On the case page, confirm **Place call** → ElevenLabs outbound call (logged in SQLite).
6. Transcript is merged back; final fields and discussion land in `case.md`.

## Persistence

- **Cases**: `data/cases/{id}/` (scan, `case.json`, `case.md`) — unchanged
- **Users + call history index**: SQLite at `DATABASE_PATH`
- **Login sessions**: Redis (`session:{id}` → user payload; HttpOnly cookie)

## API

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| `POST` | `/api/auth/login` | public | Create session cookie |
| `POST` | `/api/auth/logout` | public | Clear session |
| `GET` | `/api/auth/me` | user | Current user |
| `GET` / `POST` / `PATCH` | `/api/users` | admin | User management |
| `GET` | `/api/calls` | user | Call history (own; admin sees all) |
| `POST` | `/api/cases` | user | Upload fax and start extraction |
| `GET` | `/api/cases` | user | List cases |
| `GET` | `/api/cases/{id}` | user | Case detail |
| `GET` | `/api/cases/{id}/scan` | user | Serve scan |
| `POST` | `/api/cases/{id}/call` | user | Confirm and place ElevenLabs call |
| `POST` | `/api/webhooks/elevenlabs` | HMAC | Call completion webhook |
| `GET` / `PUT` | `/api/requirements` | admin | Read/update requirements MD |

## Deploy on Fly.io

Two apps: **API** (FastAPI + SQLite volume) and **web** (nginx UI proxying `/api` over Fly private networking). Sessions need Redis (Upstash via `fly redis`).

1. Install CLI and log in:

```bash
curl -L https://fly.io/install.sh | sh
fly auth login
```

2. Create apps + volume (skip if names are taken — edit `app` in `fly.api.toml` / `fly.web.toml` and `API_UPSTREAM` in `fly.web.toml`):

```bash
fly apps create ai-fax-assistant-api
fly apps create ai-fax-assistant-web
fly volumes create fax_data --app ai-fax-assistant-api --region iad --size 1
```

3. Redis (free Upstash tier via Fly):

```bash
fly redis create --name ai-fax-assistant-redis --region iad
# copy the private Redis URL, then:
fly secrets set REDIS_URL='redis://...' --app ai-fax-assistant-api
```

4. App secrets (use strong values; never commit `.env`):

```bash
fly secrets set --app ai-fax-assistant-api \
  ANTHROPIC_API_KEY=... \
  ELEVENLABS_API_KEY=... \
  ELEVENLABS_AGENT_ID=... \
  ELEVENLABS_AGENT_PHONE_NUMBER_ID=... \
  ELEVENLABS_WEBHOOK_SECRET=... \
  SESSION_SECRET="$(openssl rand -hex 32)" \
  ADMIN_USERNAME=admin \
  ADMIN_PASSWORD='...' \
  WEBHOOK_BASE_URL=https://ai-fax-assistant-web.fly.dev \
  CORS_ORIGINS='["https://ai-fax-assistant-web.fly.dev"]'
```

5. Deploy:

```bash
fly deploy --config fly.api.toml
fly deploy --config fly.web.toml
# or: ./scripts/fly-deploy.sh
```

- UI: `https://ai-fax-assistant-web.fly.dev`
- Health: `https://ai-fax-assistant-api.fly.dev/api/health`
- ElevenLabs webhook: `https://ai-fax-assistant-web.fly.dev/api/webhooks/elevenlabs`

Free allowance is limited (shared VMs + volume). Machines may auto-stop; API `min_machines_running` is `1` so webhooks/sessions stay warm. Anthropic/ElevenLabs usage is billed separately.

## Formatting / lint

```bash
cd backend
uv run black app
uv run ruff check app

cd ../frontend
npm run lint
npm run build
```

## CI / CD (GitHub Actions)

Workflow: [`.github/workflows/ci.yml`](.github/workflows/ci.yml)

| Trigger | Jobs |
| --- | --- |
| Pull request | Backend ruff + black, frontend oxlint + build, Docker image builds |
| Push to `main` | Same checks, then deploy to Fly.io |

### One-time Fly.io setup

1. Install [`flyctl`](https://fly.io/docs/flyctl/install/) and log in: `fly auth login`
2. Create the app (change the name in `fly.toml` if taken):

```bash
fly apps create ai-fax-assistant
fly volumes create fax_data --region ams --size 1 -a ai-fax-assistant
```

3. Set secrets (at least these):

```bash
fly secrets set \
  ANTHROPIC_API_KEY=... \
  ELEVENLABS_API_KEY=... \
  ELEVENLABS_AGENT_ID=... \
  ELEVENLABS_AGENT_PHONE_NUMBER_ID=... \
  ELEVENLABS_WEBHOOK_SECRET=... \
  ADMIN_PASSWORD='a-strong-password' \
  SESSION_SECRET="$(openssl rand -hex 32)" \
  WEBHOOK_BASE_URL=https://ai-fax-assistant.fly.dev \
  CORS_ORIGINS='["https://ai-fax-assistant.fly.dev"]' \
  -a ai-fax-assistant
```

4. In the GitHub repo: **Settings → Secrets and variables → Actions**, add repository secret `FLY_API_TOKEN` from:

```bash
fly tokens create deploy -x 999999h -a ai-fax-assistant
```

5. Push to `main` (or run the **CI** workflow manually). Deploy runs only after lint/build succeed on `main`.

Local smoke-build of the production image:

```bash
docker build -t ai-fax-assistant .
```
