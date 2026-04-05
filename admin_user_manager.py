"""
Admin User Management Utility
Use this script to manage users, view/decrypt passwords, and initialize the database
"""

import sys
import logging
from utils.config import load_config, setup_logging
from utils.crypto_utils import encrypt_password, decrypt_password
from db.hana_client import HanaClient
from db.auth_service import AuthService

# Initialize logging
setup_logging()
logger = logging.getLogger(__name__)


def init_database(auth_service, hana_client, schema):
    """Initialize database with USERS table"""
    print("\n=== Initializing Database ===")

    # Create schema if needed
    if hana_client.create_schema_if_not_exists(schema):
        print(f"✓ Schema '{schema}' ready")

    # Create USERS table
    if hana_client.create_table(schema, 'USERS'):
        print(f"✓ Table 'USERS' ready")
        return True
    return False


def create_user(auth_service):
    """Create a new user"""
    print("\n=== Create New User ===")
    email = input("Enter email address: ").strip()
    password = input("Enter password: ").strip()
    full_name = input("Enter full name (optional): ").strip() or None
    role = input("Enter role [USER/ADMIN] (default: USER): ").strip().upper() or 'USER'

    if auth_service.create_user(email, password, full_name, role):
        print(f"✓ User created successfully: {email}")
        return True
    else:
        print(f"✗ Failed to create user. Email may already exist.")
        return False


def view_user(auth_service):
    """View user information with decrypted password"""
    print("\n=== View User (With Decrypted Password) ===")
    email = input("Enter email address: ").strip()

    if not auth_service.hana_client.connection:
        print("✗ No database connection")
        return

    try:
        cursor = auth_service.hana_client.connection.cursor()

        query = f"""
        SELECT "ID", "EMAIL", "PASSWORD_ENCRYPTED", "FULL_NAME", "ROLE",
               "IS_ACTIVE", "CREATED_AT", "LAST_LOGIN", "LOGIN_ATTEMPTS"
        FROM "{auth_service.schema}"."{auth_service.table_name}"
        WHERE "EMAIL" = ?
        """

        cursor.execute(query, [email])
        row = cursor.fetchone()
        cursor.close()

        if row:
            user_id, email, encrypted_pwd, full_name, role, is_active, created_at, last_login, attempts = row
            decrypted_pwd = decrypt_password(encrypted_pwd)

            print(f"\n{'='*60}")
            print(f"User ID:           {user_id}")
            print(f"Email:             {email}")
            print(f"Full Name:         {full_name or 'N/A'}")
            print(f"Role:              {role}")
            print(f"Active:            {is_active}")
            print(f"Created:           {created_at}")
            print(f"Last Login:        {last_login or 'Never'}")
            print(f"Login Attempts:    {attempts}")
            print(f"\n--- PASSWORD INFO ---")
            print(f"Encrypted:         {encrypted_pwd[:50]}...")
            print(f"Decrypted:         {decrypted_pwd}")
            print(f"{'='*60}\n")
        else:
            print(f"✗ User not found: {email}")

    except Exception as e:
        print(f"✗ Error: {str(e)}")


def list_users(auth_service):
    """List all users"""
    print("\n=== All Users ===")
    users = auth_service.list_all_users()

    if not users:
        print("No users found")
        return

    print(f"\n{'ID':<5} {'Email':<30} {'Name':<20} {'Role':<10} {'Active':<8} {'Last Login'}")
    print("-" * 100)

    for user in users:
        print(f"{user['id']:<5} {user['email']:<30} {user['full_name'] or 'N/A':<20} "
              f"{user['role']:<10} {str(user['is_active']):<8} {user['last_login'] or 'Never'}")


def test_login(auth_service):
    """Test login with credentials"""
    print("\n=== Test Login ===")
    email = input("Enter email: ").strip()
    password = input("Enter password: ").strip()

    result = auth_service.authenticate(email, password)

    if result:
        print(f"\n✓ Login successful!")
        print(f"User: {result['full_name'] or result['email']}")
        print(f"Role: {result['role']}")
    else:
        print(f"\n✗ Login failed. Invalid credentials or account inactive.")


def encrypt_text(text):
    """Encrypt arbitrary text"""
    print("\n=== Encrypt Text ===")
    if not text:
        text = input("Enter text to encrypt: ").strip()

    encrypted = encrypt_password(text)
    print(f"\nOriginal:  {text}")
    print(f"Encrypted: {encrypted}")
    return encrypted


def decrypt_text(encrypted_text):
    """Decrypt encrypted text"""
    print("\n=== Decrypt Text ===")
    if not encrypted_text:
        encrypted_text = input("Enter encrypted text: ").strip()

    try:
        decrypted = decrypt_password(encrypted_text)
        print(f"\nEncrypted: {encrypted_text[:50]}...")
        print(f"Decrypted: {decrypted}")
        return decrypted
    except Exception as e:
        print(f"✗ Decryption failed: {str(e)}")
        return None


def main():
    """Main menu"""
    print("\n" + "="*60)
    print("  BLOOMBERG ANALYTICS HUB - User Management")
    print("="*60)

    # Load configuration
    config = load_config()

    # Connect to HANA
    print("\nConnecting to HANA database...")
    try:
        hana_client = HanaClient(config)
        if not hana_client.connect():
            print("✗ Failed to connect to HANA database")
            print("Please check your .env configuration")
            return
        print("✓ Connected to HANA")
    except Exception as e:
        print(f"✗ Error connecting to HANA: {str(e)}")
        return

    schema = config['hana']['schema']
    auth_service = AuthService(hana_client, schema)

    # Initialize database
    init_database(auth_service, hana_client, schema)

    # Add default admin user if it doesn't exist
    if not auth_service.user_exists('admin@g.com'):
        print("\n--- Creating default admin user ---")
        if auth_service.create_user('admin@g.com', 'admin', 'System Administrator', 'ADMIN'):
            print("✓ Default admin user created: admin@g.com / admin")

    while True:
        print("\n" + "-"*60)
        print("OPTIONS:")
        print("  1. Create new user")
        print("  2. View user (with decrypted password)")
        print("  3. List all users")
        print("  4. Test login")
        print("  5. Encrypt text")
        print("  6. Decrypt text")
        print("  7. Exit")
        print("-"*60)

        choice = input("\nSelect option [1-7]: ").strip()

        if choice == '1':
            create_user(auth_service)
        elif choice == '2':
            view_user(auth_service)
        elif choice == '3':
            list_users(auth_service)
        elif choice == '4':
            test_login(auth_service)
        elif choice == '5':
            encrypt_text(None)
        elif choice == '6':
            decrypt_text(None)
        elif choice == '7':
            print("\nExiting...")
            hana_client.close()
            break
        else:
            print("Invalid option")


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nInterrupted by user. Exiting...")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        print(f"\n✗ Unexpected error: {str(e)}")
        sys.exit(1)
