from cryptography.fernet import Fernet
import base64
import os
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import json
import logging

logger = logging.getLogger(__name__)

class PasswordManager:
    def __init__(self, key_file="crypto.key"):
        self.key_file = key_file
        self.key = self._load_or_create_key()
        self.fernet = Fernet(self.key)
        
    def _load_or_create_key(self) -> bytes:
        """Load existing key or create a new one."""
        try:
            if os.path.exists(self.key_file):
                with open(self.key_file, "rb") as f:
                    return f.read()
            else:
                key = Fernet.generate_key()
                with open(self.key_file, "wb") as f:
                    f.write(key)
                return key
        except Exception as e:
            logger.error(f"Failed to load/create key: {str(e)}")
            raise
            
    def encrypt_password(self, password: str) -> str:
        """Encrypt a password."""
        try:
            return self.fernet.encrypt(password.encode()).decode()
        except Exception as e:
            logger.error(f"Failed to encrypt password: {str(e)}")
            raise
            
    def decrypt_password(self, encrypted_password: str) -> str:
        """Decrypt an encrypted password."""
        try:
            if not encrypted_password:
                raise ValueError("Encrypted password is empty or None")
                
            return self.fernet.decrypt(encrypted_password.encode()).decode()
        except Exception as e:
            logger.error(f"Failed to decrypt password: {str(e)}")
            raise ValueError(f"Failed to decrypt password: {str(e)}")
            
    def encrypt_config(self, config: dict) -> dict:
        """Encrypt passwords in config."""
        try:
            encrypted_config = config.copy()
            
            # Encrypt main account password if it exists
            if encrypted_config.get("main_account"):
                if encrypted_config["main_account"] is not None:
                    encrypted_config["main_account"]["password"] = self.encrypt_password(
                        encrypted_config["main_account"]["password"]
                    )
                
            # Encrypt alt account passwords
            if "alt_accounts" in encrypted_config:
                for account in encrypted_config["alt_accounts"]:
                    if account and "password" in account:
                        account["password"] = self.encrypt_password(account["password"])
                    
            return encrypted_config
        except Exception as e:
            logger.error(f"Failed to encrypt config: {str(e)}")
            raise
            
    def decrypt_config(self, config: dict) -> dict:
        """Decrypt passwords in config."""
        try:
            decrypted_config = config.copy()
            
            # Decrypt main account password if it exists
            if decrypted_config.get("main_account"):
                if decrypted_config["main_account"] is not None:
                    decrypted_config["main_account"]["password"] = self.decrypt_password(
                        decrypted_config["main_account"]["password"]
                    )
                
            # Decrypt alt account passwords
            if "alt_accounts" in decrypted_config:
                for account in decrypted_config["alt_accounts"]:
                    if account and "password" in account:
                        account["password"] = self.decrypt_password(account["password"])
                    
            return decrypted_config
        except Exception as e:
            logger.error(f"Failed to decrypt config: {str(e)}")
            raise
            
    def save_encrypted_config(self, config: dict, config_path: str) -> None:
        """Save config with encrypted passwords."""
        try:
            encrypted_config = self.encrypt_config(config)
            with open(config_path, "w") as f:
                json.dump(encrypted_config, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save encrypted config: {str(e)}")
            raise
            
    def load_decrypted_config(self, config_path: str) -> dict:
        """Load and decrypt config."""
        try:
            with open(config_path, "r") as f:
                encrypted_config = json.load(f)
            return self.decrypt_config(encrypted_config)
        except Exception as e:
            logger.error(f"Failed to load decrypted config: {str(e)}")
            raise 