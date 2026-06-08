# Changelog

All notable changes to this project will be documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

### Planned
- Document upload module
- Search APIs
- NLP pipeline (parsing, keywords, summarization)
- Frontend integration
- Automated tests and Docker deployment

## [0.2.0] - 2026-06-08

### Added
- JWT authentication module
  - `POST /api/auth/register` — user registration
  - `POST /api/auth/login` — login with JWT token response
- User model with registration validation (`models/user.py`)
- Auth service with password hashing and credential verification (`services/auth_service.py`)
- Auth routes blueprint (`routes/auth.py`)
- `token_required` middleware decorator for protecting future routes (`middleware/auth_middleware.py`)
- Flask-JWT-Extended integration in app factory
- JWT configuration (`JWT_SECRET_KEY`, `JWT_ACCESS_TOKEN_HOURS`) in config and `.env.example`
- Unique index on `users.email` in MongoDB

### Changed
- `requirements.txt` — added `Flask-JWT-Extended` and `PyJWT`

## [0.1.0] - 2026-06-04

### Added
- Initial repository setup
- Python virtual environment setup
- Flask backend initialization
- App Factory pattern (`create_app`)
- Blueprint-based routing structure
- Environment variable configuration via `.env`
- MongoDB connection with PyMongo (`database.py`)
- Health check endpoint (`GET /api/health`) with database connectivity status
- Project documentation started (`docs/setup.md`, `CHANGELOG.md`)
- `.env.example` template for required environment variables
