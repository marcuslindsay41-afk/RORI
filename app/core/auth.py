import os
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from fastapi import HTTPException, status
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr
from supabase import create_client, Client

# JWT Configuration
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30 * 24 * 60  # 30 days

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Required config is read lazily so non-auth endpoints still start without auth secrets.
_supabase_client: Optional[Client] = None


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(
            f"{name} environment variable is not set (required for authentication; see .env.example)"
        )
    return value


def _get_jwt_secret() -> str:
    return _require_env("JWT_SECRET_KEY")


def _get_supabase() -> Client:
    global _supabase_client
    if _supabase_client is None:
        _supabase_client = create_client(
            _require_env("SUPABASE_URL"), _require_env("SUPABASE_KEY")
        )
    return _supabase_client


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    restaurant_name: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str
    user_id: str
    restaurant_id: int


class TokenData(BaseModel):
    user_id: Optional[str] = None
    restaurant_id: Optional[int] = None


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Generate password hash."""
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create JWT access token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, _get_jwt_secret(), algorithm=ALGORITHM)
    return encoded_jwt


def verify_token(token: str) -> TokenData:
    """Verify JWT token and extract user data."""
    try:
        payload = jwt.decode(token, _get_jwt_secret(), algorithms=[ALGORITHM])
        user_id: str = payload.get("user_id")
        restaurant_id: int = payload.get("restaurant_id")
        
        if user_id is None or restaurant_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        token_data = TokenData(user_id=user_id, restaurant_id=restaurant_id)
        return token_data
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def create_user(user_data: UserCreate) -> Dict[str, Any]:
    """Create a new user and restaurant in Supabase."""
    try:
        # Hash password
        hashed_password = get_password_hash(user_data.password)
        
        # Create restaurant first
        restaurant_response = _get_supabase().table("restaurants").insert({
            "name": user_data.restaurant_name,
            "created_at": datetime.utcnow().isoformat()
        }).execute()
        
        if not restaurant_response.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to create restaurant"
            )
        
        restaurant_id = restaurant_response.data[0]["id"]
        
        # Create user
        user_response = _get_supabase().table("users").insert({
            "email": user_data.email,
            "password_hash": hashed_password,
            "restaurant_id": restaurant_id,
            "is_active": True,
            "email_verified": False,
            "created_at": datetime.utcnow().isoformat()
        }).execute()
        
        if not user_response.data:
            # Clean up restaurant if user creation fails
            _get_supabase().table("restaurants").delete().eq("id", restaurant_id).execute()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to create user"
            )
        
        user_id = user_response.data[0]["id"]
        
        # Create JWT token
        access_token = create_access_token(
            data={"user_id": user_id, "restaurant_id": restaurant_id}
        )
        
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user_id": user_id,
            "restaurant_id": restaurant_id
        }
        
    except Exception as e:
        # Handle duplicate email error
        if "duplicate key" in str(e).lower() or "unique violation" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"User creation failed: {str(e)}"
        )


async def authenticate_user(user_data: UserLogin) -> Dict[str, Any]:
    """Authenticate user and return JWT token."""
    try:
        # Get user by email
        user_response = _get_supabase().table("users").select(
            "id", "password_hash", "restaurant_id", "is_active", "email_verified"
        ).eq("email", user_data.email).single().execute()
        
        if not user_response.data:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password"
            )
        
        user = user_response.data
        
        # Check if user is active
        if not user.get("is_active", True):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Account is disabled"
            )
        
        # Check if email is verified
        if not user.get("email_verified", False):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Email not verified. Please check your inbox."
            )
        
        # Verify password
        if not verify_password(user_data.password, user["password_hash"]):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password"
            )
        
        # Create JWT token
        access_token = create_access_token(
            data={"user_id": user["id"], "restaurant_id": user["restaurant_id"]}
        )
        
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user_id": user["id"],
            "restaurant_id": user["restaurant_id"]
        }
        
    except Exception as e:
        if "No rows found" in str(e):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password"
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Authentication failed: {str(e)}"
        )


async def send_verification_email(email: str) -> bool:
    """Send verification email (placeholder - implement with your email service)."""
    # TODO: Implement email verification sending
    # This would typically use Supabase Auth or an external email service
    print(f"Verification email sent to: {email}")
    return True


async def send_password_reset_email(email: str) -> bool:
    """Send password reset email (placeholder - implement with your email service)."""
    # TODO: Implement password reset email sending
    print(f"Password reset email sent to: {email}")
    return True
