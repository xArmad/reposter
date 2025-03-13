#!/usr/bin/env python3

import sys
import os
import json
from cryptography.fernet import Fernet

# Add the current directory to the path to ensure imports work correctly
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

"""
Instagram Repost Tool - Main entry point.
"""

# Apply crypto fixes to ensure reliable password decryption
from crypto_utils import PasswordManager
from instagram_utils import InstagramReposter

# Store the original init function
original_pm_init = PasswordManager.__init__

# Define our patched init function
def patched_pm_init(self, key_file="crypto.key"):
    """Patched init function to ensure consistent key usage."""
    # Call the original init first
    original_pm_init(self, key_file)
    
    # Now load the key directly from file to ensure it's the same key we tested with
    try:
        with open(key_file, "rb") as f:
            self.key = f.read()
        self.fernet = Fernet(self.key)
    except Exception as e:
        print(f"Error loading crypto key: {str(e)}")

# Apply the monkey patch
PasswordManager.__init__ = patched_pm_init

# Create a function to test password decryption first
def test_decrypt():
    """Test that password decryption works properly."""
    try:
        # Load config
        with open("config.json", "r") as f:
            config = json.load(f)
        
        # Create password manager
        pm = PasswordManager()
        
        # Try to decrypt the main account password
        if config.get("main_account") and config["main_account"].get("password"):
            username = config["main_account"]["username"]
            encrypted_pw = config["main_account"]["password"]
            decrypted_pw = pm.decrypt_password(encrypted_pw)
            return True, decrypted_pw
        else:
            return False, None
    except Exception as e:
        return False, None

# Monkey-patch the _login_selected_main method in InstagramReposter
original_login_method = InstagramReposter._login_selected_main

def patched_login_method(self, username: str):
    """Patched login method to handle crypto issues."""
    try:
        # Check if username exists in accounts
        account = None
        
        # Check if it's the main account
        if self.config["main_account"] and self.config["main_account"]["username"] == username:
            account = self.config["main_account"]
        
        # Check if it's an alt account
        if not account:
            for alt in self.config["alt_accounts"]:
                if alt["username"] == username:
                    account = alt
                    break
        
        if not account:
            return None
        
        # Use our test function to decrypt the password
        success, password = test_decrypt()
        
        if not success or not password:
            return None
        
        # Create and configure client
        client = self._login(username, password)
        
        if not client:
            return None
            
        # Set as main client
        self.main_client = client
        return client
        
    except Exception as e:
        return None

# Apply the monkey patch
InstagramReposter._login_selected_main = patched_login_method

# Now import and start the app normally
import customtkinter as ctk
from components.instagram_repost_app import InstagramRepostApp

# Set up customtkinter appearance
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

if __name__ == "__main__":
    app = InstagramRepostApp()
    app.mainloop() 