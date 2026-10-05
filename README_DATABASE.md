# Database Setup Guide

## Option 1: Docker (Recommended)

1. **Install Docker** if not already installed
2. **Start PostgreSQL container:**
   ```bash
   docker-compose up -d
   ```
3. **Verify connection:**
   ```bash
   docker-compose exec postgres psql -U user -d rori_db -c "SELECT version();"
   ```

## Option 2: Install PostgreSQL Locally

1. **Install PostgreSQL:**
   ```bash
   winget install PostgreSQL.PostgreSQL.15
   ```

2. **Create database and user:**
   ```sql
   -- Connect to PostgreSQL as superuser
   psql -U postgres
   
   -- Create database
   CREATE DATABASE rori_db;
   
   -- Create user
   CREATE USER user WITH PASSWORD 'password';
   
   -- Grant privileges
   GRANT ALL PRIVILEGES ON DATABASE rori_db TO user;
   ```

3. **Update DATABASE_URL** in `app/models/models.py` if you used different credentials

## Testing the Setup

1. **Run the test script:**
   ```bash
   .venv\Scripts\activate
   python scripts/test_run.py
   ```

2. **Run the simulation:**
   ```bash
   python scripts/simulate_restaurants.py
   ```

## Docker Commands

- **Start:** `docker-compose up -d`
- **Stop:** `docker-compose down`
- **View logs:** `docker-compose logs postgres`
- **Connect to database:** `docker-compose exec postgres psql -U user -d rori_db`

## Database Schema

The application creates these tables automatically:
- `sales` - Daily sales data
- `inventory` - Current inventory levels
- `labor` - Daily labor costs
