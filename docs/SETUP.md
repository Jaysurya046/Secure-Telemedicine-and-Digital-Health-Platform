# Setup Guide

This guide will help you set up the Secure Telemedicine Platform for development and production environments.

## Prerequisites

### Required Software

- **Python 3.11+**: Backend development
- **Node.js 20+**: Real-time service and frontend
- **PostgreSQL 15+**: Primary database
- **Redis 7+**: Caching and pub/sub
- **Docker & Docker Compose**: Containerization (recommended)

### Optional Tools

- **Git**: Version control
- **VS Code**: Recommended IDE
- **Postman/Insomnia**: API testing
- **pgAdmin**: PostgreSQL management

## Quick Start with Docker (Recommended)

### 1. Clone and Setup

```bash
# Clone the repository
git clone <repository-url>
cd telemedicine-platform

# Copy environment variables
cp .env.example .env

# Edit environment variables
nano .env  # or use your preferred editor
```

### 2. Configure Environment Variables

Edit `.env` file with your configuration:

```bash
# Django Settings
DJANGO_SECRET_KEY=your-secret-key-here-change-in-production
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1

# Database
POSTGRES_DB=telemedicine_db
POSTGRES_USER=telemedicine_user
POSTGRES_PASSWORD=secure_password_here
POSTGRES_HOST=db
POSTGRES_PORT=5432

# Redis
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_PASSWORD=redis_password_here

# JWT Settings
JWT_SECRET_KEY=jwt-secret-key-change-in-production
JWT_ACCESS_TOKEN_LIFETIME=15  # minutes
JWT_REFRESH_TOKEN_LIFETIME=10080  # 7 days in minutes

# Email Configuration
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-app-password

# Node.js Real-time Service
NODE_ENV=development
RT_SERVICE_PORT=3002
RT_SERVICE_SECRET=realtime-secret-key

# Frontend URLs
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_WS_URL=ws://localhost:3002
REACT_APP_API_URL=http://localhost:8000
REACT_APP_WS_URL=ws://localhost:3002

# File Storage
MEDIA_ROOT=/app/media
MAX_UPLOAD_SIZE=10485760  # 10MB in bytes

# CORS
CORS_ALLOWED_ORIGINS=http://localhost:3000,http://localhost:3001
```

### 3. Start Services

```bash
# Build and start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Check service status
docker-compose ps
```

### 4. Initialize Database

```bash
# Run migrations
docker-compose exec backend python manage.py migrate

# Create superuser
docker-compose exec backend python manage.py createsuperuser

# Load sample data (optional)
docker-compose exec backend python manage.py loaddata sample_data.json
```

### 5. Access Applications

- **Patient Portal**: http://localhost:3000
- **Doctor Dashboard**: http://localhost:3001
- **Django Admin**: http://localhost:8000/admin
- **API Documentation**: http://localhost:8000/api/docs
- **Real-time Service**: ws://localhost:3002

## Manual Setup

### 1. Database Setup

#### Install PostgreSQL

**Ubuntu/Debian**:
```bash
sudo apt update
sudo apt install postgresql postgresql-contrib
sudo systemctl start postgresql
sudo systemctl enable postgresql
```

**macOS**:
```bash
brew install postgresql@15
brew services start postgresql@15
```

**Windows**:
Download and install from https://www.postgresql.org/download/windows/

#### Create Database

```bash
# Connect to PostgreSQL
sudo -u postgres psql

# Create database and user
CREATE DATABASE telemedicine_db;
CREATE USER telemedicine_user WITH PASSWORD 'secure_password_here';
ALTER ROLE telemedicine_user SET client_encoding TO 'utf8';
ALTER ROLE telemedicine_user SET default_transaction_isolation TO 'read committed';
ALTER ROLE telemedicine_user SET timezone TO 'UTC';
GRANT ALL PRIVILEGES ON DATABASE telemedicine_db TO telemedicine_user;

# Exit
\q
```

### 2. Redis Setup

#### Install Redis

**Ubuntu/Debian**:
```bash
sudo apt update
sudo apt install redis-server
sudo systemctl start redis-server
sudo systemctl enable redis-server
```

**macOS**:
```bash
brew install redis
brew services start redis
```

**Windows**:
Download from https://github.com/microsoftarchive/redis/releases

#### Configure Redis

Edit `/etc/redis/redis.conf`:
```bash
# Set password
requirepass redis_password_here

# Bind to localhost
bind 127.0.0.1

# Enable persistence
save 900 1
save 300 10
save 60 10000
```

Restart Redis:
```bash
sudo systemctl restart redis-server
```

### 3. Backend Setup (Django)

```bash
# Navigate to backend directory
cd backend

# Create virtual environment
python -m venv venv

# Activate virtual environment
# On Linux/macOS:
source venv/bin/activate
# On Windows:
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy environment file
cp .env.example .env

# Edit .env with your configuration
nano .env

# Run migrations
python manage.py migrate

# Create superuser
python manage.py createsuperuser

# Collect static files
python manage.py collectstatic --noinput

# Run development server
python manage.py runserver
```

### 4. Real-time Service Setup (Node.js)

```bash
# Navigate to real-time service directory
cd realtime-service

# Install dependencies
npm install

# Copy environment file
cp .env.example .env

# Edit .env with your configuration
nano .env

# Run development server
npm run dev
```

### 5. Patient Portal Setup (Next.js)

```bash
# Navigate to patient portal directory
cd patient-portal

# Install dependencies
npm install

# Copy environment file
cp .env.local.example .env.local

# Edit .env.local with your configuration
nano .env.local

# Run development server
npm run dev
```

### 6. Doctor Dashboard Setup (React)

```bash
# Navigate to doctor dashboard directory
cd doctor-dashboard

# Install dependencies
npm install

# Copy environment file
cp .env.example .env

# Edit .env with your configuration
nano .env

# Run development server
npm run dev
```

## Development Workflow

### Running All Services

**With Docker**:
```bash
docker-compose up -d
```

**Manual**:

Terminal 1 - Django Backend:
```bash
cd backend
source venv/bin/activate
python manage.py runserver
```

Terminal 2 - Real-time Service:
```bash
cd realtime-service
npm run dev
```

Terminal 3 - Patient Portal:
```bash
cd patient-portal
npm run dev
```

Terminal 4 - Doctor Dashboard:
```bash
cd doctor-dashboard
npm run dev
```

Terminal 5 - Celery Worker (for async tasks):
```bash
cd backend
source venv/bin/activate
celery -A config worker -l info
```

Terminal 6 - Celery Beat (for scheduled tasks):
```bash
cd backend
source venv/bin/activate
celery -A config beat -l info
```

### Database Migrations

```bash
# Create new migration
python manage.py makemigrations

# Apply migrations
python manage.py migrate

# Show migrations
python manage.py showmigrations

# Rollback migration
python manage.py migrate app_name migration_name
```

### Creating Sample Data

```bash
# Create sample users and data
python manage.py create_sample_data

# Or use Django shell
python manage.py shell
```

## Testing

### Backend Tests

```bash
cd backend
source venv/bin/activate

# Run all tests
python manage.py test

# Run specific app tests
python manage.py test apps.users

# Run with coverage
coverage run --source='.' manage.py test
coverage report
coverage html  # Generate HTML report
```

### Real-time Service Tests

```bash
cd realtime-service

# Run tests
npm test

# Run with coverage
npm run test:coverage

# Run in watch mode
npm run test:watch
```

### Frontend Tests

```bash
# Patient Portal
cd patient-portal
npm test

# Doctor Dashboard
cd doctor-dashboard
npm test
```

### End-to-End Tests

```bash
# Install Playwright
npm install -D @playwright/test

# Run E2E tests
npm run test:e2e
```

## Production Deployment

### 1. Pre-deployment Checklist

- [ ] Set `DJANGO_DEBUG=False`
- [ ] Configure proper `ALLOWED_HOSTS`
- [ ] Use strong `SECRET_KEY` and `JWT_SECRET_KEY`
- [ ] Set up SSL/TLS certificates
- [ ] Configure production database with backups
- [ ] Set up Redis with persistence
- [ ] Configure email service (SendGrid/AWS SES)
- [ ] Set up file storage (AWS S3/similar)
- [ ] Configure monitoring (Sentry/New Relic)
- [ ] Set up logging aggregation
- [ ] Configure CDN for static files
- [ ] Enable rate limiting
- [ ] Set up health checks
- [ ] Configure backup strategy
- [ ] Review security settings
- [ ] Update CORS settings

### 2. Environment Variables for Production

```bash
# Django
DJANGO_DEBUG=False
DJANGO_SECRET_KEY=<strong-random-key>
DJANGO_ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com
DJANGO_SECURE_SSL_REDIRECT=True
DJANGO_SECURE_HSTS_SECONDS=31536000

# Database (use managed service)
POSTGRES_HOST=your-db-host.rds.amazonaws.com
POSTGRES_PORT=5432
POSTGRES_DB=telemedicine_prod
POSTGRES_USER=telemedicine_prod_user
POSTGRES_PASSWORD=<strong-password>

# Redis (use managed service)
REDIS_HOST=your-redis-host.cache.amazonaws.com
REDIS_PORT=6379
REDIS_PASSWORD=<strong-password>

# File Storage
AWS_ACCESS_KEY_ID=<your-key>
AWS_SECRET_ACCESS_KEY=<your-secret>
AWS_STORAGE_BUCKET_NAME=telemedicine-media
AWS_S3_REGION_NAME=us-east-1

# Email
EMAIL_HOST=smtp.sendgrid.net
EMAIL_PORT=587
EMAIL_HOST_USER=apikey
EMAIL_HOST_PASSWORD=<sendgrid-api-key>

# Monitoring
SENTRY_DSN=<your-sentry-dsn>

# CORS
CORS_ALLOWED_ORIGINS=https://yourdomain.com,https://www.yourdomain.com
```

### 3. Docker Production Build

```bash
# Build production images
docker-compose -f docker-compose.prod.yml build

# Push to registry
docker-compose -f docker-compose.prod.yml push

# Deploy
docker-compose -f docker-compose.prod.yml up -d
```

### 4. Nginx Configuration

```nginx
# /etc/nginx/sites-available/telemedicine

upstream django_backend {
    server 127.0.0.1:8000;
}

upstream realtime_service {
    server 127.0.0.1:3002;
}

upstream patient_portal {
    server 127.0.0.1:3000;
}

upstream doctor_dashboard {
    server 127.0.0.1:3001;
}

# Redirect HTTP to HTTPS
server {
    listen 80;
    server_name yourdomain.com www.yourdomain.com;
    return 301 https://$server_name$request_uri;
}

# Patient Portal
server {
    listen 443 ssl http2;
    server_name yourdomain.com www.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;
    
    # SSL Configuration
    ssl_protocols TLSv1.3 TLSv1.2;
    ssl_ciphers 'ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256';
    ssl_prefer_server_ciphers off;
    
    # Security Headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options "DENY" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;

    location / {
        proxy_pass http://patient_portal;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }
}

# Doctor Dashboard
server {
    listen 443 ssl http2;
    server_name doctors.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;

    location / {
        proxy_pass http://doctor_dashboard;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }
}

# API Backend
server {
    listen 443 ssl http2;
    server_name api.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;

    client_max_body_size 10M;

    location / {
        proxy_pass http://django_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /static/ {
        alias /var/www/telemedicine/static/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }
}

# WebSocket Server
server {
    listen 443 ssl http2;
    server_name ws.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;

    location / {
        proxy_pass http://realtime_service;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 86400;
    }
}
```

### 5. SSL Certificate Setup

```bash
# Install Certbot
sudo apt install certbot python3-certbot-nginx

# Obtain certificate
sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com -d api.yourdomain.com -d ws.yourdomain.com -d doctors.yourdomain.com

# Auto-renewal (cron job)
sudo crontab -e
# Add: 0 0 * * * certbot renew --quiet
```

### 6. Systemd Service Files

**Django Backend** (`/etc/systemd/system/telemedicine-backend.service`):
```ini
[Unit]
Description=Telemedicine Django Backend
After=network.target postgresql.service redis.service

[Service]
User=www-data
Group=www-data
WorkingDirectory=/var/www/telemedicine/backend
Environment="PATH=/var/www/telemedicine/backend/venv/bin"
ExecStart=/var/www/telemedicine/backend/venv/bin/gunicorn \
    --workers 4 \
    --bind 127.0.0.1:8000 \
    --timeout 120 \
    --access-logfile /var/log/telemedicine/access.log \
    --error-logfile /var/log/telemedicine/error.log \
    config.wsgi:application

[Install]
WantedBy=multi-user.target
```

**Real-time Service** (`/etc/systemd/system/telemedicine-realtime.service`):
```ini
[Unit]
Description=Telemedicine Real-time Service
After=network.target redis.service

[Service]
User=www-data
Group=www-data
WorkingDirectory=/var/www/telemedicine/realtime-service
Environment="NODE_ENV=production"
ExecStart=/usr/bin/node src/server.js

[Install]
WantedBy=multi-user.target
```

Enable and start services:
```bash
sudo systemctl enable telemedicine-backend
sudo systemctl enable telemedicine-realtime
sudo systemctl start telemedicine-backend
sudo systemctl start telemedicine-realtime
```

## Monitoring and Maintenance

### Health Checks

```bash
# Backend health
curl https://api.yourdomain.com/health/

# Real-time service health
curl https://ws.yourdomain.com/health/

# Database connection
curl https://api.yourdomain.com/health/db/

# Redis connection
curl https://api.yourdomain.com/health/redis/
```

### Log Locations

- **Django**: `/var/log/telemedicine/django.log`
- **Nginx**: `/var/log/nginx/access.log` and `/var/log/nginx/error.log`
- **PostgreSQL**: `/var/log/postgresql/postgresql-15-main.log`
- **Redis**: `/var/log/redis/redis-server.log`

### Backup Strategy

```bash
# Database backup script
#!/bin/bash
BACKUP_DIR="/backups/postgres"
DATE=$(date +%Y%m%d_%H%M%S)
pg_dump -U telemedicine_user telemedicine_db | gzip > $BACKUP_DIR/backup_$DATE.sql.gz

# Keep only last 30 days
find $BACKUP_DIR -name "backup_*.sql.gz" -mtime +30 -delete
```

Add to cron:
```bash
0 2 * * * /usr/local/bin/backup-database.sh
```

## Troubleshooting

### Common Issues

**Database connection error**:
```bash
# Check PostgreSQL is running
sudo systemctl status postgresql

# Check connection
psql -U telemedicine_user -d telemedicine_db -h localhost
```

**Redis connection error**:
```bash
# Check Redis is running
sudo systemctl status redis-server

# Test connection
redis-cli -a redis_password_here ping
```

**Port already in use**:
```bash
# Find process using port
lsof -i :8000

# Kill process
kill -9 <PID>
```

**Migration errors**:
```bash
# Reset migrations (development only!)
python manage.py migrate --fake app_name zero
python manage.py migrate app_name
```

## Support

For issues and questions:
- **Documentation**: https://docs.yourdomain.com
- **GitHub Issues**: https://github.com/yourorg/telemedicine-platform/issues
- **Email**: support@yourdomain.com
- **Slack**: https://yourorg.slack.com

---

**Remember**: Always test in a staging environment before deploying to production!
