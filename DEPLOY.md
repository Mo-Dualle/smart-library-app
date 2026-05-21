# Deploy LibraryApp on Render (free tier)

## Blueprint sync failed?

Render often fails with a generic email and no details. Common causes:

| Cause | What to do |
|-------|------------|
| **Already have a free Postgres** | Only **one** free Postgres per account. Delete the old one, or use `render.yaml` (web only) and add `DATABASE_URL` manually. |
| **Broken partial blueprint** | Dashboard → **Blueprints** → **Smart-Library** → delete the blueprint instance, then create a **New Blueprint Instance** from a clean state. |
| **Wrong blueprint file** | Default must be `render.yaml` at the **repo root** on the branch Render uses (usually `main`). |
| **Old resources conflict** | If a failed sync created `libraryapp` / `libraryapp-db`, delete those services in the dashboard before re-syncing. |

**Recommended fix:** use the updated **`render.yaml`** (web service only). It syncs reliably. Then add the database manually (step 3 below).

---

## Deploy (recommended: `render.yaml`)

### 1. Push to GitHub

```bash
git add render.yaml build.sh DEPLOY.md
git commit -m "Fix Render blueprint for Smart-Library"
git push
```

### 2. New Blueprint Instance

1. [Render Dashboard](https://dashboard.render.com) → **Blueprints** → **New Blueprint Instance**
2. Connect repo **Smart-Library** (or your repo name)
3. Confirm blueprint file: **`render.yaml`**
4. Click **Apply**

### 3. Add PostgreSQL

**Option A — Render Postgres**

1. **New** → **PostgreSQL** → plan **Free**
2. Copy the **Internal Database URL**
3. Open web service **smart-library** → **Environment** → set:
   - `DATABASE_URL` = pasted URL
4. **Manual Deploy** → Deploy latest commit

**Option B — [Neon](https://neon.tech) free Postgres**

1. Create a project → copy connection string
2. Set `DATABASE_URL` on the web service (use `?sslmode=require` if needed)
3. Redeploy

### 4. Create admin user

Web service → **Shell**:

```bash
python manage.py createsuperuser
```

### 5. Open the app

Visit `https://smart-library-xxxx.onrender.com` (your URL is on the service page).

`RENDER_EXTERNAL_URL` is set automatically — you usually do **not** need `ALLOWED_HOSTS` or `CSRF_TRUSTED_ORIGINS` manually.

---

## One-click web + database (`render.full.yaml`)

Only if you have **no** free Render Postgres yet:

1. Blueprint setup → set custom blueprint path to **`render.full.yaml`**
2. Apply

If sync fails again, fall back to **`render.yaml`** + manual database above.

---

## Manual deploy (no Blueprint)

| Setting | Value |
|---------|--------|
| Build Command | `bash build.sh` |
| Start Command | `gunicorn libraryapp.wsgi:application --bind 0.0.0.0:$PORT` |
| `SECRET_KEY` | Generate |
| `DEBUG` | `false` |
| `DATABASE_URL` | Internal Postgres URL |
| `PYTHON_VERSION` | `3.11.9` |

---

## Local development

```bash
pip install -r requirements.txt
copy .env.example .env
python manage.py migrate
python manage.py runserver
```

Without `DATABASE_URL`, SQLite is used locally.

---

## Uploaded files

Media files on the free web tier may be **lost on redeploy**. Use Cloudinary/S3 later for persistent images.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Blueprint sync failed | Use `render.yaml`, delete old blueprint instance, push latest commit |
| `DisallowedHost` | Add your `*.onrender.com` host to `ALLOWED_HOSTS` (or rely on `RENDER_EXTERNAL_URL`) |
| CSRF error | Set `CSRF_TRUSTED_ORIGINS=https://your-host.onrender.com` |
| Build fails on `collectstatic` | Check deploy logs; ensure `library/static/main.js` exists |
| Database connection error | Set `DATABASE_URL` and redeploy |
