# API Documentation

## Health Check

### Endpoint

`GET /api/health`

### Description

Returns the current health status of the backend service and database connection.

### Success Response

**Status Code:** `200 OK`

```json
{
    "status": "healthy",
    "database": "connected"
}
```

---

# Authentication

## Register User

### Endpoint

`POST /api/auth/register`

### Description

Registers a new user account.

### Request Body

```json
{
    "name": "Dhanya",
    "email": "dhanya@example.com",
    "password": "Password123"
}
```

### Success Response

**Status Code:** `201 Created`

```json
{
    "message": "user registered successfully",
    "user": {
        "id": "6843xxxxxx",
        "name": "Dhanya",
        "email": "dhanya@example.com"
    }
}
```

### Error Responses

#### Missing Required Fields

**Status Code:** `400 Bad Request`

```json
{
    "error": "name, email and password are required"
}
```

#### Email Already Exists

**Status Code:** `409 Conflict`

```json
{
    "error": "email already exists"
}
```

---

## Login User

### Endpoint

`POST /api/auth/login`

### Description

Authenticates a user and returns a JWT access token.

### Request Body

```json
{
    "email": "dhanya@example.com",
    "password": "Password123"
}
```

### Success Response

**Status Code:** `200 OK`

```json
{
    "token": "eyJhbGciOiJIUzI1NiIs...",
    "user": {
        "id": "6843xxxxxx",
        "name": "Dhanya",
        "email": "dhanya@example.com"
    }
}
```

### Error Responses

#### Invalid Credentials

**Status Code:** `401 Unauthorized`

```json
{
    "error": "invalid email or password"
}
```

#### Missing Credentials

**Status Code:** `400 Bad Request`

```json
{
    "error": "email and password are required"
}
```

---

## JWT Authentication

Protected endpoints require an Authorization header.

### Header Format

```http
Authorization: Bearer <jwt_token>
```

### Example

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

Requests without a valid JWT token will receive:

**Status Code:** `401 Unauthorized`

```json
{
    "error": "authentication required"
}
```

---

# Search

Search endpoints require JWT authentication.

### Authorization Header

```http
Authorization: Bearer <jwt_token>
```

---

## Search Documents

### Endpoint

`GET /api/search`

### Description

Searches the entire processed document corpus using TF-IDF vectorization and cosine similarity.

Search is corpus-wide. It is not limited to documents uploaded by the authenticated user. Only documents with `processed = true` and non-empty extracted text are searchable.

The search ranking uses document title, extracted keywords, and extracted text. The response does not include `filepath` or full `text_content`.

### Authentication

Required

### Query Parameters

| Parameter | Type   | Required | Description                                 |
| --------- | ------ | -------- | ------------------------------------------- |
| q         | String | Yes      | Search query                                |
| limit     | Number | No       | Maximum number of results. Defaults to `5`. |

### Example Request

```http
GET /api/search?q=pump%20seal&limit=5
```

### Success Response

**Status Code:** `200 OK`

```json
{
  "query": "pump seal",
  "count": 1,
  "results": [
    {
      "id": "62a2f647502464b019871b61",
      "title": "Pump Maintenance Manual",
      "keywords": ["pump", "seal", "pressure"],
      "uploaded_by": "62948aec7e96386d3bd6885",
      "uploaded_by_name": "Dhanya",
      "uploaded_at": "2026-06-11T17:54:15.455Z",
      "score": 0.8123
    }
  ]
}
```

### Empty Results Response

**Status Code:** `200 OK`

```json
{
  "query": "compressor",
  "count": 0,
  "results": []
}
```

### Error Responses

#### Missing or Empty Query

**Status Code:** `400 Bad Request`

```json
{
  "error": "search query is required"
}
```

#### Invalid Limit

**Status Code:** `400 Bad Request`

```json
{
  "error": "limit must be a positive integer"
}
```

#### Unauthorized

**Status Code:** `401 Unauthorized`

```json
{
  "error": "authentication required"
}
```

#### Search Service Unavailable

**Status Code:** `500 Internal Server Error`

```json
{
  "error": "search service unavailable"
}
```

# Document Management

All document endpoints require JWT authentication.

### Authorization Header

```http
Authorization: Bearer <jwt_token>
```

---

## Upload Document

### Endpoint

`POST /api/documents/upload`

### Description

Uploads a document, processes it immediately, and stores the fully processed document in MongoDB.

### Authentication

Required

### Request Format

`multipart/form-data`

### Form Fields

| Field | Type   | Required | Description                |
| ----- | ------ | -------- | -------------------------- |
| file  | File   | Yes      | PDF, DOCX, or TXT document |
| title | String | No       | Custom document title      |
| tags  | String | No       | Comma-separated tags       |

### Example Request

```text
file: test.txt
title: Test Document
tags: test,sample
```

### Success Response

**Status Code:** `201 Created`

```json
{
  "message": "document uploaded successfully",
  "document": {
    "id": "62a2f647502464b019871b61",
    "title": "Test Document",
    "original_filename": "test.txt",
    "filename": "7f17d299be204729a11fb0bf33e0c9f1.txt",
    "file_size": 25,
    "content_type": "text/plain",
    "uploaded_by": "62948aec7e96386d3bd6885",
    "uploaded_at": "2026-06-11T17:54:15.455Z",
    "tags": [],
    "keywords": ["pressure", "pump", "maintenance"],
    "summary": "Pump maintenance requires pressure inspection.",
    "processed": true
  }
}
```

### Error Responses

#### Missing File

**Status Code:** `400 Bad Request`

```json
{
  "error": "file is required"
}
```

#### Unsupported File Type

**Status Code:** `400 Bad Request`

```json
{
  "error": "file type is not allowed"
}
```

#### No Extractable Text

**Status Code:** `400 Bad Request`

```json
{
  "error": "no extractable text found"
}
```

#### Unauthorized

**Status Code:** `401 Unauthorized`

```json
{
  "error": "authentication required"
}
```

---

## List Documents

### Endpoint

`GET /api/documents`

### Description

Returns all documents uploaded by the authenticated user.

### Authentication

Required

### Success Response

**Status Code:** `200 OK`

```json
{
  "documents": [
    {
      "id": "62a2f647502464b019871b61",
      "title": "Test Document",
      "original_filename": "test.txt",
      "file_size": 25,
      "content_type": "text/plain",
      "uploaded_at": "2026-06-11T17:54:15.455Z",
      "processed": true
    }
  ]
}
```

### Error Response

#### Unauthorized

**Status Code:** `401 Unauthorized`

```json
{
  "error": "authentication required"
}
```

---

## Get Document

### Endpoint

`GET /api/documents/<document_id>`

### Description

Returns metadata for a specific document owned by the authenticated user.

### Authentication

Required

### Success Response

**Status Code:** `200 OK`

```json
{
  "document": {
    "id": "62a2f647502464b019871b61",
    "title": "Test Document",
    "original_filename": "test.txt",
    "filename": "7f17d299be204729a11fb0bf33e0c9f1.txt",
    "file_size": 25,
    "content_type": "text/plain",
    "uploaded_at": "2026-06-11T17:54:15.455Z",
    "tags": [],
    "text_content": "Pump maintenance requires pressure inspection.",
    "keywords": ["pressure", "pump", "maintenance"],
    "summary": "Pump maintenance requires pressure inspection.",
    "processed": true
  }
}
```

### Error Response

#### Document Not Found

**Status Code:** `404 Not Found`

```json
{
  "error": "document not found"
}
```

---

## Get Document Summary

### Endpoint

`GET /api/documents/<document_id>/summary`

### Description

Returns the generated summary and keywords for any processed document in the corpus.

This endpoint is corpus-wide for authenticated users. It does not expose the full extracted text or file path.

### Authentication

Required

### Success Response

**Status Code:** `200 OK`

```json
{
  "id": "62a2f647502464b019871b61",
  "summary": "Pump maintenance requires pressure inspection.",
  "keywords": ["pressure", "pump", "maintenance"]
}
```

### Error Response

#### Document Not Found

**Status Code:** `404 Not Found`

```json
{
  "error": "document not found"
}
```

#### Unauthorized

**Status Code:** `401 Unauthorized`

```json
{
  "error": "authentication required"
}
```

---

## Delete Document

### Endpoint

`DELETE /api/documents/<document_id>`

### Description

Deletes a document and its associated uploaded file.

### Authentication

Required

### Success Response

**Status Code:** `200 OK`

```json
{
  "message": "document deleted successfully"
}
```

### Error Response

#### Document Not Found

**Status Code:** `404 Not Found`

```json
{
  "error": "document not found"
}
```

#### Unauthorized

**Status Code:** `401 Unauthorized`

```json
{
  "error": "authentication required"
}
```

