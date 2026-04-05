"""
Simple encryption utilities for password storage
Uses Fernet symmetric encryption for basic security
"""

from cryptography.fernet import Fernet
import base64
import hashlib

# Generate a key from a secret phrase (you should change this to your own secret)
SECRET_PHRASE = "bloomberg_analytics_hub_secret_2024"

def get_cipher_key():
    """Generate a consistent cipher key from the secret phrase"""
    # Create a SHA256 hash of the secret phrase
    hash_obj = hashlib.sha256(SECRET_PHRASE.encode())
    # Use the hash as a base64 key for Fernet
    key = base64.urlsafe_b64encode(hash_obj.digest())
    return key

def encrypt_password(password):
    """
    Encrypt a password string

    Args:
        password (str): Plain text password

    Returns:
        str: Encrypted password as base64 string
    """
    cipher = Fernet(get_cipher_key())
    encrypted = cipher.encrypt(password.encode())
    return encrypted.decode()

def decrypt_password(encrypted_password):
    """
    Decrypt an encrypted password

    Args:
        encrypted_password (str): Encrypted password as base64 string

    Returns:
        str: Decrypted plain text password
    """
    cipher = Fernet(get_cipher_key())
    decrypted = cipher.decrypt(encrypted_password.encode())
    return decrypted.decode()

def verify_password(plain_password, encrypted_password):
    """
    Verify if a plain password matches the encrypted version

    Args:
        plain_password (str): Plain text password to verify
        encrypted_password (str): Encrypted password to compare against

    Returns:
        bool: True if passwords match, False otherwise
    """
    try:
        decrypted = decrypt_password(encrypted_password)
        return plain_password == decrypted
    except Exception:
        return False
