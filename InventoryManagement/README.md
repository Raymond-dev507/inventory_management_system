# Inventory Management System

A web-based inventory management system built with Django for managing
products, categories, suppliers, stock, sales, users, reports, and
inventory activity.

## Features

- User authentication
- User management
- Product management
- Category management
- Supplier management
- Stock-in management
- Stock-out management
- Sales management
- Automatic stock deduction
- Low-stock detection
- Negative stock control
- Inventory activity logging
- Global search
- Sales reports
- PDF report generation
- Best-selling products
- Slow-selling products
- Inventory insights
- Email functionality
- Telegram notifications
- Gemini AI integration

## Technologies

- Python
- Django
- MySQL
- HTML
- CSS
- JavaScript
- AdminLTE
- Bootstrap
- Gemini API
- Telegram Bot API
- SMTP Email (local)
- Brevo API (production)

## Requirements

Before installing the project, make sure you have:

- Python 3.x
- MySQL
- Git
- pip

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/Raymond-dev507/inventory_management_system
cd inventory_management_system
```

### 2. Create and activate a virtual environment

```bash
python -m venv venv
source venv/bin/activate   # On Windows: venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

Copy `.env.example` to `.env` and fill in your own values:

```bash
cp .env.example .env
```
AI

GEMINI_API_KEY=your-gemini-api-key

Telegram

TELEGRAM_BOT_TOKEN=your-telegram-bot-token
TELEGRAM_CHAT_ID=your-telegram-chat-id

Database

DATABASE_USER=your-database-user
DATABASE_PASSWORD=your-database-password
DATABASE_HOST=127.0.0.1
DATABASE_PORT=3306
DATABASE_NAME=your-database-name

Email (local development - SMTP)

EMAIL_ACCOUNT=your-email@gmail.com
EMAIL_PASSWORD=your-email-app-password

Email (production - Brevo API)

BREVO_API_KEY=your-brevo-api-key

Django

SECRET_KEY=your-django-secret-key
DEBUG=True
ALLOWED_HOSTS=127.0.0.1,localhost


### 5. Set up the MySQL database

Create a database in MySQL matching `DATABASE_NAME` in your `.env`.

### 6. Run migrations

```bash
python manage.py migrate
```

### 7. Create a superuser

```bash
python manage.py createsuperuser
```

### 8. Run the development server

```bash
python manage.py runserver
```

Visit `http://127.0.0.1:8000` in your browser.

## Deployment

This project is deployed on **Render** as a Django web service.

- Live demo: https://inventory-management-system-0scz.onrender.com
- Build command: `pip install -r requirements.txt && python manage.py collectstatic --noinput && python manage.py migrate`
- Start command: `gunicorn InventoryManagement.wsgi:application`

### Database Configuration

This project uses different databases depending on environment:

- **Local development**: MySQL
- **Production (Render)**: PostgreSQL — Render's managed Postgres add-on

Update the corresponding environment variables in Render (`DATABASE_URL` or your Postgres credentials) separately from your local MySQL `.env` values. See `settings.py` for how the database backend is switched based on environment.
### Environment Variables (Production)

Set these in Render → your service → **Environment**:

| Variable | Description |
|---|---|
| `SECRET_KEY` | Django secret key |
| `DEBUG` | Set to `False` in production |
| `ALLOWED_HOSTS` | Your Render domain (e.g. `your-app.onrender.com`) |
| `DATABASE_USER` / `DATABASE_PASSWORD` / `DATABASE_HOST` / `DATABASE_PORT` / `DATABASE_NAME` | MySQL connection details |
| `BREVO_API_KEY` | API key for transactional emails in production |
| `GEMINI_API_KEY` | Gemini AI integration |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | Telegram notifications |

### Email Configuration

Email sending differs between environments due to a platform restriction:

- **Local development**: uses standard SMTP (Gmail SMTP) via Django's built-in `send_mail()`.
- **Production (Render)**: Render blocks outbound SMTP ports, so production uses the **Brevo HTTP API** instead, which sends email over HTTPS and works around that restriction.

This switching is handled automatically in `inventory/utils.py` via `send_notification_email()`, based on whether the app is running on Render (`RENDER` environment variable) or locally.

## License

This project is licensed under the [MIT License](LICENSE).
