# Participant Chat Lab

This is a participant-facing chatbot site with:

- a premium static frontend designed for GitHub Pages
- a FastAPI backend that keeps the OpenAI API key server-side
- an admin control room for changing how the bot behaves
- optional image generation when participants ask for images
- transcript logging for research use

## Architecture

GitHub Pages can host the frontend, but it cannot safely host a live chatbot by itself because the OpenAI API key must stay private.

Use this split:

- `site/`: deploy to GitHub Pages
- `backend/`: deploy to Render

## Project layout

```text
participant-chat-lab/
  .github/workflows/deploy-pages.yml
  render.yaml
  backend/
    app/
    data/
    requirements.txt
    .env.example
  site/
    index.html
    admin.html
    app.js
    admin.js
    config.js
    styles.css
```

## Fastest deployment path

1. Create a new public GitHub repo.
2. Put this whole project into that repo, but do not upload `backend/.env`.
3. Push to `main`.
4. In Render, create a new Blueprint from that GitHub repo.
5. Render will detect `render.yaml` and create the backend service.
6. In Render, set:
   - `OPENAI_API_KEY`
   - `ADMIN_TOKEN`
7. Wait for the Render deploy to finish and copy the backend URL, which will look like `https://your-service-name.onrender.com`.
8. In GitHub, open `Settings -> Secrets and variables -> Actions -> Variables`.
9. Add a repository variable named `PAGES_API_BASE_URL` with your Render backend URL.
10. In GitHub, open `Actions` and re-run the `Deploy GitHub Pages` workflow.
11. In GitHub, enable Pages to deploy from GitHub Actions if prompted.

Your public frontend URL will be:

`https://<your-github-username>.github.io/<repo-name>/`

The included Pages workflow injects `PAGES_API_BASE_URL` into `site/config.js` automatically, so you do not need to hand-edit the frontend after deployment.

## Backend setup

### Local run

```bash
pip install -r backend/requirements.txt
```

Create `backend/.env` and set:

- `OPENAI_API_KEY`
- `ADMIN_TOKEN`
- `ALLOWED_ORIGINS` if you want something more restrictive than `*`
- optionally `MOCK_MODE=true` for local testing without an API key

Run locally:

```bash
uvicorn app.main:app --reload --app-dir backend
```

### Render notes

- `render.yaml` is already configured for a free Python web service.
- The service exposes `/health` for Render health checks.
- Free Render services sleep after inactivity and can take a short time to wake up.
- Render free storage is ephemeral, so generated images and transcripts are not permanent there.

## Admin controls

Open `admin.html` on the deployed site and enter the admin token.

You can change:

- bot name and display copy
- system prompt
- starter prompts
- welcome message
- response temperature
- max turns
- image generation on/off
- image styling prompt

Those settings are persisted in `backend/data/bot-config.json`.

## Notes

- Sessions are stored in memory while the server is running.
- Transcripts are written to `backend/data/transcripts/`.
- If you need long-lived sessions or permanent analytics, add a database next.
- The admin token is a lightweight control for a lab prototype. For public use, put the admin page behind real authentication.
- If `OPENAI_API_KEY` is missing or `MOCK_MODE=true`, the app returns mock text responses and a placeholder generated image so you can test the interface locally.
- `site/config.js` is populated automatically during the GitHub Pages workflow from the repository variable `PAGES_API_BASE_URL`.
