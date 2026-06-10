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

