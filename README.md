# LibraryApp

A library management web app built with Django. Members can browse the catalog, borrow books, pay fines, and manage their profile. Staff use a separate admin area to run day-to-day operations: catalog, loans, fines, users, and permission groups.

The front end uses server-rendered HTML with Bootstrap 5 and a small amount of JavaScript for confirmations, modals, and inline actions. There is no separate React or Vue app in this repository; the “js” in the project name refers to the client-side scripts that support the Django templates.

## What it does

**For members**

- Browse books, authors, and categories  
- Borrow and return books, with reservations when nothing is available  
- View and pay fines, track reading sessions  
- Register, log in with email, and edit profile (including avatar)

**For staff**

Staff sign in to `/admin-panel/` and land on a dashboard that matches their role:

- **Librarian** — books, authors, categories, loans, reservations  
- **Finance** — fines and payment overview  
- **User manager** — members and staff accounts (without full system admin powers)  
- **Full overview** — superusers and staff with broad access see everything in one place  

Access is controlled with Django’s built-in **groups** and **permissions**. Each group gets a specific set of model permissions (for example `change_book`, `view_account`). There is no parallel custom role system in code; the database is the source of truth.

Default groups created by migrations include Librarian, Finance Officer, User Manager, and Full Admin. You can add more groups from the staff UI and toggle permissions with on/off controls.

## Tech stack

- Python 3.11+  
- Django 5.2  
- PostgreSQL (via `DATABASE_URL` in environment)  
- Bootstrap 5, Font Awesome  
- Pillow for images  
- WhiteNoise for static files in production  

## Getting started

### Prerequisites

- Python 3.11 or newer  
- PostgreSQL running locally or remotely  
- A virtual environment is recommended  

### Setup

Clone the repository and open the project folder:

```bash
cd "Django and js Projects"
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
pip install django-environ
```

Create a `.env` file in the project root (same level as `manage.py`):

```env
SECRET_KEY=your-secret-key-here
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
DATABASE_URL=postgres://USER:PASSWORD@localhost:5432/library_db
```

Replace the database URL with your own credentials and database name.

Run migrations and start the server:

```bash
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Open [http://127.0.0.1:8000/](http://127.0.0.1:8000/) for the public site. Django admin is at `/admin/`. The staff portal is at `/admin-panel/` after you log in as a staff user or superuser.

### First-time staff access

A superuser can do everything. For other staff, assign them to one or more groups under **Groups** in the staff panel (or via Django admin). The app sets `is_staff` automatically when a user belongs to a group that grants library permissions.

User managers can create staff accounts and assign groups, but they cannot grant Full Admin access or edit system-level group definitions the way a superuser can.

## Project layout

| Path | Purpose |
|------|---------|
| `libraryapp/` | Django project settings and root URLs |
| `library/` | Main app: models, views, templates, migrations |
| `library/roles.py` | Permission helpers and staff dashboard routing |
| `library/templates/` | HTML templates for members and staff |
| `library/static/main.js` | Shared client-side behaviour |
| `manage.py` | Django management commands |

More detail on groups and permissions lives in [ROLES_AND_PERMISSIONS.md](ROLES_AND_PERMISSIONS.md).

## Common commands

```bash
python manage.py runserver
python manage.py migrate
python manage.py makemigrations
python manage.py createsuperuser
python manage.py collectstatic
```

## Deployment notes

The settings file includes commented options for HTTPS, secure cookies, and HSTS. Turn those on when you deploy behind TLS. Static files are collected to `staticfiles/` and served through WhiteNoise with `gunicorn` listed in requirements for production WSGI.

## License

Add your license here if this project is shared publicly.
