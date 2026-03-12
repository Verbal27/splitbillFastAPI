# SplitBill API

A RESTful API for managing shared expenses between groups of people. Built with **FastAPI**, **PostgreSQL**, and **SQLAlchemy (async)**.

---

## Features

- **Split Bills** — Create and manage shared bills with multiple members
- **Flexible Expense Splitting** — Split expenses equally, by percentage, or with custom amounts
- **Balance Tracking** — Automatic balance calculation between all members
- **Money Transactions** — Record direct payments between members
- **Guest Access** — Share a read-only view of a bill via a guest link (no account required)
- **User Accounts** — Register, activate via email, update profile, and delete account
- **Authentication** — JWT-based auth with access token expiry
- **Email Notifications** — Members are notified by email when added to a bill
- **Password Reset** — Token-based password reset via email
- **Comments** — Leave notes on a bill
- **Docker Support** — Full Docker + Docker Compose setup included

---

## Tech Stack

| Layer | Technology |
|---|---|
| Framework | FastAPI |
| Database | PostgreSQL 16 |
| ORM | SQLAlchemy 2.0 (async) |
| Migrations | Alembic |
| Auth | JWT via PyJWT + Passlib |
| Email | FastAPI-Mail |
| Runtime | Python 3.12+ |
| Package Manager | uv |
| Containerization | Docker + Docker Compose |

---

## Getting Started

### Prerequisites

- Python 3.12+
- PostgreSQL (or Docker)
- [uv](https://github.com/astral-sh/uv) (recommended) or pip

### 1. Clone the repository

```bash
git clone https://github.com/Verbal27/splitbillFastAPI.git
cd splitbillFastAPI
```

### 2. Set up environment variables

Create a `.env` file in the project root:

```env
# Database
DB_HOST=localhost
DB_PORT=5432
DB_USER=postgres
DB_PASS=your_password
DB_NAME=SplitBillFastApi

# Auth
SECRET_KEY=your_secret_key_here
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# Email (SMTP)
MAIL_USERNAME=your_email@example.com
MAIL_PASSWORD=your_email_password
MAIL_FROM=your_email@example.com
MAIL_PORT=587
MAIL_SERVER=smtp.example.com
MAIL_STARTTLS=true
MAIL_SSL_TLS=false
```

### 3. Install dependencies

```bash
uv sync
```

Or with pip:

```bash
pip install -r requirements.txt
```

### 4. Run database migrations

```bash
alembic upgrade head
```

### 5. Start the development server

```bash
python main.py
```

The API will be available at `http://localhost:8000`.  
Interactive docs: `http://localhost:8000/docs`

---

## Running with Docker

The easiest way to run the full stack (API + PostgreSQL) is with Docker Compose:

```bash
docker compose up --build
```

This starts:
- `splitbills_server` — the FastAPI app on port `8000`
- `splitbills_db` — PostgreSQL on port `5433`

The app will automatically wait for the database to be healthy before starting.

---

## API Overview

### Authentication

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/auth/token` | Login and receive a JWT access token |

### Users

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/users/register` | Register a new account |
| `GET` | `/users/activate?token=...` | Activate account via email token |
| `GET` | `/users/me` | Get current user profile |
| `PATCH` | `/users/me/update` | Update profile or password |
| `DELETE` | `/users/delete` | Delete account |
| `POST` | `/users/reset-password` | Request a password reset email |
| `POST` | `/users/reset-password-complete` | Complete password reset with token |

### Split Bills

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/splitbills/` | List all bills you own or are a member of |
| `POST` | `/splitbills/` | Create a new bill |
| `GET` | `/splitbills/{id}` | Get a specific bill |
| `PATCH` | `/splitbills/{id}/close-splitbill` | Close a settled bill |

### Members

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/splitbills/{id}/add-members` | Add a member to a bill |
| `DELETE` | `/splitbills/{id}/remove-member` | Remove a member |
| `PATCH` | `/splitbills/{id}/modify-member` | Update a member's details |

### Expenses

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/splitbills/{id}/expenses` | List all expenses |
| `POST` | `/splitbills/{id}/expenses` | Add an expense |
| `PATCH` | `/splitbills/{id}/expenses/{exp_id}` | Update an expense |
| `DELETE` | `/splitbills/{id}/expenses/{exp_id}` | Delete an expense |

### Transactions

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/splitbills/{id}/money-given` | Record a direct payment |
| `PATCH` | `/splitbills/{id}/money-given/{mg_id}` | Update a transaction |
| `DELETE` | `/splitbills/{id}/money-given/{mg_id}` | Delete a transaction |

### Comments

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/splitbills/{id}/comments` | Add a comment to a bill |

### Guest Access

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/guest-access/{token}` | View a bill as a guest (no auth required) |

---

## Expense Splitting Modes

When creating or updating an expense, choose one of three split types:

- **`equal`** — The total is divided equally among all (or selected) members.
- **`percentage`** — Provide a percentage for each member; must total 100%.
- **`custom`** — Provide an exact amount per member; must sum to the total expense amount.

---

## Project Structure

```
splitbillFastAPI/
├── main.py                  # App entry point, router registration
├── api/
│   ├── core/
│   │   ├── auth.py          # JWT logic, password hashing
│   │   ├── config.py        # Settings loaded from .env
│   │   └── utils.py         # Balance calculation, email helpers, guest links
│   ├── db/
│   │   └── database.py      # Async SQLAlchemy session and base
│   ├── models/
│   │   └── models.py        # ORM models (Users, SplitBills, Expenses, etc.)
│   ├── routers/
│   │   ├── auth.py          # /auth routes
│   │   ├── users.py         # /users routes
│   │   ├── splitbills.py    # /splitbills routes
│   │   └── guest.py         # /guest-access routes
│   └── schemas/
│       ├── users_schema.py  # Pydantic schemas for users
│       └── splitbill_schema.py  # Pydantic schemas for bills, expenses, etc.
├── alembic/                 # Database migration scripts
├── Dockerfile
├── compose.yaml
└── pyproject.toml
```

---

## Contributing

Contributions are welcome! Here's how to get started:

1. **Fork** the repository and create a feature branch:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes** and ensure code quality with the pre-commit hooks:
   ```bash
   pre-commit install
   pre-commit run --all-files
   ```

3. **Write or update tests** if applicable.

4. **Commit** with a clear message:
   ```bash
   git commit -m "feat: add your feature description"
   ```

5. **Open a pull request** against the `master` branch with a description of your changes.

### Code Style

This project uses [Ruff](https://github.com/astral-sh/ruff) for linting. Run it before submitting:

```bash
ruff check .
```

---

## License

This project is open source. See [LICENSE](LICENSE) for details.
