"""
Authentication service for user management and login
Handles encrypted password storage and validation
"""

import logging
from datetime import datetime
from utils.crypto_utils import encrypt_password, verify_password
from utils.email_service import EmailService


class AuthService:
    """Service for user authentication and management"""

    def __init__(self, hana_client, schema='BLOOMBERG_DATA'):
        """
        Initialize authentication service

        Args:
            hana_client: HanaClient instance
            schema (str): Database schema name
        """
        self.logger = logging.getLogger(__name__)
        self.hana_client = hana_client
        self.schema = schema
        self.table_name = 'USERS'
        self.email_service = EmailService()

    def create_user(self, email, password, full_name=None, role='USER'):
        """
        Create a new user with encrypted password

        Args:
            email (str): User email address
            password (str): Plain text password
            full_name (str): User's full name
            role (str): User role (USER, ADMIN, etc.)

        Returns:
            bool: True if user created successfully, False otherwise
        """
        if not self.hana_client.connection:
            self.logger.error("No connection to HANA. Cannot create user.")
            return False

        try:
            # Check if user already exists
            if self.user_exists(email):
                self.logger.warning(f"User with email {email} already exists")
                return False

            # Encrypt the password
            encrypted_password = encrypt_password(password)

            cursor = self.hana_client.connection.cursor()

            insert_sql = f"""
            INSERT INTO "{self.schema}"."{self.table_name}" (
                "EMAIL", "PASSWORD_ENCRYPTED", "FULL_NAME", "ROLE"
            ) VALUES (?, ?, ?, ?)
            """

            cursor.execute(insert_sql, [email, encrypted_password, full_name, role])
            self.hana_client.connection.commit()
            cursor.close()

            self.logger.info(f"User created successfully: {email}")
            return True

        except Exception as e:
            self.logger.error(f"Error creating user: {str(e)}")
            return False

    def authenticate(self, email, password, ip_address=None):
        """
        Authenticate a user with email and password

        Args:
            email (str): User email address
            password (str): Plain text password
            ip_address (str): IP address of the login attempt

        Returns:
            dict: User information if authenticated, None otherwise
        """
        if not self.hana_client.connection:
            self.logger.error("No connection to HANA. Cannot authenticate.")
            return None

        try:
            cursor = self.hana_client.connection.cursor()

            # Get user from database
            query = f"""
            SELECT "ID", "EMAIL", "PASSWORD_ENCRYPTED", "FULL_NAME", "ROLE",
                   "IS_ACTIVE", "LOGIN_ATTEMPTS"
            FROM "{self.schema}"."{self.table_name}"
            WHERE "EMAIL" = ?
            """

            cursor.execute(query, [email])
            row = cursor.fetchone()

            if not row:
                self.logger.warning(f"Login attempt for non-existent user: {email}")
                cursor.close()

                # Send email alert for unregistered user attempt
                self.logger.info(f"Sending email alert for unregistered user attempt: {email}")
                self.email_service.send_new_user_attempt_alert(
                    attempted_email=email,
                    ip_address=ip_address,
                    timestamp=datetime.now()
                )

                return None

            user_id, user_email, encrypted_password, full_name, role, is_active, login_attempts = row

            # Check if account is active
            if not is_active:
                self.logger.warning(f"Login attempt for inactive account: {email}")
                cursor.close()
                return None

            # Verify password
            if verify_password(password, encrypted_password):
                # Password is correct - update last login and reset login attempts
                update_sql = f"""
                UPDATE "{self.schema}"."{self.table_name}"
                SET "LAST_LOGIN" = ?, "LOGIN_ATTEMPTS" = 0
                WHERE "EMAIL" = ?
                """
                cursor.execute(update_sql, [datetime.now(), email])
                self.hana_client.connection.commit()
                cursor.close()

                self.logger.info(f"Successful login for user: {email}")
                return {
                    'id': user_id,
                    'email': user_email,
                    'full_name': full_name,
                    'role': role
                }
            else:
                # Password is incorrect - increment login attempts
                new_attempts = login_attempts + 1
                update_sql = f"""
                UPDATE "{self.schema}"."{self.table_name}"
                SET "LOGIN_ATTEMPTS" = ?
                WHERE "EMAIL" = ?
                """
                cursor.execute(update_sql, [new_attempts, email])
                self.hana_client.connection.commit()
                cursor.close()

                self.logger.warning(f"Failed login attempt for user: {email} (attempt {new_attempts})")

                # Send email alert on EVERY failed attempt
                self.logger.info(f"Failed login attempt #{new_attempts} for {email} - sending email alert")
                self.email_service.send_failed_login_alert(
                    attempted_email=email,
                    ip_address=ip_address,
                    timestamp=datetime.now()
                )

                return None

        except Exception as e:
            self.logger.error(f"Error during authentication: {str(e)}")
            return None

    def user_exists(self, email):
        """
        Check if a user with the given email exists

        Args:
            email (str): User email address

        Returns:
            bool: True if user exists, False otherwise
        """
        if not self.hana_client.connection:
            return False

        try:
            cursor = self.hana_client.connection.cursor()

            query = f"""
            SELECT COUNT(*) FROM "{self.schema}"."{self.table_name}"
            WHERE "EMAIL" = ?
            """

            cursor.execute(query, [email])
            count = cursor.fetchone()[0]
            cursor.close()

            return count > 0

        except Exception as e:
            self.logger.error(f"Error checking user existence: {str(e)}")
            return False

    def get_user_info(self, email):
        """
        Get user information (without password)

        Args:
            email (str): User email address

        Returns:
            dict: User information or None
        """
        if not self.hana_client.connection:
            return None

        try:
            cursor = self.hana_client.connection.cursor()

            query = f"""
            SELECT "ID", "EMAIL", "FULL_NAME", "ROLE", "IS_ACTIVE",
                   "CREATED_AT", "LAST_LOGIN", "LOGIN_ATTEMPTS"
            FROM "{self.schema}"."{self.table_name}"
            WHERE "EMAIL" = ?
            """

            cursor.execute(query, [email])
            row = cursor.fetchone()
            cursor.close()

            if row:
                return {
                    'id': row[0],
                    'email': row[1],
                    'full_name': row[2],
                    'role': row[3],
                    'is_active': row[4],
                    'created_at': str(row[5]) if row[5] else None,
                    'last_login': str(row[6]) if row[6] else None,
                    'login_attempts': row[7]
                }
            return None

        except Exception as e:
            self.logger.error(f"Error getting user info: {str(e)}")
            return None

    def list_all_users(self):
        """
        List all users (without passwords)

        Returns:
            list: List of user dictionaries
        """
        if not self.hana_client.connection:
            return []

        try:
            cursor = self.hana_client.connection.cursor()

            query = f"""
            SELECT "ID", "EMAIL", "FULL_NAME", "ROLE", "IS_ACTIVE",
                   "CREATED_AT", "LAST_LOGIN"
            FROM "{self.schema}"."{self.table_name}"
            ORDER BY "CREATED_AT" DESC
            """

            cursor.execute(query)
            rows = cursor.fetchall()
            cursor.close()

            users = []
            for row in rows:
                users.append({
                    'id': row[0],
                    'email': row[1],
                    'full_name': row[2],
                    'role': row[3],
                    'is_active': row[4],
                    'created_at': str(row[5]) if row[5] else None,
                    'last_login': str(row[6]) if row[6] else None
                })

            return users

        except Exception as e:
            self.logger.error(f"Error listing users: {str(e)}")
            return []
