"""Admin dashboard tests."""
import os
import tempfile
from pathlib import Path
import pytest
from fastapi import status
from datetime import datetime


class TestAdminAccess:
    """Test admin access control."""

    def test_admin_dashboard_requires_auth(self, client):
        """Test admin dashboard requires authentication."""
        response = client.get("/admin")
        assert response.status_code == status.HTTP_303_SEE_OTHER
        assert response.headers["Location"] == "/login"

    def test_admin_dashboard_requires_admin_role(self, client, test_user):
        """Test regular users cannot access admin dashboard."""
        # Login as regular user
        client.post(
            "/api/auth/login",
            json={"email": "test@example.com", "password": "testpass123"}
        )

        # Try to access admin dashboard
        response = client.get("/admin", follow_redirects=False)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_admin_can_access_dashboard(self, client, admin_user):
        """Test admin users can access admin dashboard."""
        # Login as admin
        client.post(
            "/api/auth/login",
            json={"email": "admin@example.com", "password": "adminpass123"}
        )

        # Access admin dashboard
        response = client.get("/admin")
        assert response.status_code == status.HTTP_200_OK
        assert b"Admin Dashboard" in response.content


class TestUserManagement:
    """Test admin user management features."""

    def test_list_users_requires_admin(self, client, test_user):
        """Test non-admin users cannot list users."""
        # Login as regular user
        client.post(
            "/api/auth/login",
            json={"email": "test@example.com", "password": "testpass123"}
        )

        response = client.get("/admin/users")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_admin_can_list_users(self, client, admin_user, test_user):
        """Test admin can list all users."""
        # Login as admin
        client.post(
            "/api/auth/login",
            json={"email": "admin@example.com", "password": "adminpass123"}
        )

        response = client.get("/admin/users")
        assert response.status_code == status.HTTP_200_OK
        assert b"User Management" in response.content
        assert b"test@example.com" in response.content
        assert b"admin@example.com" in response.content

    def test_admin_can_promote_user(self, client, admin_user, test_user, db_session):
        """Test admin can promote regular user to admin."""
        # Login as admin
        client.post(
            "/api/auth/login",
            json={"email": "admin@example.com", "password": "adminpass123"}
        )

        # Promote test user
        response = client.post(
            f"/admin/users/{test_user.id}/promote",
            follow_redirects=False
        )
        assert response.status_code == status.HTTP_303_SEE_OTHER
        assert response.headers["Location"] == "/admin/users"

        # Verify user is now admin
        db_session.refresh(test_user)
        assert test_user.is_admin is True

    def test_admin_can_demote_user(self, client, admin_user, db_session):
        """Test admin can demote another admin to regular user."""
        from app.models.auth import User
        from app.services.auth import hash_password

        # Create another admin user
        other_admin = User(
            email="other@example.com",
            username="otheradmin",
            password_hash=hash_password("password123"),
            is_admin=True
        )
        db_session.add(other_admin)
        db_session.commit()
        db_session.refresh(other_admin)

        # Login as admin
        client.post(
            "/api/auth/login",
            json={"email": "admin@example.com", "password": "adminpass123"}
        )

        # Demote other admin
        response = client.post(
            f"/admin/users/{other_admin.id}/demote",
            follow_redirects=False
        )
        assert response.status_code == status.HTTP_303_SEE_OTHER

        # Verify user is now regular user
        db_session.refresh(other_admin)
        assert other_admin.is_admin is False

    def test_admin_cannot_demote_self(self, client, admin_user):
        """Test admin cannot demote themselves."""
        # Login as admin
        client.post(
            "/api/auth/login",
            json={"email": "admin@example.com", "password": "adminpass123"}
        )

        # Try to demote self
        response = client.post(
            f"/admin/users/{admin_user.id}/demote",
            follow_redirects=False
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST


class TestDocumentManagement:
    """Test admin document management features."""

    def test_list_documents_requires_admin(self, client, test_user):
        """Test non-admin users cannot list documents."""
        # Login as regular user
        client.post(
            "/api/auth/login",
            json={"email": "test@example.com", "password": "testpass123"}
        )

        response = client.get("/admin/documents")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_admin_can_list_documents(self, client, admin_user):
        """Test admin can list documents."""
        # Login as admin
        client.post(
            "/api/auth/login",
            json={"email": "admin@example.com", "password": "adminpass123"}
        )

        response = client.get("/admin/documents")
        assert response.status_code == status.HTTP_200_OK
        assert b"Toolkit Documents" in response.content

    def test_admin_can_access_upload_page(self, client, admin_user):
        """Test admin can access document upload page."""
        # Login as admin
        client.post(
            "/api/auth/login",
            json={"email": "admin@example.com", "password": "adminpass123"}
        )

        response = client.get("/admin/documents/upload")
        assert response.status_code == status.HTTP_200_OK
        assert b"Upload Toolkit Document" in response.content

    def test_admin_can_toggle_document_active(self, client, admin_user, db_session):
        """Test admin can toggle document active status."""
        from app.models.toolkit import ToolkitDocument

        # Create a test document
        doc = ToolkitDocument(
            version_tag="test-v1",
            source_filename="test.docx",
            file_path="/tmp/test.docx",
            chunk_count=0,
            is_active=True
        )
        db_session.add(doc)
        db_session.commit()
        db_session.refresh(doc)

        # Login as admin
        client.post(
            "/api/auth/login",
            json={"email": "admin@example.com", "password": "adminpass123"}
        )

        # Toggle active status
        response = client.post(
            f"/admin/documents/{doc.id}/toggle-active",
            follow_redirects=False
        )
        assert response.status_code == status.HTTP_303_SEE_OTHER

        # Verify document is now inactive
        db_session.refresh(doc)
        assert doc.is_active is False

        # Toggle back
        response = client.post(
            f"/admin/documents/{doc.id}/toggle-active",
            follow_redirects=False
        )
        assert response.status_code == status.HTTP_303_SEE_OTHER

        # Verify document is active again
        db_session.refresh(doc)
        assert doc.is_active is True

    def test_reindex_document_not_found(self, client, admin_user):
        """Test reindexing non-existent document returns 404."""
        # Login as admin
        client.post(
            "/api/auth/login",
            json={"email": "admin@example.com", "password": "adminpass123"}
        )

        # Try to reindex non-existent document
        response = client.post(
            "/admin/documents/00000000-0000-0000-0000-000000000000/reindex"
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_reindex_document_file_missing(self, client, admin_user, db_session):
        """Test reindexing document with missing file returns error."""
        from app.models.toolkit import ToolkitDocument

        # Create a test document with non-existent file
        doc = ToolkitDocument(
            version_tag="test-v2",
            source_filename="missing.docx",
            file_path="/tmp/nonexistent.docx",
            chunk_count=0
        )
        db_session.add(doc)
        db_session.commit()
        db_session.refresh(doc)

        # Login as admin
        client.post(
            "/api/auth/login",
            json={"email": "admin@example.com", "password": "adminpass123"}
        )

        # Try to reindex
        response = client.post(f"/admin/documents/{doc.id}/reindex")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert b"not found" in response.content


class TestAnalytics:
    """Test admin analytics features."""

    def test_analytics_requires_admin(self, client, test_user):
        """Test non-admin users cannot access analytics."""
        # Login as regular user
        client.post(
            "/api/auth/login",
            json={"email": "test@example.com", "password": "testpass123"}
        )

        response = client.get("/admin/analytics")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_admin_can_access_analytics(self, client, admin_user):
        """Test admin can access analytics dashboard."""
        # Login as admin
        client.post(
            "/api/auth/login",
            json={"email": "admin@example.com", "password": "adminpass123"}
        )

        response = client.get("/admin/analytics")
        assert response.status_code == status.HTTP_200_OK
        assert b"Analytics" in response.content
        assert b"Top Queries" in response.content
        assert b"Issue Types" in response.content
        assert b"Rating Distribution" in response.content

    def test_analytics_shows_chat_data(self, client, admin_user, test_user, db_session):
        """Test analytics displays chat logs and feedback."""
        from app.models.toolkit import ChatLog, Feedback

        # Create test chat logs
        chat1 = ChatLog(
            user_id=str(test_user.id),
            query="What is the process?",
            answer="Here is the process...",
            citations=[],
            similarity_score=[0.95]
        )
        chat2 = ChatLog(
            user_id=str(test_user.id),
            query="How do I start?",
            answer="To start...",
            citations=[],
            similarity_score=[0.88]
        )
        db_session.add(chat1)
        db_session.add(chat2)
        db_session.commit()
        db_session.refresh(chat1)
        db_session.refresh(chat2)

        # Create feedback
        feedback1 = Feedback(
            chat_log_id=str(chat1.id),
            rating=5,
            issue_type="accurate"
        )
        feedback2 = Feedback(
            chat_log_id=str(chat2.id),
            rating=2,
            issue_type="incomplete"
        )
        db_session.add(feedback1)
        db_session.add(feedback2)
        db_session.commit()

        # Login as admin
        client.post(
            "/api/auth/login",
            json={"email": "admin@example.com", "password": "adminpass123"}
        )

        # Access analytics
        response = client.get("/admin/analytics")
        assert response.status_code == status.HTTP_200_OK

        # Check that data is displayed
        content = response.content.decode()
        assert "What is the process?" in content or "How do I start?" in content


class TestDashboardStats:
    """Test admin dashboard statistics."""

    def test_dashboard_shows_stats(self, client, admin_user, test_user, db_session):
        """Test dashboard displays correct statistics."""
        from app.models.toolkit import ToolkitDocument, ToolkitChunk, ChatLog, Feedback

        # Create test data
        doc = ToolkitDocument(
            version_tag="v1.0",
            source_filename="toolkit.docx",
            file_path="/tmp/toolkit.docx",
            chunk_count=1
        )
        db_session.add(doc)
        db_session.commit()
        db_session.refresh(doc)

        chunk = ToolkitChunk(
            document_id=str(doc.id),
            chunk_text="Sample chunk text",
            chunk_index=0
        )
        db_session.add(chunk)
        db_session.commit()

        chat = ChatLog(
            user_id=str(test_user.id),
            query="Test query",
            answer="Test answer",
            citations=[],
            similarity_score=[0.9]
        )
        db_session.add(chat)
        db_session.commit()
        db_session.refresh(chat)

        feedback = Feedback(
            chat_log_id=str(chat.id),
            rating=4
        )
        db_session.add(feedback)
        db_session.commit()

        # Login as admin
        client.post(
            "/api/auth/login",
            json={"email": "admin@example.com", "password": "adminpass123"}
        )

        # Access dashboard
        response = client.get("/admin")
        assert response.status_code == status.HTTP_200_OK

        content = response.content.decode()
        # Should show user counts
        assert "Total Users" in content
        # Should show document stats
        assert "Documents" in content
        # Should show chat activity
        assert "Chat Activity" in content
