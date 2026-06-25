# Changelog

All notable changes to this project will be documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

### Planned
- Frontend integration
- Docker deployment

## [0.7.0] - 2026-06-25

### Added
- `POST /api/ask` endpoint for question answering over the document corpus
- Chunk-based document retrieval using stored document chunks
- Two-stage TF-IDF retrieval pipeline:
  - Chunk ranking using cosine similarity
  - Sentence-level ranking within the top retrieved chunks
- Confidence score and source metadata (document and chunk ID) returned with answers
- Comprehensive Q&A integration tests covering authentication, question validation, corpus-wide retrieval, processed-document filtering, and answer extraction

### Changed
- Documents now store precomputed chunks during upload to avoid regenerating chunks during search and Q&A
- Refactored text preprocessing to preserve original document wording in stored `text_content` and chunks while keeping NLP normalization internal
- Search and Q&A now reuse the common retrieval pipeline for chunk ranking


## [0.5.1] - 2026-06-17

### Added
- GET /api/documents/<id>/summary endpoint
- Summary and keyword retrieval API
- Summary endpoint integration tests
- API documentation updates

## [0.5.0] - 2026-06-17

### Added

#### Automated Document Processing

* Integrated NLP pipeline into document upload workflow
* Automatic text extraction during upload
* Automatic keyword generation during upload
* Automatic summary generation during upload

### Changed

#### Document Upload

* Documents are now processed immediately after upload
* Upload requests now trigger:

  * Document parsing
  * Text preprocessing
  * TF-IDF keyword extraction
  * Extractive summarization
* Successfully processed documents are stored with:

  * `text_content`
  * `keywords`
  * `summary`
  * `processed = true`

#### Database Storage

* MongoDB now stores processed document content instead of placeholder NLP fields
* Processed metadata is generated before document insertion

### Improved

* Added cleanup of uploaded files when NLP processing fails
* Prevented insertion of partially processed documents
* Improved validation for empty and non-processable documents
* Improved upload reliability through end-to-end processing checks

### Testing

* Updated document upload integration tests
* Added validation for processed document uploads
* Added validation for cleaned text persistence
* Added validation for empty document rejection
* Added validation for upload cleanup after processing failures

### Verification

* Verified end-to-end upload workflow using Postman
* Verified processed document storage using MongoDB Compass
* Verified automatic population of summaries and keywords after upload


## [0.4.0] - 2026-06-16

### Added

- Document parser service
  - TXT extraction
  - PDF extraction
  - DOCX extraction

- Text preprocessing service
  - whitespace normalization
  - tokenization

- TF-IDF keyword extraction service

- Extractive summarization service

### Testing

- Added NLP test suite
- Parser tests
- Preprocessor tests
- Keyword extraction tests
- Summarization tests

## [0.3.0] - 2026-06-11

### Added
- Document upload module
- Document listing endpoint
- Document retrieval endpoint
- Document deletion endpoint
- Document ownership enforcement
- File storage in uploads/
- Document metadata persistence in MongoDB
- Document integration tests

### Added Schema Fields
- original_filename
- filepath
- processed

### Security
- User-scoped document access
- User-scoped document deletion

### Testing
- Upload endpoint tests
- Document retrieval tests
- Document deletion tests
- Ownership verification tests

## [0.2.1] - 2026-06-08

### Added
- Auth integration tests (`tests/test_auth.py`) — 9 tests for registration, login, and JWT protection
- Shared test fixtures (`tests/conftest.py`) with isolated `knowledge_db_test` database
- `pytest` test runner and `pytest.ini` for import path configuration

### Changed
- `config.py` — added `MONGO_DB_NAME` environment variable (default: `knowledge_db`)
- `database.py` — database name now read from config instead of hardcoded
- `requirements.txt` — added `pytest` and dependencies
- `.env.example` — documented `MONGO_DB_NAME`

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
