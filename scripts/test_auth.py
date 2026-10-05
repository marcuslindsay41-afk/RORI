#!/usr/bin/env python3
"""
Test script for Rori Authentication API
"""

import os
import sys
import requests
import json
from datetime import datetime

# Add parent directory to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

BASE_URL = "http://127.0.0.1:8000"

def print_section(title):
    """Print a formatted section header"""
    print(f"\n{'='*60}")
    print(f" {title}")
    print(f"{'='*60}")

def print_response(response, title="Response"):
    """Print formatted API response"""
    print(f"\n{title}:")
    print(f"Status Code: {response.status_code}")
    try:
        data = response.json()
        print(f"Response Body:\n{json.dumps(data, indent=2)}")
    except:
        print(f"Response Body: {response.text}")

def test_signup():
    """Test user registration"""
    print_section("Testing User Registration")
    
    # Test data
    user_data = {
        "email": f"test{datetime.now().strftime('%Y%m%d%H%M%S')}@example.com",
        "password": "testPassword123",
        "restaurant_name": "Test Restaurant"
    }
    
    print(f"Creating user: {user_data['email']}")
    
    try:
        response = requests.post(f"{BASE_URL}/auth/signup", json=user_data)
        print_response(response, "Registration Response")
        
        if response.status_code == 200:
            data = response.json()
            return data.get("access_token"), data.get("restaurant_id")
        else:
            print("❌ Registration failed")
            return None, None
            
    except Exception as e:
        print(f"❌ Registration error: {e}")
        return None, None

def test_login(email, password):
    """Test user login"""
    print_section("Testing User Login")
    
    login_data = {
        "email": email,
        "password": password
    }
    
    print(f"Logging in user: {email}")
    
    try:
        response = requests.post(f"{BASE_URL}/auth/login", json=login_data)
        print_response(response, "Login Response")
        
        if response.status_code == 200:
            data = response.json()
            return data.get("access_token"), data.get("restaurant_id")
        else:
            print("❌ Login failed")
            return None, None
            
    except Exception as e:
        print(f"❌ Login error: {e}")
        return None, None

def test_get_current_user(token):
    """Test getting current user info"""
    print_section("Testing Get Current User")
    
    headers = {
        "Authorization": f"Bearer {token}"
    }
    
    try:
        response = requests.get(f"{BASE_URL}/auth/me", headers=headers)
        print_response(response, "Current User Response")
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ User authenticated: {data.get('user_id')}")
            return data.get("restaurant_id")
        else:
            print("❌ Failed to get current user")
            return None
            
    except Exception as e:
        print(f"❌ Get current user error: {e}")
        return None

def test_logout(token):
    """Test user logout"""
    print_section("Testing User Logout")
    
    headers = {
        "Authorization": f"Bearer {token}"
    }
    
    try:
        response = requests.post(f"{BASE_URL}/auth/logout", headers=headers)
        print_response(response, "Logout Response")
        
        if response.status_code == 200:
            print("✅ Logout successful")
            return True
        else:
            print("❌ Logout failed")
            return False
            
    except Exception as e:
        print(f"❌ Logout error: {e}")
        return False

def test_protected_endpoint(token, restaurant_id):
    """Test accessing a protected endpoint"""
    print_section("Testing Protected Endpoint Access")
    
    headers = {
        "Authorization": f"Bearer {token}"
    }
    
    try:
        response = requests.post(
            f"{BASE_URL}/run-analysis/{restaurant_id}",
            headers=headers
        )
        print_response(response, "Protected Endpoint Response")
        
        if response.status_code == 200:
            print("✅ Protected endpoint access successful")
            return True
        else:
            print("❌ Protected endpoint access failed")
            return False
            
    except Exception as e:
        print(f"❌ Protected endpoint error: {e}")
        return False

def test_invalid_token():
    """Test accessing endpoint with invalid token"""
    print_section("Testing Invalid Token")
    
    headers = {
        "Authorization": "Bearer invalid_token_here"
    }
    
    try:
        response = requests.get(f"{BASE_URL}/auth/me", headers=headers)
        print_response(response, "Invalid Token Response")
        
        if response.status_code == 401:
            print("✅ Invalid token properly rejected")
            return True
        else:
            print("❌ Invalid token not properly rejected")
            return False
            
    except Exception as e:
        print(f"❌ Invalid token test error: {e}")
        return False

def main():
    """Run all authentication tests"""
    print_section("Rori Authentication API Test Suite")
    print(f"Testing against: {BASE_URL}")
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Test variables
    test_email = None
    test_password = "testPassword123"
    token = None
    restaurant_id = None
    
    # Test 1: Signup
    token, restaurant_id = test_signup()
    if not token:
        print_section("❌ Test Suite Failed")
        print("Registration failed - cannot continue tests")
        return
    
    # Extract email from token (for testing)
    test_email = "test@example.com"  # Would normally store from signup
    
    # Test 2: Login
    login_token, login_restaurant_id = test_login(test_email, test_password)
    if not login_token:
        print_section("❌ Test Suite Failed")
        print("Login failed - cannot continue tests")
        return
    
    token = login_token
    restaurant_id = login_restaurant_id
    
    # Test 3: Get current user
    current_restaurant_id = test_get_current_user(token)
    if not current_restaurant_id:
        print_section("❌ Test Suite Failed")
        print("Get current user failed")
        return
    
    # Test 4: Protected endpoint
    test_protected_endpoint(token, restaurant_id)
    
    # Test 5: Logout
    test_logout(token)
    
    # Test 6: Invalid token
    test_invalid_token()
    
    # Final summary
    print_section("✅ Test Suite Completed")
    print("All authentication tests have been executed.")
    print("Review the responses above for any errors.")
    print(f"Completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

if __name__ == "__main__":
    main()
