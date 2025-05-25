# services/auth_service.py
"""
Service for handling user authentication using a database backend.
Uses SQLAlchemy for ORM and Passlib for password hashing.
Compatible with SQLite.
"""
import logging
from passlib.context import CryptContext
from typing import Optional, Any, Dict as TypingDict
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, Index
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
import datetime # For timezone.utc

try:
    from config import APP_TITLE
except ImportError:
    APP_TITLE = "TradingDashboard_AuthService"

logger = logging.getLogger(APP_TITLE)

# --- Password Hashing Setup ---
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# --- SQLAlchemy Setup ---
Base = declarative_base()

# --- User Model Definition ---
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True) # Autoincrement is default for Integer PK in SQLite
    username = Column(String(100), unique=True, index=True, nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=True)
    full_name = Column(String(255), nullable=True)
    hashed_password = Column(String(255), nullable=False)
    disabled = Column(Boolean, default=False)
    # SQLite stores DateTime as TEXT in ISO format by default.
    # SQLAlchemy handles conversion to/from Python datetime objects.
    # Using timezone.utc ensures consistency if data moves between DBs.
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.datetime.now(datetime.timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.datetime.now(datetime.timezone.utc), onupdate=lambda: datetime.datetime.now(datetime.timezone.utc))

    def __repr__(self):
        return f"<User(username='{self.username}', email='{self.email}')>"

class AuthService:
    """
    Handles user authentication logic with a database backend.
    """

    def __init__(self, db_engine: Any): # Expects an SQLAlchemy engine
        self.logger = logging.getLogger(f"{APP_TITLE}.AuthService")
        self.engine = db_engine
        # For SQLite, it's good practice to ensure sessions are handled correctly,
        # especially in multi-threaded environments like Streamlit.
        # The engine creation in app.py will handle connect_args.
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        self.logger.info("AuthService initialized with database engine.")
        self._init_db()

    def _init_db(self):
        """
        Creates the 'users' table in the database if it doesn't already exist.
        """
        try:
            Base.metadata.create_all(bind=self.engine)
            self.logger.info("'users' table checked/created successfully (if it didn't exist).")
            # Pre-populate with default users if the table is new and empty
            with self.SessionLocal() as session:
                if session.query(User).count() == 0:
                    self.logger.info("User table is empty. Creating default 'testuser' and 'admin'.")
                    self.create_user_direct_to_db(session, "testuser", "testpassword123", email="test@example.com", is_initial_setup=True)
                    self.create_user_direct_to_db(session, "admin", "adminpass", email="admin@example.com", is_initial_setup=True)
        except SQLAlchemyError as e:
            self.logger.error(f"Error during _init_db (table creation or default user): {e}", exc_info=True)


    def _verify_password(self, plain_password: str, hashed_password: str) -> bool:
        try:
            return pwd_context.verify(plain_password, hashed_password)
        except Exception as e: # Broad exception for passlib errors
            self.logger.error(f"Error verifying password: {e}", exc_info=True)
            return False

    def _get_password_hash(self, password: str) -> str:
        return pwd_context.hash(password)

    def get_user(self, session: Session, username: str) -> Optional[User]:
        try:
            return session.query(User).filter(User.username == username).first()
        except SQLAlchemyError as e:
            self.logger.error(f"Database error getting user '{username}': {e}", exc_info=True)
            return None

    def authenticate_user(self, username: str, password: str) -> Optional[TypingDict[str, Any]]:
        self.logger.info(f"Attempting to authenticate user: {username}")
        try:
            with self.SessionLocal() as session:
                db_user = self.get_user(session, username)
                if not db_user:
                    self.logger.warning(f"Authentication failed: User '{username}' not found.")
                    return None
                if db_user.disabled:
                    self.logger.warning(f"Authentication failed: User '{username}' is disabled.")
                    return None
                if not self._verify_password(password, db_user.hashed_password):
                    self.logger.warning(f"Authentication failed: Invalid password for user '{username}'.")
                    return None
                
                self.logger.info(f"User '{username}' authenticated successfully.")
                return {
                    "username": db_user.username, "email": db_user.email,
                    "full_name": db_user.full_name, "disabled": db_user.disabled
                }
        except SQLAlchemyError as e:
            self.logger.error(f"Database error during authentication for '{username}': {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error during authentication for '{username}': {e}", exc_info=True)
            return None

    def create_user_direct_to_db(self, session: Session, username: str, password: str, email: Optional[str] = None, full_name: Optional[str] = None, disabled: bool = False, is_initial_setup: bool = False) -> TypingDict[str, Any]:
        if not is_initial_setup:
            self.logger.info(f"Attempting to create user (direct_to_db): {username}")

        if not username or not password:
            msg = "Username and password are required."
            if not is_initial_setup: self.logger.warning(f"User creation failed: {msg}")
            return {"error": msg}

        existing_user = self.get_user(session, username)
        if existing_user:
            msg = f"Username '{username}' already exists."
            if not is_initial_setup: self.logger.warning(f"User creation failed: {msg}")
            return {"error": msg}

        hashed_password = self._get_password_hash(password)
        new_user = User(
            username=username, email=email, full_name=full_name,
            hashed_password=hashed_password, disabled=disabled
        )
        try:
            session.add(new_user)
            session.commit()
            session.refresh(new_user)
            log_msg = f"Initial user '{username}' provisioned in DB." if is_initial_setup else f"User '{username}' created successfully in DB."
            self.logger.log(logging.DEBUG if is_initial_setup else logging.INFO, log_msg)
            return {"message": f"User '{username}' created successfully.", "username": new_user.username}
        except IntegrityError as e:
            session.rollback()
            self.logger.error(f"Database integrity error creating user '{username}': {e}", exc_info=True)
            return {"error": f"Could not create user '{username}'. Username or email might already exist."}
        except SQLAlchemyError as e:
            session.rollback()
            self.logger.error(f"Database error creating user '{username}': {e}", exc_info=True)
            return {"error": f"A database error occurred while creating user '{username}'."}

    def create_user(self, username: str, password: str, email: Optional[str] = None, full_name: Optional[str] = None, disabled: bool = False) -> TypingDict[str, Any]:
        self.logger.info(f"Public create_user called for: {username}")
        try:
            with self.SessionLocal() as session:
                return self.create_user_direct_to_db(session, username, password, email, full_name, disabled, is_initial_setup=False)
        except Exception as e:
            self.logger.error(f"Failed to create session or other error in public create_user for '{username}': {e}", exc_info=True)
            return {"error": "Could not connect to the database or an unexpected error occurred."}

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    TEST_DATABASE_URL_SQLITE = "sqlite:///./test_auth_sqlite.db" # Create a local file for testing
    if os.path.exists("test_auth_sqlite.db"):
        os.remove("test_auth_sqlite.db") # Clean slate for testing
        
    test_engine_sqlite = create_engine(TEST_DATABASE_URL_SQLITE, connect_args={"check_same_thread": False})
    
    auth_service_test_sqlite = AuthService(db_engine=test_engine_sqlite)

    print("\n--- Testing User Creation (SQLite DB) ---")
    new_user_result_sqlite = auth_service_test_sqlite.create_user("newuser_sqlite", "newpass123_sqlite", email="new_sqlite@example.com")
    print(new_user_result_sqlite)
    
    print("\n--- Testing Authentication (SQLite DB) ---")
    auth_success_sqlite = auth_service_test_sqlite.authenticate_user("testuser", "testpassword123")
    print(f"Auth success for testuser (SQLite): {auth_success_sqlite is not None}")
    if auth_success_sqlite:
        print(f"Authenticated user data (SQLite): {auth_success_sqlite}")

    print("\nUsers in SQLite DB:")
    with auth_service_test_sqlite.SessionLocal() as session:
        all_users_sqlite = session.query(User).all()
        for user_obj_sqlite in all_users_sqlite:
            print(f"  ID: {user_obj_sqlite.id}, Username: {user_obj_sqlite.username}, Email: {user_obj_sqlite.email}, Created: {user_obj_sqlite.created_at}")
    
    if os.path.exists("test_auth_sqlite.db"):
        os.remove("test_auth_sqlite.db") # Clean up test DB file
        print("\nCleaned up test_auth_sqlite.db")
