# Rori Authentication API Documentation

This document provides comprehensive information about the Supabase-based authentication system for the Rori restaurant analytics platform.

## Overview

The authentication system provides:
- User registration with restaurant creation
- JWT-based authentication
- Email verification
- Password reset functionality
- Multi-tenant restaurant isolation

## Environment Variables

Set these environment variables in your FastAPI application:

```bash
# JWT Configuration
JWT_SECRET_KEY=your-super-secret-jwt-key-change-in-production

# Supabase Configuration
SUPABASE_URL=https://your-project-id.supabase.co
SUPABASE_KEY=your-supabase-anon-key
```

## Database Setup

1. **Create Supabase Project**: Set up a new project at [supabase.com](https://supabase.com)

2. **Run Schema SQL**: Execute the SQL in `docs/supabase_schema.sql` in your Supabase SQL Editor

3. **Enable Auth**: Configure Supabase Auth settings as needed

## API Endpoints

### 1. User Registration

**Endpoint**: `POST /auth/signup`

**Description**: Register a new user and create their restaurant

**Request Body**:
```json
{
    "email": "user@example.com",
    "password": "securePassword123",
    "restaurant_name": "My Restaurant"
}
```

**Success Response** (200):
```json
{
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "token_type": "bearer",
    "user_id": "550e8400-e29b-41d4-a716-446655440000",
    "restaurant_id": 1
}
```

**Error Responses**:
- **400**: Email already registered
- **500**: Registration failed

**Example Request**:
```bash
curl -X POST http://127.0.0.1:8000/auth/signup \
  -H "Content-Type: application/json" \
  -d '{
    "email": "john@restaurant.com",
    "password": "securePassword123",
    "restaurant_name": "John\\'s Diner"
  }'
```

### 2. User Login

**Endpoint**: `POST /auth/login`

**Description**: Authenticate user and return JWT token

**Request Body**:
```json
{
    "email": "user@example.com",
    "password": "securePassword123"
}
```

**Success Response** (200):
```json
{
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "token_type": "bearer",
    "user_id": "550e8400-e29b-41d4-a716-446655440000",
    "restaurant_id": 1
}
```

**Error Responses**:
- **401**: Invalid email or password
- **401**: Account is disabled
- **401**: Email not verified
- **500**: Authentication failed

**Example Request**:
```bash
curl -X POST http://127.0.0.1:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "john@restaurant.com",
    "password": "securePassword123"
  }'
```

### 3. Email Verification Request

**Endpoint**: `POST /auth/verify-email`

**Description**: Resend verification email

**Request Body**:
```json
{
    "email": "user@example.com"
}
```

**Success Response** (200):
```json
{
    "message": "Verification email sent successfully"
}
```

**Example Request**:
```bash
curl -X POST http://127.0.0.1:8000/auth/verify-email \
  -H "Content-Type: application/json" \
  -d '{
    "email": "john@restaurant.com"
  }'
```

### 4. Password Reset Request

**Endpoint**: `POST /auth/reset-password`

**Description**: Request password reset email

**Request Body**:
```json
{
    "email": "user@example.com"
}
```

**Success Response** (200):
```json
{
    "message": "Password reset email sent successfully"
}
```

**Example Request**:
```bash
curl -X POST http://127.0.0.1:8000/auth/reset-password \
  -H "Content-Type: application/json" \
  -d '{
    "email": "john@restaurant.com"
  }'
```

### 5. Get Current User Info

**Endpoint**: `GET /auth/me`

**Description**: Get current authenticated user information

**Headers**:
```
Authorization: Bearer <jwt_token>
```

**Success Response** (200):
```json
{
    "user_id": "550e8400-e29b-41d4-a716-446655440000",
    "restaurant_id": 1,
    "authenticated": true
}
```

**Example Request**:
```bash
curl -X GET http://127.0.0.1:8000/auth/me \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
```

### 6. Logout

**Endpoint**: `POST /auth/logout`

**Description**: Logout user (client-side token removal)

**Headers**:
```
Authorization: Bearer <jwt_token>
```

**Success Response** (200):
```json
{
    "message": "Logged out successfully"
}
```

**Example Request**:
```bash
curl -X POST http://127.0.0.1:8000/auth/logout \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
```

## JWT Token Structure

The JWT token contains:
```json
{
    "user_id": "550e8400-e29b-41d4-a716-446655440000",
    "restaurant_id": 1,
    "exp": 1640995200
}
```

## Error Handling

Common error responses:

**400 Bad Request**:
```json
{
    "detail": "Email already registered"
}
```

**401 Unauthorized**:
```json
{
    "detail": "Invalid email or password"
}
```

**500 Internal Server Error**:
```json
{
    "detail": "Authentication failed: Database error"
}
```

## Security Features

### Password Security
- Passwords are hashed using bcrypt
- Minimum password length enforced by validation
- Passwords never stored in plain text

### JWT Security
- Tokens expire after 30 days
- Tokens include user_id and restaurant_id
- Secret key should be changed in production

### Email Verification
- Users must verify email before login
- Verification emails can be resent
- Unverified accounts cannot authenticate

### Multi-Tenant Isolation
- Each user is associated with a restaurant
- Data is filtered by restaurant_id
- Row Level Security (RLS) enabled in Supabase

## Testing Workflow

### 1. Register a New User
```bash
curl -X POST http://127.0.0.1:8000/auth/signup \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@restaurant.com",
    "password": "testPassword123",
    "restaurant_name": "Test Restaurant"
  }'
```

### 2. Login with Credentials
```bash
curl -X POST http://127.0.0.1:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@restaurant.com",
    "password": "testPassword123"
  }'
```

### 3. Use Token for Protected Endpoints
```bash
# Store the token from login response
TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."

# Access protected endpoint
curl -X GET http://127.0.0.1:8000/auth/me \
  -H "Authorization: Bearer $TOKEN"
```

### 4. Access Restaurant Data
```bash
# Use the same token to access restaurant-specific data
curl -X POST http://127.0.0.1:8000/run-analysis/1 \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json"
```

## Integration with Existing Endpoints

To protect existing endpoints, add the authentication dependency:

```python
from app.api.auth import get_current_user

@router.post("/data/pos")
def create_pos_sales(
    payload: POSPayload, 
    current_user: TokenData = Depends(get_current_user),
    background_tasks: BackgroundTasks
):
    # Use current_user.restaurant_id instead of API key
    restaurant_id = current_user.restaurant_id
    # ... rest of the function
```

## Production Considerations

### Email Service Integration
Replace the placeholder email functions with a real email service:
- Supabase Auth emails
- SendGrid, AWS SES, or other email providers
- Email templates for verification and password reset

### Security Hardening
- Use environment variables for secrets
- Implement rate limiting
- Add CSRF protection
- Enable HTTPS in production

### Monitoring and Logging
- Log authentication events
- Monitor failed login attempts
- Track user registration metrics
- Security audit logging

## Troubleshooting

### Common Issues

**JWT Token Not Working**:
- Check if token is expired
- Verify JWT_SECRET_KEY is correct
- Ensure token format is correct

**Email Not Verified Error**:
- Check if email was sent
- Verify email service configuration
- Manually verify email in database for testing

**Database Connection Issues**:
- Verify Supabase URL and keys
- Check network connectivity
- Ensure database schema is created

### Debug Mode
For debugging, you can temporarily disable email verification:

```python
# In app/core/auth.py, temporarily set email_verified to True
"is_active": True,
"email_verified": True,  # Set to True for testing
```

Remember to revert this change before production deployment.
