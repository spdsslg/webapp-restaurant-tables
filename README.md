# Restaurant reservations

A web application for reserving tables at one restaurant. Customers find a suitable table, book a visit, and manage their reservations. Managers handle restaurant tables and customer bookings; administrators manage accounts and staff access.

The application uses **Flask**, **PostgreSQL**, **Flask-SQLAlchemy**, and **Alembic** migrations. Pages are rendered with **Jinja**, HTML, and CSS, with small JavaScript `fetch()` requests for availability and reservation filters. Docker Compose runs the application, database, and Mailpit email inbox together.

## Features

- Customer registration, login/logout, profile editing, password changes, and emailed password-reset links
- Availability table filtered by date, start time, duration, and party size
- Personal reservation history filtered by date range and status
- Cancellation without a cutoff, preserving reservation history
- Manager/administrator table creation, renaming, and activation/deactivation; capacities are fixed after creation
- Manager/administrator overview of all customer reservations, with filters and cancellation
- Administrator account creation, role assignment, and activation/deactivation, with protection for the last active administrator
- Server-side validation, role/ownership checks, CSRF protection, and database protection against overlapping reservations
- Responsive interface for desktop and phone screens

Bookings use **Europe/Warsaw** local time, including daylight saving. Initial opening hours are Monday–Friday **09:00–22:00** and Saturday–Sunday **10:00–21:00**. Start times are spaced 30 minutes apart; durations range from 30 minutes to three hours in 30-minute increments. The entire reservation must fit within opening hours. These booking rules have no settings screen in the current version.

## Requirements

- Docker with the Docker Compose plugin, such as Docker Desktop
- The complete project source folder
- An internet connection for the first image build/download
- Available local ports: `8000`, `8025`, `1025`, and `54320`

No separate Python or PostgreSQL installation is required when using Docker. Run the following commands from the project root, where `compose.yaml` is located.

## First-time setup

### 1. Create a local environment file

Generate a random application secret:

```sh
docker run --rm python:3.12-slim python -c "import secrets; print(secrets.token_hex(32))"
```

Create a file named `.env` in the project root:

```dotenv
FLASK_SECRET_KEY=replace_with_the_generated_value
FLASK_RESTAURANT_NAME=Restaurant
POSTGRES_PASSWORD=choose_a_local_database_password
```

Replace both placeholder values. Keep the secret private and stable between restarts; changing it invalidates signed login sessions. The `.env` file is excluded from Git and Docker build contents. On another computer, create a separate local `.env` rather than publishing your credentials.

### 2. Build and start the services

Start Docker, then run:

```sh
docker compose up -d --build --wait
```

Compose starts PostgreSQL, waits for it to become healthy, applies database migrations through the `migrate` service, and starts Flask. Mailpit starts alongside them. The migration container finishing successfully is expected.

### 3. Add initial restaurant data

```sh
docker compose exec web flask --app app:create_app seed-demo
```

This adds missing restaurant settings, opening hours, and eight sample tables, T1–T8, with capacities **2, 2, 2, 2, 4, 4, 6, 6**. It does not create user accounts. Run it for the initial demonstration setup; it is not required at every startup.

### 4. Create the first administrator

```sh
docker compose exec web flask --app app:create_app create-admin --email owner@example.com --name Owner
```

Replace the example email/name with your own. Enter a password of 8–128 characters when prompted, then confirm it. The password is not displayed or included in the command. This command creates the first administrator only; additional accounts and manager access can be managed through **Administration** after signing in.

### 5. Open the application

- Application: http://localhost:8000
- Mailpit inbox: http://localhost:8025

Register a customer account through the application, or sign in with the administrator created above. Public registration always creates a customer account.

## Password-reset email demonstration

Mailpit is a local inbox for testing email. It requires no real email-provider account and does not deliver messages to external recipients.

1. Choose **Forgot password?** on the login screen, or open http://localhost:8000/account/forgot-password
2. Submit the email address of an existing active account
3. Open http://localhost:8025 and open the password-reset message
4. Follow its link, choose a new password, and sign in again

Reset links expire after 30 minutes by default and can be used successfully only once. Registration email verification is not required. Mailpit is intended for the private local demonstration; real email delivery must be configured separately for public deployment.

## Everyday commands

Start again after stopping:

```sh
docker compose up -d --wait
```

View application logs:

```sh
docker compose logs -f web
```

Stop the services:

```sh
docker compose stop
```

PostgreSQL data persists in the `postgres_data` Docker volume. Ordinary stops and restarts preserve accounts and bookings. **`docker compose down -v` deletes the database volume**, so do not use it unless you intend to remove that data. Changing `POSTGRES_PASSWORD` in `.env` does not update the password of an already initialized database.

Application source, templates, styles, tests, and migrations are mounted from the project folder. Ordinary source edits do not require an image rebuild; dependency or Docker configuration changes do. After adding migrations, apply them with:

```sh
docker compose run --rm migrate
```

## Tests

With the application running, start the separate disposable test database and run the full suite:

```sh
docker compose --profile test up -d --wait db-test
docker compose exec -e TEST_DATABASE_URL=postgresql+psycopg://restaurant_test:test-only@db-test:5432/restaurant_test web python -m pytest
```

The test database is separate from the application's persistent database and is cleared by the test fixtures. Do not point the tests at data you want to keep. Running pytest without `TEST_DATABASE_URL` skips database integration tests.

The latest verified suite has **62 passing cases** and **89.04% Python statement coverage across `app/`**, exceeding the configured 70% minimum. This metric does not measure templates, CSS, JavaScript, or migrations. Stop the test database when finished:

```sh
docker compose --profile test stop db-test
```

## Project structure

| Path | Purpose |
| --- | --- |
| `app/__init__.py` | Application factory, configuration, and blueprint registration |
| `app/models.py` | Users, tables, opening hours, settings, and reservations |
| `app/auth.py`, `app/profile.py`, `app/admin.py` | Authentication, profile/password flows, and account administration |
| `app/bookings.py`, `app/booking_rules.py` | Availability, booking creation, and booking validation |
| `app/reservations.py`, `app/staff_reservations.py` | Customer and staff reservation history/cancellation |
| `app/tables.py` | Staff table management |
| `app/templates/`, `app/static/` | Jinja templates, CSS, and JavaScript |
| `migrations/` | Versioned database schema changes |
| `tests/` | Automated application and PostgreSQL integration tests |
| `compose.yaml`, `Dockerfile` | Container setup and service coordination |

## Running on another computer

Use the same source files and setup steps above. Docker Compose creates a new database volume on that computer; existing accounts and reservations are not copied automatically. Run the initial seed and first-administrator commands for a fresh demonstration database.

The current configuration uses Flask's development server and binds published ports to `127.0.0.1`, so open the application in a browser on the computer running Docker. This is a local demonstration setup. Public hosting requires deployment configuration such as a production server, HTTPS, and real email delivery.

If startup fails, inspect the relevant services:

```sh
docker compose ps -a
docker compose logs web migrate db
```

Check that Docker is running, `.env` contains a secret key, and the listed ports are free.
