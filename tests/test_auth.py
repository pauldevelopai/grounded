"""Authentication tests."""
import pytest
from fastapi import status


class TestRegistration:
    """Test user registration."""

    def test_register_success(self, client):
        """Test successful user registration."""
        response = client.post(
            "/api/auth/register",
            json={"email": "newuser@example.com", "password": "password123"}
        )
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["email"] == "newuser@example.com"
        assert data["is_admin"] is False
        assert "id" in data

    def test_register_duplicate_email(self, client, test_user):
        """Test registration with duplicate email fails."""
        response = client.post(
            "/api/auth/register",
            json={"email": test_user.email, "password": "password123"}
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "already registered" in response.json()["detail"]

    def test_register_invalid_email(self, client):
        """Test registration with invalid email fails."""
        response = client.post(
            "/api/auth/register",
            json={"email": "notanemail", "password": "password123"}
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_register_short_password(self, client):
        """Test registration with short password fails."""
        response = client.post(
            "/api/auth/register",
            json={"email": "newuser@example.com", "password": "short"}
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


class TestLogin:
    """Test user login."""

    def test_login_success(self, client, test_user):
        """Test successful login."""
        response = client.post(
            "/api/auth/login",
            json={"email": "test@example.com", "password": "testpass123"}
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["message"] == "Login successful"
        assert "access_token" in response.cookies
        assert "refresh_token" in response.cookies

    def test_login_wrong_password(self, client, test_user):
        """Test login with wrong password fails."""
        response = client.post(
            "/api/auth/login",
            json={"email": "test@example.com", "password": "wrongpassword"}
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_login_nonexistent_user(self, client):
        """Test login with non-existent user fails."""
        response = client.post(
            "/api/auth/login",
            json={"email": "nobody@example.com", "password": "password123"}
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestAuthenticatedEndpoints:
    """Test authenticated endpoints."""

    def test_get_me_authenticated(self, client, test_user):
        """Test getting current user when authenticated."""
        # Login first
        login_response = client.post(
            "/api/auth/login",
            json={"email": "test@example.com", "password": "testpass123"}
        )
        assert login_response.status_code == status.HTTP_200_OK

        # Get current user
        response = client.get("/api/auth/me")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["email"] == "test@example.com"
        assert data["is_admin"] is False

    def test_get_me_unauthenticated(self, client):
        """Test getting current user when not authenticated fails."""
        response = client.get("/api/auth/me")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestLogout:
    """Test logout."""

    def test_logout(self, client, test_user):
        """Test logout clears cookies."""
        # Login first
        login_response = client.post(
            "/api/auth/login",
            json={"email": "test@example.com", "password": "testpass123"}
        )
        assert "access_token" in login_response.cookies

        # Logout
        logout_response = client.post("/api/auth/logout")
        assert logout_response.status_code == status.HTTP_200_OK
        assert logout_response.json()["message"] == "Logout successful"


class TestAdminAccess:
    """Test admin access control."""

    def test_admin_user_is_admin(self, client, admin_user):
        """Test admin user has admin flag."""
        # Login as admin
        login_response = client.post(
            "/api/auth/login",
            json={"email": "admin@example.com", "password": "adminpass123"}
        )
        assert login_response.status_code == status.HTTP_200_OK

        # Check user info
        response = client.get("/api/auth/me")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["is_admin"] is True

    def test_regular_user_not_admin(self, client, test_user):
        """Test regular user does not have admin flag."""
        # Login as regular user
        login_response = client.post(
            "/api/auth/login",
            json={"email": "test@example.com", "password": "testpass123"}
        )
        assert login_response.status_code == status.HTTP_200_OK

        # Check user info
        response = client.get("/api/auth/me")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["is_admin"] is False
