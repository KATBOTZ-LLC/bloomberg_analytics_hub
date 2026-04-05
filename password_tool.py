#!/usr/bin/env python3
"""
Simple Password Encryption/Decryption Tool
For personal testing and verification of encrypted passwords
"""

from utils.crypto_utils import encrypt_password, decrypt_password, verify_password

def main():
    print("=" * 70)
    print("PASSWORD ENCRYPTION/DECRYPTION TOOL")
    print("=" * 70)
    print()
    print("Options:")
    print("1. Encrypt a password")
    print("2. Decrypt an encrypted password")
    print("3. Verify a password against encrypted value")
    print("4. Exit")
    print()

    while True:
        choice = input("Select option (1-4): ").strip()
        print()

        if choice == '1':
            # Encrypt password
            password = input("Enter password to encrypt: ").strip()
            if password:
                encrypted = encrypt_password(password)
                print()
                print("✓ Encrypted Password:")
                print("-" * 70)
                print(encrypted)
                print("-" * 70)
                print()
                print("SQL to insert user:")
                print(f"INSERT INTO \"BLOOMBERG_DATA\".\"USERS\"")
                print(f"    (\"EMAIL\", \"PASSWORD_ENCRYPTED\", \"FULL_NAME\", \"ROLE\")")
                print(f"VALUES")
                print(f"    ('user@example.com', '{encrypted}', 'User Name', 'USER');")
                print()
            else:
                print("✗ Password cannot be empty")
                print()

        elif choice == '2':
            # Decrypt password
            encrypted = input("Enter encrypted password: ").strip()
            if encrypted:
                try:
                    decrypted = decrypt_password(encrypted)
                    print()
                    print("✓ Decrypted Password:")
                    print("-" * 70)
                    print(decrypted)
                    print("-" * 70)
                    print()
                except Exception as e:
                    print()
                    print(f"✗ Failed to decrypt: {str(e)}")
                    print("Make sure you copied the full encrypted string")
                    print()
            else:
                print("✗ Encrypted password cannot be empty")
                print()

        elif choice == '3':
            # Verify password
            password = input("Enter plain password: ").strip()
            encrypted = input("Enter encrypted password: ").strip()
            if password and encrypted:
                try:
                    if verify_password(password, encrypted):
                        print()
                        print("✓ PASSWORD MATCHES!")
                        print("The plain password matches the encrypted value")
                        print()
                    else:
                        print()
                        print("✗ PASSWORD DOES NOT MATCH")
                        print("The plain password does not match the encrypted value")
                        print()
                except Exception as e:
                    print()
                    print(f"✗ Verification failed: {str(e)}")
                    print()
            else:
                print("✗ Both password and encrypted password are required")
                print()

        elif choice == '4':
            print("Goodbye!")
            break

        else:
            print("✗ Invalid option. Please select 1-4")
            print()

if __name__ == '__main__':
    main()
