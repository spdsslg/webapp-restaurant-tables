# Restaurant reservations

A table reservation application for a single restaurant, built with Flask and PostgreSQL. The interface uses Jinja templates, HTML, CSS, and JavaScript for availability searches and reservation filtering. Docker Compose runs the application, database, and Mailpit email inbox.

Customers can register, book a table, filter their reservation history, cancel bookings, and update their profile or password. Managers maintain restaurant tables and manage customer reservations. Administrators also manage accounts and staff access.

Reservations use Europe/Warsaw time. The restaurant opens Monday–Friday from 09:00 to 22:00 and on weekends from 10:00 to 21:00. Bookings start at 30-minute intervals and last between 30 minutes and three hours. The server checks opening hours, table capacity, and overlapping reservations.

## Setup

Install Docker with Docker Compose and run the commands below from the project root.

### Configuration

Create a `.env` file:

```dotenv
FLASK_SECRET_KEY=your_generated_secret
FLASK_RESTAURANT_NAME=Restaurant
POSTGRES_PASSWORD=your_database_password
```

Generate a secret with the following command and use its output for `FLASK_SECRET_KEY`:

```sh
docker run --rm python:3.12-slim python -c "import secrets; print(secrets.token_hex(32))"
```

Choose a database password and keep `.env` out of Git. Keep the application secret unchanged between restarts to preserve login sessions.

### Start the application

```sh
docker compose up -d --build --wait
docker compose exec web flask --app app:create_app seed-demo
```

Startup applies database migrations automatically. The seed command adds opening hours, booking defaults, and eight sample tables. It is only needed for initial setup and does not create accounts.

Open http://localhost:8000 and register a customer account.

### Create an administrator

```sh
docker compose exec web flask --app app:create_app create-admin --email owner@example.com --name Owner
```

Replace the example name and email. The command prompts for a password and creates the first administrator. After signing in, use **Administration** to create accounts and assign manager access.

### Password-reset emails

Mailpit captures emails locally at http://localhost:8025; messages are not sent to real email addresses. To try password recovery, choose **Forgot your password?** on the login page, enter a registered email address, and open the reset link from Mailpit. Links expire after 30 minutes and can be used once.

## Development

Source files are mounted into the container, and Flask reloads after Python changes. Rebuild the image after changing dependencies or Docker configuration.

```sh
docker compose logs -f web       # View application logs
docker compose stop              # Stop services
docker compose up -d --wait       # Start services again
```

Database contents persist in a Docker volume. `docker compose down -v` deletes that volume. Changing the password in `.env` does not change an existing database's password.

To apply newly added migrations:

```sh
docker compose run --rm migrate
```

The current container runs Flask's development server, with published ports bound to localhost.

## Tests

With the application running, start the isolated PostgreSQL test database and run pytest:

```sh
docker compose --profile test up -d --wait db-test
docker compose exec -e TEST_DATABASE_URL=postgresql+psycopg://restaurant_test:test-only@db-test:5432/restaurant_test web python -m pytest
```

Tests clear their database between cases; the application's database is separate. Without `TEST_DATABASE_URL`, database integration tests are skipped.

Stop the test database when finished:

```sh
docker compose --profile test stop db-test
```
