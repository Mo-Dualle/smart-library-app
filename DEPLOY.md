# Deploy LibraryApp on Render (free tier)

This project is configured for [Render](https://render.com): Django + Gunicorn + WhiteNoise + PostgreSQL.

## Quick deploy (Blueprint)

1. Push the repo to **GitHub** (already done).
2. Go to [Render Dashboard](https://dashboard.render.com) → **New** → **Blueprint**.
3. Connect the GitHub repo. Render reads `render.yaml` and creates:
   - a **PostgreSQL** database (`libraryapp-db`)
   - a **Web Service** (`libraryapp`)
4. After the first deploy finishes, open the web service → **Shell** and run:

   ```bash
   python manage.py createsuperuser
   ```

5. Visit your app URL (e.g. `https://libraryapp-xxxx.onrender.com`).

## Required environment variables (manual deploy)

If you create the web service by hand instead of Blueprint, set:

| Variable | Example |
|----------|---------|
| `SECRET_KEY` | long random string (Render can generate) |
| `DEBUG` | `False` |
| `ALLOWED_HOSTS` | `your-app.onrender.com` |
| `CSRF_TRUSTED_ORIGINS` | `https://your-app.onrender.com` |
| `DATABASE_URL` | Internal URL from Render Postgres |

**Build command:** `./build.sh`  
**Start command:** `gunicorn libraryapp.wsgi:application --bind 0.0.0.0:$PORT --workers 2 --timeout 120`

## Local development

```bash
python -m venv venv
venv\Scripts\activate          # Windows
pip install -r requirements.txt
copy .env.example .env         # edit SECRET_KEY
python manage.py migrate
python manage.py runserver
```

Without `DATABASE_URL`, SQLite (`db.sqlite3`) is used locally.

## Uploaded files (important)

Avatars, book covers, and author/category photos are stored in `media/` on disk.

On Render’s **free** web tier, that disk is **ephemeral** — uploads may be **lost on redeploy**.

For a production demo with persistent images, add object storage later (e.g. Cloudinary, S3, Supabase Storage).

## Free tier notes

- The app **spins down** after inactivity; the first visit may take 30–60 seconds.
- Free Postgres on Render may have limits; check current Render pricing.

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `DisallowedHost` | Add your `*.onrender.com` host to `ALLOWED_HOSTS`. |
| CSRF error on login | Set `CSRF_TRUSTED_ORIGINS` to `https://your-exact-host.onrender.com`. |
| Static files 404 | Ensure `build.sh` ran `collectstatic`; check deploy logs. |
| Database errors | Confirm `DATABASE_URL` is linked to the web service. |
