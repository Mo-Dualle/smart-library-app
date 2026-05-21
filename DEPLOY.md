# Deploy LibraryApp on Render (free tier)

## Create admin login (no Shell required)

Render **Shell is not free** on many plans. Use **one** of these:

### Method A — Environment variables (easiest on Render)

1. [Render Dashboard](https://dashboard.render.com) → your web service **smart-library** → **Environment**
2. Add variables (then **Save** and **Manual Deploy**):

   | Key | Example | Notes |
   |-----|---------|--------|
   | `ADMIN_EMAIL` | `admin@library.com` | What you type on **/login/** |
   | `ADMIN_PASSWORD` | `YourSecurePass123` | Min 8 characters |
   | `ADMIN_USERNAME` | `admin` | Optional |
   | `DATABASE_URL` | `postgresql://...` | Required — from Postgres service |

3. Wait for deploy to finish. Each build runs `bootstrap_admin`, which creates or updates that user.
4. Sign in at `https://your-app.onrender.com/login/` with **ADMIN_EMAIL** + **ADMIN_PASSWORD**.

> Do not commit passwords to Git. Only set them in the Render dashboard.

---

### Method B — From your Windows PC (same database as production)

1. **Render** → **PostgreSQL** → copy **External Database URL**  
   (If you use Neon, copy the connection string from Neon instead.)

2. Open PowerShell in your project folder:

```powershell
cd "c:\Users\hp\Desktop\react and django projecy\Django and js Projects"

$env:DATABASE_URL = "postgresql://USER:PASS@HOST/DB"   # paste External URL
$env:SECRET_KEY = "local-temp-key-only-for-this-command"
$env:DEBUG = "True"

python manage.py migrate
python manage.py createsuperuser
```

3. When prompted:
   - **Email address** → use this on `/login/` (e.g. `admin@library.com`)
   - **Username** → any unique name (not used for login)
   - **Password** → your password

4. Sign in on the live site with that **email** and password.

**Reset password** (if user already exists):

```powershell
python manage.py shell
```

```python
from library.models import Account
u = Account.objects.get(email__iexact="admin@library.com")
u.set_password("NewPassword123!")
u.is_active = True
u.is_staff = True
u.is_superuser = True
u.save()
exit()
```

---

### Method C — Register as a member only

1. Go to `/register/` on the live site  
2. Sign in at `/login/`  

This gives a **member** account, not staff. Use Method A or B for staff/superuser.

---

### Login tips

| Do | Don't |
|----|--------|
| Use **email** on `/login/` | Use **username** from `createsuperuser` |
| Use lowercase email (e.g. `admin@library.com`) | Mix random capitals |
| Wait for deploy after setting `ADMIN_*` env vars | Log in before deploy finishes |

Message **"Invalid email or password"** means email/password don't match the production database.

---

## Blueprint sync failed?

| Cause | What to do |
|-------|------------|
| **Already have a free Postgres** | Only **one** free DB per account. Use `render.yaml` + manual `DATABASE_URL`. |
| **Broken partial blueprint** | Delete blueprint instance → **New Blueprint Instance**. |
| **Wrong blueprint file** | Use `render.yaml` at repo root on `main`. |

---

## Deploy (recommended: `render.yaml`)

### 1. Push to GitHub

```bash
git add .
git commit -m "Deploy config and bootstrap admin"
git push
```

### 2. Blueprint or manual web service

- Blueprint file: **`render.yaml`**
- Service name: **smart-library**

### 3. PostgreSQL + `DATABASE_URL`

1. **New** → **PostgreSQL** (Free) — or use [Neon](https://neon.tech)
2. Copy **Internal Database URL** → web service env **`DATABASE_URL`**
3. Add **`ADMIN_EMAIL`** and **`ADMIN_PASSWORD`** (Method A above)
4. **Manual Deploy**

### 4. Open the app

`https://smart-library-xxxx.onrender.com/login/`

---

## Environment variables (production)

| Variable | Required | Purpose |
|----------|----------|---------|
| `SECRET_KEY` | Yes | Django secret (Render can generate) |
| `DEBUG` | Yes | `false` |
| `DATABASE_URL` | Yes | Postgres connection string |
| `ADMIN_EMAIL` | For admin | Login email without Shell |
| `ADMIN_PASSWORD` | For admin | Login password without Shell |
| `PYTHON_VERSION` | Optional | `3.11.9` |

`RENDER_EXTERNAL_URL` is set automatically by Render.

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

Media on the free web tier may be **lost on redeploy**. Use Cloudinary/S3 later for persistent images.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Invalid email or password | Set `ADMIN_EMAIL` / `ADMIN_PASSWORD`, redeploy; or Method B from PC |
| Shell not available | Use Method A or B above |
| `DisallowedHost` | Rely on `RENDER_EXTERNAL_URL` or add host to `ALLOWED_HOSTS` |
| CSRF error | `CSRF_TRUSTED_ORIGINS=https://your-host.onrender.com` |
| Database error | Set `DATABASE_URL` on web service, redeploy |
