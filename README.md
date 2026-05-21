# LibraryApp Documentation

## Introduction

LibraryApp is a web-based library management system built with Django. It supports two sides of the workflow: member services and staff operations. Members can search and borrow books, while staff handle catalog updates, circulation, fines, and account management from a role-based admin panel.

## Project Objectives

The project was built to:

- provide a simple and clean member experience for borrowing and reservations
- support daily staff tasks in one system
- use Django groups and permissions as the access control foundation
- prevent permission escalation by limiting what non-superusers can grant

## Features

### Member features

- account registration and login
- browse books, authors, and categories
- borrow and return books
- reserve unavailable books
- view and pay fines
- manage profile and avatar

### Staff features

- role-based staff dashboard routing
- books, authors, and categories management
- loan and reservation management
- fines tracking and updates
- user account management (view, update, disable, delete where permitted)
- staff account creation through assignable groups
- group and permission management with ON/OFF permission toggles

## Technologies Used

- Python 3.11+
- Django 5.2
- PostgreSQL (configured through `DATABASE_URL`)
- Bootstrap 5 and Font Awesome
- Vanilla JavaScript for client-side interactions
- Pillow for image handling
- WhiteNoise for static file serving in deployment

## System Design / Architecture

The application follows a standard Django structure:

- `libraryapp/` contains global settings and URL configuration
- `library/` contains domain models, business logic, views, templates, and migrations
- template-based UI rendering is used instead of a separate frontend SPA

Access control is based on Django's built-in models:

- users belong to one or more `auth.Group`
- groups hold `auth.Permission` entries
- views and UI actions are guarded by permission checks

Staff users are routed to dashboards based on their effective permission area:

- librarian dashboard
- finance dashboard
- user manager dashboard
- full overview for superusers or broad access profiles

## Database Design

Key domain models include:

- `Account` (custom user model)
- `Author`, `Category`, `Book`
- `Borrow`
- `Reservation`
- `Fine`
- `ReadingSession`

Authentication and authorization use Django's built-in tables for:

- groups
- permissions
- user-group relations

## Implementation

Main implementation highlights:

- custom account model with email-based authentication
- role-aware helper layer in `library/roles.py`
- permission-gated staff views in `library/views.py`
- group management UI with permission toggles for create/update flows
- safeguards that block non-superusers from assigning protected or elevated access

## Authentication & Security

Security and access controls include:

- CSRF protection and secured session handling
- role-based authorization at both view and template levels
- restricted group assignment logic to prevent privilege escalation
- protected system groups and deletion safeguards
- superuser-only paths for unrestricted administrative operations

## Challenges and Solutions

### Challenge: static and overlapping role logic

The initial approach mixed custom role behavior with built-in Django permissions, which made access behavior harder to reason about.

**Solution:** refactor to Django-native groups and permissions as the single source of truth.

### Challenge: permission escalation risk for mid-level admins

User managers could potentially create or assign higher-privilege access.

**Solution:** enforce delegation constraints, filter assignable groups/permissions, and protect high-privilege groups from non-superusers.

### Challenge: role dashboard misrouting

Some staff users were landing on the wrong dashboard due to broad permission overlap.

**Solution:** update dashboard routing logic to handle superusers and mixed-permission users deterministically.

## Testing

Testing was performed through functional and authorization-focused checks:

- member flows: borrow, reserve, fines, profile updates
- staff flows: CRUD operations for books/users/groups
- permission checks: each role can access only intended screens and actions
- negative access checks: forbidden routes return expected permission errors

## Deployment

See **[DEPLOY.md](DEPLOY.md)** for step-by-step **Render** deployment (free tier):

- `render.yaml` — Blueprint (web + Postgres)
- `build.sh` — install, `collectstatic`, `migrate`
- `.env.example` — local environment template

## Future Improvements

- add automated test coverage for role and permission scenarios
- introduce audit logs for security-sensitive actions (group edits, account changes)
- improve dashboard analytics and operational reporting
- add API endpoints for future mobile or external integration
- persistent media storage for production (S3 / Cloudinary)

## Conclusion

LibraryApp delivers a complete library workflow with clear separation between member and staff responsibilities. By relying on Django's native permission system and strengthening delegation rules, the project remains practical for day-to-day use while keeping security and maintainability at the center.




