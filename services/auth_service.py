# services/auth_service.py
"""
Service for handling user authentication, including user creation,
password hashing and verification.

Simulates a user database with an in-memory dictionary for demonstration.
In a production environment, replace this with a secure database.
"""
import logging
from passlib.context import CryptContext
from typing import Dict, Optional, Any

try:
    from config import APP_TITLE
except ImportError:
    APP_TITLE = "TradingDashboard_AuthService"

logger = logging.getLogger(APP_TITLE)

# --- Password Hashing Setup ---
# Use bcrypt as the default hashing algorithm
# Deprecated schemes can be added for migrating old passwords if needed
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# --- Simulated User Store (Replace with Database in Production) ---
# Structure: {username: {"hashed_password": "...", "email": "...", "disabled": False}}
_simulated_user_db: Dict[str, Dict[str, Any]] = {}

class AuthService:
    """
    Handles user authentication logic.
    """

    def __init__(self):
        self.logger = logging.getLogger(f"{APP_TITLE}.AuthService")
        # For demonstration, pre-populate with a test user if the DB is empty
        if not _simulated_user_db:
            self.create_user("testuser", "testpassword123", email="test@example.com", is_initial_setup=True)
            self.create_user("admin", "adminpass", email="admin@example.com", is_initial_setup=True)
        self.logger.info("AuthService initialized.")

    def _verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verifies a plain password against a hashed password."""
        try:
            return pwd_context.verify(plain_password, hashed_password)
        except Exception as e:
            self.logger.error(f"Error verifying password: {e}", exc_info=True)
            return False

    def _get_password_hash(self, password: str) -> str:
        """Hashes a plain password."""
        return pwd_context.hash(password)

    def get_user(self, username: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves a user from the simulated database.
        In a real app, this would query your actual database.
        """
        if username in _simulated_user_db:
            return _simulated_user_db[username]
        return None

    def authenticate_user(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        """
        Authenticates a user.
        If successful, returns user data (excluding password).
        Otherwise, returns None.
        """
        self.logger.info(f"Attempting to authenticate user: {username}")
        user = self.get_user(username)
        if not user:
            self.logger.warning(f"Authentication failed: User '{username}' not found.")
            return None
        if user.get("disabled", False):
            self.logger.warning(f"Authentication failed: User '{username}' is disabled.")
            return None
        if not self._verify_password(password, user["hashed_password"]):
            self.logger.warning(f"Authentication failed: Invalid password for user '{username}'.")
            return None
        
        self.logger.info(f"User '{username}' authenticated successfully.")
        # Return user data without the hashed password for security
        user_info_to_return = {k: v for k, v in user.items() if k != "hashed_password"}
        return user_info_to_return

    def create_user(self, username: str, password: str, email: Optional[str] = None, full_name: Optional[str] = None, disabled: bool = False, is_initial_setup: bool = False) -> Dict[str, Any]:
        """
        Creates a new user in the simulated database.
        In a real app, this would insert a new record into your users table.
        """
        if not is_initial_setup: # Only log for actual user creation attempts via UI
             self.logger.info(f"Attempting to create user: {username}")

        if not username or not password:
            msg = "Username and password are required."
            if not is_initial_setup: self.logger.warning(f"User creation failed: {msg}")
            return {"error": msg}
        
        if username in _simulated_user_db:
            msg = f"Username '{username}' already exists."
            if not is_initial_setup: self.logger.warning(f"User creation failed: {msg}")
            return {"error": msg}

        hashed_password = self._get_password_hash(password)
        user_data = {
            "username": username,
            "email": email,
            "full_name": full_name,
            "hashed_password": hashed_password,
            "disabled": disabled
        }
        _simulated_user_db[username] = user_data
        
        if not is_initial_setup:
            self.logger.info(f"User '{username}' created successfully.")
        else:
            # For initial setup, avoid flooding logs if called multiple times during init
            self.logger.debug(f"Initial user '{username}' provisioned in simulated DB.")
            
        return {"message": f"User '{username}' created successfully.", "username": username}

# Example of how to use (for testing this module directly):
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    auth_service_test = AuthService()

    # Test user creation
    print("\n--- Testing User Creation ---")
    new_user_result = auth_service_test.create_user("newuser", "newpass123", email="new@example.com")
    print(new_user_result)
    existing_user_result = auth_service_test.create_user("testuser", "anotherpass") # Should fail
    print(existing_user_result)

    # Test authentication
    print("\n--- Testing Authentication ---")
    auth_success = auth_service_test.authenticate_user("testuser", "testpassword123")
    print(f"Auth success for testuser: {auth_success is not None}")
    if auth_success:
        print(f"Authenticated user data: {auth_success}")

    auth_fail_user = auth_service_test.authenticate_user("nonexistentuser", "password")
    print(f"Auth success for nonexistentuser: {auth_fail_user is not None}")

    auth_fail_pass = auth_service_test.authenticate_user("testuser", "wrongpassword")
    print(f"Auth success for testuser with wrong pass: {auth_fail_pass is not None}")

    # Verify a password directly (for testing hash generation)
    print("\n--- Testing Password Verification ---")
    test_user_data = auth_service_test.get_user("testuser")
    if test_user_data:
        is_correct = auth_service_test._verify_password("testpassword123", test_user_data["hashed_password"])
        print(f"Verification of 'testpassword123' for testuser: {is_correct}")
        is_incorrect = auth_service_test._verify_password("wrongpassword", test_user_data["hashed_password"])
        print(f"Verification of 'wrongpassword' for testuser: {is_incorrect}")
    
    print("\nSimulated User DB state:")
    for uname, udata in _simulated_user_db.items():
        print(f"  {uname}: {{email: {udata.get('email')}, disabled: {udata.get('disabled')}}}")

