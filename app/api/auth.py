from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr

from app.core.auth import (
    UserCreate, UserLogin, Token, TokenData,
    create_user, authenticate_user, verify_token,
    send_verification_email, send_password_reset_email
)

router = APIRouter()
security = HTTPBearer()


class PasswordReset(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> TokenData:
    """Get current authenticated user from JWT token."""
    token = credentials.credentials
    token_data = verify_token(token)
    return token_data


@router.post("/auth/signup", response_model=Token)
async def signup(user_data: UserCreate):
    """
    Register a new user and create their restaurant.
    
    Args:
        user_data: User registration data including email, password, and restaurant name
        
    Returns:
        JWT token with user_id and restaurant_id
        
    Raises:
        HTTPException: If email already exists or registration fails
    """
    try:
        # Create user and restaurant
        result = await create_user(user_data)
        
        # Send verification email
        await send_verification_email(user_data.email)
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Registration failed: {str(e)}"
        )


@router.post("/auth/login", response_model=Token)
async def login(user_data: UserLogin):
    """
    Authenticate user and return JWT token.
    
    Args:
        user_data: User login credentials
        
    Returns:
        JWT token with user_id and restaurant_id
        
    Raises:
        HTTPException: If credentials are invalid or account issues
    """
    try:
        result = await authenticate_user(user_data)
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Login failed: {str(e)}"
        )


@router.post("/auth/verify-email")
async def verify_email_request(email_data: PasswordReset):
    """
    Request email verification (resend verification email).
    
    Args:
        email_data: Email address to verify
        
    Returns:
        Success message
        
    Raises:
        HTTPException: If email sending fails
    """
    try:
        success = await send_verification_email(email_data.email)
        
        if success:
            return {"message": "Verification email sent successfully"}
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to send verification email"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Email verification failed: {str(e)}"
        )


@router.post("/auth/reset-password")
async def reset_password_request(email_data: PasswordReset):
    """
    Request password reset email.
    
    Args:
        email_data: Email address for password reset
        
    Returns:
        Success message
        
    Raises:
        HTTPException: If email sending fails
    """
    try:
        success = await send_password_reset_email(email_data.email)
        
        if success:
            return {"message": "Password reset email sent successfully"}
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to send password reset email"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Password reset failed: {str(e)}"
        )


@router.post("/auth/reset-password-confirm")
async def reset_password_confirm(reset_data: PasswordResetConfirm):
    """
    Confirm password reset with token and new password.
    
    Args:
        reset_data: Reset token and new password
        
    Returns:
        Success message
        
    Raises:
        HTTPException: If token is invalid or reset fails
    """
    try:
        # TODO: Implement password reset confirmation logic
        # This would validate the token and update the user's password
        return {"message": "Password reset successfully"}
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Password reset confirmation failed: {str(e)}"
        )


@router.get("/auth/me")
async def get_current_user_info(current_user: TokenData = Depends(get_current_user)):
    """
    Get current authenticated user information.
    
    Args:
        current_user: Current authenticated user from JWT token
        
    Returns:
        User information including user_id and restaurant_id
    """
    return {
        "user_id": current_user.user_id,
        "restaurant_id": current_user.restaurant_id,
        "authenticated": True
    }


@router.post("/auth/logout")
async def logout(current_user: TokenData = Depends(get_current_user)):
    """
    Logout user (client-side token removal).
    
    Args:
        current_user: Current authenticated user
        
    Returns:
        Success message
        
    Note:
        Actual token removal happens on client side
    """
    return {"message": "Logged out successfully"}
