from instagrapi import Client
from typing import List, Dict, Optional, Tuple, Any
import os
import yaml
import logging
from crypto_utils import PasswordManager
import json
import threading
from datetime import datetime
import concurrent.futures
import time
from functools import partial
import shutil
from pathlib import Path
import requests
from PIL import Image
from instagrapi.types import Media, UserShort
from instagrapi.exceptions import ClientError, LoginRequired, ReloginAttemptExceeded, BadPassword
# Import VerificationDialog dynamically when needed to avoid circular imports

# Custom exceptions
class IPBlacklistError(Exception):
    """Raised when Instagram has blacklisted the user's IP address."""
    pass

# Custom JSON encoder to handle datetime objects
class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        # Handle HttpUrl objects by converting them to strings
        if str(type(obj)).find('HttpUrl') > -1:
            return str(obj)
        return super().default(obj)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class InstagramClient(Client):
    """Custom Instagram client with enhanced security and verification handling."""
    
    def __init__(self, username=None, verification_handler=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.username = username
        self.verification_handler = verification_handler
        self.verification_code = None
        self.verification_event = threading.Event()
        self.password_manager = PasswordManager()
        
        # Set minimal timeouts and delays for faster operation
        self.delay_range = [0.1, 0.3]  # Further reduced from [0.2, 0.5]
        self.request_timeout = 8  # Further reduced from 10 seconds
        self.handle_exception = None  # Don't auto-handle exceptions
        
        # Disable unnecessary features to speed up
        self.disable_presence = True
        self.disable_video_data = True
        
        # Set additional performance options
        self.inject_sessionid_to_public = True  # Use sessionid for public requests too
        self.max_connection_attempts = 1  # Don't retry connections too many times
        
    def challenge_code_handler(self, username, choice):
        """Override the default challenge code handler."""
        if self.verification_handler:
            # Reset event and code
            self.verification_event.clear()
            self.verification_code = None
            
            # Request verification code in main thread
            self.verification_handler(username, choice, self)
            
            # Wait for verification code with timeout
            if not self.verification_event.wait(timeout=180):  # 180 second timeout (3 minutes)
                raise Exception("Verification code entry timed out")
            return self.verification_code
            
        raise Exception("No verification handler set")
        
    def set_verification_code(self, code):
        """Set the verification code after it's entered by the user.
        
        Args:
            code: The verification code entered by the user
        """
        self.verification_code = code
        logger.info(f"Verification code set for {self.username}")
        # Immediately signal that the code is ready
        self.verification_event.set()
        
    def change_verification_handler(self, handler):
        """Change the verification handler function.
        
        Args:
            handler: New verification handler function
        """
        self.verification_handler = handler
        logger.info(f"Verification handler updated for {self.username}")
        
    def save_session(self):
        """Save session to encrypted file for faster login next time."""
        try:
            if not self.username:
                logger.error("Cannot save session: username not set")
                return False
                
            if not os.path.exists("sessions"):
                os.makedirs("sessions")
            
            session_file = f"sessions/{self.username}.json"
            
            # Get session data as dictionary
            session_data = self.get_settings()
            
            # Convert to JSON string
            json_str = json.dumps(session_data, cls=DateTimeEncoder)
            
            # Encrypt the data
            encrypted_data = self.password_manager.encrypt_password(json_str)
            
            # Create encrypted file structure
            encrypted_file = {
                "encrypted_data": encrypted_data,
                "encryption_version": 1
            }
            
            # Write to file
            with open(session_file, "w") as f:
                json.dump(encrypted_file, f, indent=2)
                
            logger.info(f"Saved encrypted session for {self.username}")
            return True
            
        except Exception as e:
            logging.error(f"Failed to save session for {self.username}: {str(e)}")
            return False
            
    def load_session(self):
        """Load session from file if available."""
        try:
            if not self.username:
                logger.error("Cannot load session: username not set")
            return False
                
            session_file = f"sessions/{self.username}.json"
            if not os.path.exists(session_file):
                logger.info(f"No session file found for {self.username}")
                return False
                
            with open(session_file, "r") as f:
                file_data = json.load(f)
                
            # Check if file is encrypted
            if "encrypted_data" in file_data:
                # Decrypt the data
                encrypted_data = file_data["encrypted_data"]
                json_str = self.password_manager.decrypt_password(encrypted_data)
                
                # Parse the decrypted JSON
                session_data = json.loads(json_str)
                
                # Load the settings into the client
                self.set_settings(session_data)
                logger.info(f"Loaded encrypted session for {self.username}")
                
            else:
                # Legacy unencrypted format - load directly and convert to encrypted on next save
                self.set_settings(file_data)
                logger.info(f"Loaded unencrypted session for {self.username} (will be encrypted on next save)")
                
            return True
            
        except Exception as e:
            logging.error(f"Failed to load session for {self.username}: {str(e)}")
            return False
            
    def login(self, password, **kwargs):
        """Optimized login method with better session handling."""
        if not self.username:
            raise ValueError("Username not set")
            
        if not password:
            raise ValueError("Password cannot be empty")
            
        start_time = time.time()
        logger.info(f"Starting login for {self.username}")
        
        try:
            # Try to use the most direct login method
            result = super().login(self.username, password, **kwargs)
            logger.info(f"Login successful for {self.username} in {time.time() - start_time:.2f}s")
            return result
        except Exception as e:
            error_msg = str(e)
            logger.warning(f"Login failed for {self.username}: {error_msg}")
            
            # If login fails, try to handle specific errors
            if "challenge_required" in error_msg:
                logger.info(f"Handling challenge for {self.username}...")
                try:
                    # Handle the challenge (this will trigger verification_handler)
                    self.handle_challenge()
                    
                    # Try login again after the challenge is handled
                    logger.info(f"Retrying login for {self.username} after challenge...")
                    result = super().login(self.username, password, **kwargs)
                    logger.info(f"Login after challenge successful for {self.username} in {time.time() - start_time:.2f}s")
                    return result
                except Exception as challenge_error:
                    logger.error(f"Challenge handling failed for {self.username}: {str(challenge_error)}")
                    # Re-raise the original exception if challenge handling fails
                    raise Exception(f"Login failed: {str(challenge_error)}") from e
            
            # For other types of errors, just raise the original exception
            raise
            
    def get_account_info(self):
        """Get basic account information to validate session."""
        return self.account_info()

    def handle_verification(self, choice_type=None):
        """Handle verification requests from Instagram during login or other processes.
        
        Args:
            choice_type: Type of verification (sms, email, etc.)
            
        Returns:
            bool: True if verification succeeded, False otherwise
        """
        try:
            if not self.verification_handler:
                logger.error("No verification handler set for verification")
                return False
                
            # Pass the challenge to the verification handler
            code = self.verification_handler(self.username, choice_type, self)
            
            # If code is None, verification was cancelled
            if code is None:
                logger.warning("Verification cancelled by user")
                return False
                
            # Store the verification code for the parent challenge handler
            self.verification_code = code
            logger.info(f"Verification code received for {self.username}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to handle verification: {str(e)}")
            return False

class InstagramReposter:
    def __init__(self, config_path: str = "config.json", selected_main_account: str = None, parent=None):
        """Initialize Instagram Reposter with config file."""
        # Initialize properties
        self.config_path = config_path
        self.password_manager = PasswordManager()
        self.config = self._load_config()
        self.parent = parent
        self.media_cache = {}
        self.alt_media_cache = {}
        self.alt_posts_cache = {}
        self.main_client = None
        self.alt_clients = []
        self.cache_lock = threading.Lock()  # Lock for thread-safe cache access
        self.repost_status_changed = False  # Flag to indicate repost status has changed
        
        try:
            if selected_main_account:
                self.main_client = self._login_selected_main(selected_main_account)
            else:
                self.main_client = None
                self.alt_clients = []
        except Exception as e:
            logger.error(f"Error initializing Instagram Reposter: {str(e)}")
            self.main_client = None
            self.alt_clients = []

    def _load_config(self) -> dict:
        """Load configuration from JSON file."""
        try:
            # Default empty config structure
            default_config = {
                "main_account": None,
                "alt_accounts": []
            }
            
            if os.path.exists(self.config_path):
                try:
                    config = self.password_manager.load_decrypted_config(self.config_path)
                    # Ensure config has all required fields
                    if "main_account" not in config:
                        config["main_account"] = None
                    if "alt_accounts" not in config:
                        config["alt_accounts"] = []
                    return config
                except Exception as e:
                    logger.warning(f"Failed to load existing config, creating new one: {str(e)}")
                    return default_config
            else:
                # Create new config file
                self.password_manager.save_encrypted_config(default_config, self.config_path)
                return default_config
                
        except Exception as e:
            logger.error(f"Failed to load config: {str(e)}")
            raise

    def _save_config(self):
        """Save configuration with encrypted passwords."""
        try:
            self.password_manager.save_encrypted_config(self.config, self.config_path)
        except Exception as e:
            logger.error(f"Failed to save config: {str(e)}")
            raise

    def get_available_accounts(self) -> List[str]:
        """Get list of all available accounts."""
        accounts = []
        if self.config["main_account"]:
            accounts.append(self.config["main_account"]["username"])
        for account in self.config["alt_accounts"]:
            accounts.append(account["username"])
        return accounts

    def get_accounts(self) -> List[Dict]:
        """Get list of all accounts with their details."""
        accounts = []
        
        # Add main account if it exists
        if self.config["main_account"]:
            main_account = self.config["main_account"].copy()
            # Check if this account is logged in
            main_account["is_logged_in"] = (
                self.main_client is not None and 
                self.main_client.username == main_account["username"]
            )
            accounts.append(main_account)
        
        # Add alt accounts
        for account in self.config["alt_accounts"]:
            account_copy = account.copy()
            # Check if this account is logged in as an alt client
            account_copy["is_logged_in"] = any(
                client is not None and client.username == account["username"] 
                for client in self.alt_clients
            )
            accounts.append(account_copy)
            
        return accounts

    def _login_selected_main(self, username: str) -> InstagramClient:
        """Login to the selected main account."""
        try:
            # Ensure username exists in accounts
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
                logger.error(f"Account {username} not found in config")
                return None
            
            # Check if password exists and is not empty
            if "password" not in account or not account["password"]:
                logger.error(f"No password found for {username}")
                return None
                
            # Attempt to decrypt password
            password = None
            try:
                encrypted_password = account["password"]
                password = self.password_manager.decrypt_password(encrypted_password)
                logger.info(f"Successfully decrypted password for {username}")
            except Exception as e:
                logger.error(f"Failed to decrypt password for {username}: {str(e)}")
                return None
                    
            # Create and configure client
            logger.info(f"Logging in as {username}")
            client = self._login(username, password)
            
            if not client:
                logger.error(f"Failed to login to selected main account {username}")
                return None
                
            # Set as main client
            self.main_client = client
            return client
            
        except Exception as e:
            logger.error(f"Failed to login to selected main account {username}: {str(e)}")
            return None

    def initialize_alt_accounts(self, main_username=None):
        """Initialize alternative accounts from config."""
        try:
            self.alt_clients = []
            
            # If there's a main username, add other accounts as alts
            if main_username:
                # Add the configured main account if it's not the main username
                if self.config["main_account"] and self.config["main_account"]["username"] != main_username:
                    try:
                        main_account = self.config["main_account"]
                        # Decrypt password
                        password = None
                        if "password" in main_account:
                            encrypted_password = main_account["password"]
                            password = self.password_manager.decrypt_password(encrypted_password)
                            
                        main_client = self._login(main_account["username"], password)
                        if main_client:
                            self.alt_clients.append(main_client)
                    except Exception as e:
                        logger.error(f"Failed to add main account as alt client: {str(e)}")
                
                # Add all other alt accounts (except the one that's now main)
                for account in self.config["alt_accounts"]:
                    if account["username"] != main_username:
                        try:
                            # Decrypt password
                            password = None
                            if "password" in account:
                                encrypted_password = account["password"]
                                password = self.password_manager.decrypt_password(encrypted_password)
                                
                            alt_client = self._login(account["username"], password)
                            if alt_client:
                                self.alt_clients.append(alt_client)
                        except Exception as e:
                            logger.error(f"Failed to add alt client {account['username']}: {str(e)}")
            else:
                # If no main username, just add all alt accounts
                if self.config["main_account"]:
                    try:
                        main_account = self.config["main_account"]
                        # Decrypt password
                        password = None
                        if "password" in main_account:
                            encrypted_password = main_account["password"]
                            password = self.password_manager.decrypt_password(encrypted_password)
                            
                        main_client = self._login(main_account["username"], password)
                        if main_client:
                            self.alt_clients.append(main_client)
                    except Exception as e:
                        logger.error(f"Failed to add main account as alt client: {str(e)}")
                
                # Add all alt accounts
                for account in self.config["alt_accounts"]:
                    try:
                        # Decrypt password
                        password = None
                        if "password" in account:
                            encrypted_password = account["password"]
                            password = self.password_manager.decrypt_password(encrypted_password)
                            
                        alt_client = self._login(account["username"], password)
                        if alt_client:
                            self.alt_clients.append(alt_client)
                    except Exception as e:
                        logger.error(f"Failed to add alt client {account['username']}: {str(e)}")
            
            logger.info(f"Initialized {len(self.alt_clients)} alternative accounts")
        except Exception as e:
            logger.error(f"Error initializing alternative accounts: {str(e)}")
            self.alt_clients = []

    def _login(self, username: str, password: str = None) -> "InstagramClient":
        """Internal method to log in to Instagram.
        
        Args:
            username: Instagram username
            password: Instagram password
            
        Returns:
            InstagramClient: A logged-in Instagram client
        """
        # Validate that both username and password are provided
        if not username:
            logger.warning("Login failed: Username not provided")
            return None
            
        if not password:
            logger.warning(f"Login failed for {username}: Password not provided")
            return None
            
        # Create the client
        client = InstagramClient(
            username=username, 
            verification_handler=self.verification_handler
        )
        
        try:
            # Login with password
            client.login(password)
            logger.info(f"Successfully logged in as {username}")
            return client
        except Exception as e:
            logger.warning(f"Login failed for {username}: {str(e)}")
            return None

    def _cache_alt_posts(self, client):
        """Cache recent posts from an alt account with improved detection."""
        try:
            # Skip if client has no username
            if not client.username:
                logger.warning("Client has no username, skipping cache update")
                return {'captions': {}, 'media_ids': {}, 'original_media_ids': {}, 'thumbnail_urls': {}}
                
            # Use the more efficient v1 API directly
            logger.info(f"Caching posts for {client.username}")
            start_time = time.time()
            
            # Implement retry mechanism for API errors
            max_retries = 3
            retry_count = 0
            medias = []
            last_error = None
            
            while retry_count <= max_retries and not medias:
                try:
                    # Use a timeout to prevent hanging
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        # Reduce the number of posts to fetch for faster response
                        future = executor.submit(client.user_medias_v1, client.user_id, 15)  # Reduced from 20 to 15
                        try:
                            # Increased timeout from 8 to 12 seconds
                            medias = future.result(timeout=12)
                            logger.info(f"Fetched {len(medias)} media items for {client.username} in {time.time() - start_time:.2f}s")
                            break  # Success, exit retry loop
                        except concurrent.futures.TimeoutError:
                            retry_count += 1
                            last_error = "timeout"
                            logger.warning(f"Media fetch for {client.username} timed out after 12 seconds (attempt {retry_count}/{max_retries+1})")
                            if retry_count <= max_retries:
                                # Wait a bit longer between retries
                                time.sleep(2)  # Increased from 1 to 2 seconds
                                continue
                            else:
                                logger.error(f"Media fetch for {client.username} timed out after all retries")
                                # Try to reconnect
                                if self.reconnect_client(client):
                                    logger.info(f"Reconnected {client.username}, trying one final time")
                                    try:
                                        # One final attempt after reconnect with longer timeout
                                        future = executor.submit(client.user_medias_v1, client.user_id, 15)
                                        medias = future.result(timeout=15)  # Even longer timeout for final try
                                        logger.info(f"Fetched {len(medias)} media items after reconnect")
                                    except Exception as e:
                                        logger.error(f"Still failed after reconnect: {str(e)}")
                                        return {'captions': {}, 'media_ids': {}, 'original_media_ids': {}, 'thumbnail_urls': {}}
                except Exception as e:
                    retry_count += 1
                    last_error = str(e)
                    logger.warning(f"Error fetching media for {client.username} (attempt {retry_count}/{max_retries+1}): {str(e)}")
                    if retry_count <= max_retries:
                        time.sleep(2)  # Increased wait time between retries
                        continue
                    else:
                        logger.error(f"Failed to get media after all retries: {str(e)}")
                        return {'captions': {}, 'media_ids': {}, 'original_media_ids': {}, 'thumbnail_urls': {}}
            
            # If we still don't have any media after retries, return empty cache
            if not medias:
                logger.warning(f"No media found for {client.username} after retries. Last error: {last_error}")
                return {'captions': {}, 'media_ids': {}, 'original_media_ids': {}, 'thumbnail_urls': {}}
            
            # Create a more comprehensive cache structure
            cache = {
                'captions': {},
                'media_ids': {},
                'original_media_ids': {},
                'thumbnail_urls': {}
            }
            
            # Process media with a timeout to prevent hanging on large collections
            start_process_time = time.time()
            max_process_time = 8  # Increased from 5 to 8 seconds
            
            for media in medias:
                # Check if we've exceeded the maximum processing time
                if time.time() - start_process_time > max_process_time:
                    logger.warning(f"Processing media for {client.username} is taking too long, stopping early")
                    break
                    
                # Cache by caption
                caption = (media.caption_text or "").strip()
                if caption:
                    # Store the actual caption text as the key for exact matching
                    cache['captions'][caption] = True
                    # Log the caption being cached for debugging
                    logger.info(f"Caching caption for {client.username}: '{caption[:50]}...' (truncated)")
                    
                # Cache by media ID
                media_id = str(media.pk)
                cache['media_ids'][media_id] = True
                
                # Cache thumbnail URL if available
                if hasattr(media, 'thumbnail_url') and media.thumbnail_url:
                    thumbnail_url = str(media.thumbnail_url)
                    cache['thumbnail_urls'][thumbnail_url] = True
                
                # Try to extract original media ID from caption if it contains it
                # Some repost apps add the original media ID in the caption
                if caption and "ID:" in caption:
                    try:
                        # Extract potential media IDs from caption
                        import re
                        id_matches = re.findall(r'ID:(\d+)', caption)
                        for id_match in id_matches:
                            cache['original_media_ids'][id_match] = True
                    except:
                        pass
            
            logger.info(f"Cached {len(cache['captions'])} captions, {len(cache['media_ids'])} media IDs, and {len(cache['thumbnail_urls'])} thumbnail URLs for {client.username}")
            return cache
            
        except Exception as e:
            logger.error(f"Error in _cache_alt_posts for {client.username}: {str(e)}")
            return {'captions': {}, 'media_ids': {}, 'original_media_ids': {}, 'thumbnail_urls': {}}

    def check_repost_status(self, media):
        """Check if media has been reposted by any alt account using multiple detection methods."""
        try:
            caption = getattr(media, "caption_text", "") or ""
            caption = caption.strip()
            media_id = str(getattr(media, "pk", "unknown"))
            reposted_accounts = []
            
            # Initialize alt_posts_cache if it doesn't exist
            if not hasattr(self, "alt_posts_cache"):
                self.alt_posts_cache = {}
                logger.info("Created missing alt_posts_cache")
            
            # Skip if no alt clients
            if not self.alt_clients:
                return reposted_accounts
                
            # Skip if no caption (can't reliably check repost status without caption)
            if not caption:
                logger.info(f"Media {media_id} has no caption, skipping repost check")
                return reposted_accounts
            
            # Force cache refresh if it's older than 5 minutes or doesn't exist
            current_time = time.time()
            cache_needs_update = False
            
            for client in self.alt_clients:
                # Skip clients with no username
                if not client.username:
                    logger.warning("Found client with no username, skipping")
                    continue
                    
                with self.cache_lock:
                    if (client.username not in self.alt_posts_cache or
                        current_time - self.alt_posts_cache.get(f"{client.username}_timestamp", 0) > 300):
                        cache_needs_update = True
                        break
            
            # Update cache if needed
            if cache_needs_update:
                logger.info("Cache needs update, refreshing alt posts cache")
                # Use a thread pool to check all accounts in parallel with timeout
                with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                    futures = {}
                    
                    for client in self.alt_clients:
                        # Skip clients with no username
                        if not client.username:
                            logger.warning("Found client with no username, skipping cache update")
                            continue
                            
                        # Submit cache update task
                        futures[executor.submit(self._cache_alt_posts, client)] = client.username
                    
                    # Wait for all cache updates to complete with timeout - 15 seconds total
                    try:
                        for future in concurrent.futures.as_completed(futures, timeout=15):
                            client_username = futures[future]
                            try:
                                result = future.result()
                                with self.cache_lock:
                                    self.alt_posts_cache[client_username] = result
                                    self.alt_posts_cache[f"{client_username}_timestamp"] = current_time
                                    logger.info(f"Updated cache for {client_username}")
                            except Exception as e:
                                logger.warning(f"Failed to update cache for {client_username}: {str(e)}")
                    except concurrent.futures.TimeoutError:
                        logger.warning("Some cache updates timed out, proceeding with available data")
            
            # Check if we have any valid cache data
            valid_cache_exists = False
            for client in self.alt_clients:
                if client.username in self.alt_posts_cache and self.alt_posts_cache[client.username].get('captions'):
                    valid_cache_exists = True
                    break
                    
            # If no valid cache exists, try a direct API approach as fallback
            if not valid_cache_exists:
                logger.warning("No valid cache data available, using fallback repost detection")
                return self._fallback_repost_check(media)
            
            # Now check if caption exists in any of the cached posts
            for client in self.alt_clients:
                # Skip clients with no username
                if not client.username:
                    logger.warning("Found client with no username, skipping repost check")
                    continue
                    
                with self.cache_lock:
                    if client.username in self.alt_posts_cache:
                        cache = self.alt_posts_cache[client.username]
                        
                        # Skip if cache is empty (likely due to API error)
                        if not cache or not cache.get('captions'):
                            logger.warning(f"Cache for {client.username} is empty, skipping repost check")
                            continue
                        
                        # Check by exact caption match
                        if caption in cache.get('captions', {}):
                            logger.info(f"Found exact caption match for {media_id} in {client.username}")
                            reposted_accounts.append(client.username)
                            continue
                        
                        # Also check by media ID if available
                        if media_id in cache.get('media_ids', {}):
                            logger.info(f"Found media ID match for {media_id} in {client.username}")
                            reposted_accounts.append(client.username)
                            continue
                            
                        # Check by original media ID
                        if media_id in cache.get('original_media_ids', {}):
                            logger.info(f"Found original media ID match for {media_id} in {client.username}")
                            reposted_accounts.append(client.username)
                            continue
                            
                        # Check for media URL or thumbnail URL match
                        if hasattr(media, 'thumbnail_url') and media.thumbnail_url:
                            thumbnail_url = str(media.thumbnail_url)
                            if thumbnail_url in cache.get('thumbnail_urls', {}):
                                logger.info(f"Found thumbnail URL match for {media_id} in {client.username}")
                                reposted_accounts.append(client.username)
                                continue
            
            if reposted_accounts:
                # Filter out any None values that might have slipped through
                reposted_accounts = [account for account in reposted_accounts if account is not None]
                if reposted_accounts:  # Check again after filtering
                    logger.info(f"Media {media_id} has been reposted to: {', '.join(reposted_accounts)}")
            else:
                logger.info(f"Repost status for {media_id}: No reposts found")
            
            return reposted_accounts
            
        except Exception as e:
            logger.error(f"Error checking repost status: {str(e)}")
            # Return empty list instead of raising exception
            return []

    def _fallback_repost_check(self, media):
        """Fallback method for repost detection when API fails."""
        try:
            caption = (media.caption_text or "").strip()
            media_id = str(media.pk)
            reposted_accounts = []
            
            if not caption or not self.alt_clients:
                return reposted_accounts
                
            logger.info(f"Using fallback repost detection for media {media_id}")
            
            # Try to directly fetch a few recent posts from each alt account
            for client in self.alt_clients:
                if not client.username:
                    continue
                    
                try:
                    # Try to get just a few posts with a short timeout
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(client.user_medias_v1, client.user_id, 5)  # Just get 5 most recent
                        try:
                            alt_medias = future.result(timeout=5)  # Short 5 second timeout
                            
                            # Check each media
                            for alt_media in alt_medias:
                                alt_caption = (alt_media.caption_text or "").strip()
                                
                                # Direct caption comparison
                                if caption == alt_caption:
                                    logger.info(f"Fallback: Found exact caption match for {media_id} in {client.username}")
                                    reposted_accounts.append(client.username)
                                    break
                                    
                                # High similarity check
                                elif alt_caption and len(alt_caption) > 10 and len(caption) > 10:
                                    from difflib import SequenceMatcher
                                    similarity = SequenceMatcher(None, caption, alt_caption).ratio()
                                    if similarity > 0.9:
                                        logger.info(f"Fallback: Found similar caption match ({similarity:.2f}) for {media_id} in {client.username}")
                                        reposted_accounts.append(client.username)
                                        break
                        except concurrent.futures.TimeoutError:
                            logger.warning(f"Fallback: Media fetch for {client.username} timed out")
                            continue
                except Exception as e:
                    logger.warning(f"Fallback: Error checking {client.username}: {str(e)}")
                    continue
            
            if reposted_accounts:
                logger.info(f"Fallback: Media {media_id} has been reposted to: {', '.join(reposted_accounts)}")
            else:
                logger.info(f"Fallback: No reposts found for {media_id}")
                
            return reposted_accounts
            
        except Exception as e:
            logger.error(f"Error in fallback repost check: {str(e)}")
            return []

    def get_user_medias(self, amount: int = 20) -> List:
        """Get recent media from main account with video views and repost status."""
        try:
            # Check if we have a valid main client and username
            if not self.main_client or not self.main_client.username:
                logger.warning("No main client or username available")
                return []

            # Clean up any invalid cache files
            invalid_cache = "thumbnails/media_cache_None.json"
            if os.path.exists(invalid_cache):
                try:
                    os.remove(invalid_cache)
                    logger.info("Cleaned up invalid cache file")
                except Exception as e:
                    logger.warning(f"Failed to clean up invalid cache file: {str(e)}")

            # Check for cached media first
            cache_file = f"thumbnails/media_cache_{self.main_client.username}.json"
            
            if os.path.exists(cache_file):
                try:
                    # Check if cache is less than 5 minutes old (reduced from 10 minutes)
                    cache_time = os.path.getmtime(cache_file)
                    if (datetime.now().timestamp() - cache_time) < 300:  # 5 minutes
                        with open(cache_file, 'r') as f:
                            cached_data = json.load(f)
                            logger.info(f"Using cached media data from {cache_file}")
                            # Convert cached data back to MediaWrapper objects
                            from instagrapi.types import Media
                            medias = []
                            for item in cached_data:
                                try:
                                    # Create Media object correctly - it expects a dictionary, not positional arguments
                                    media = Media(**item)  # Use keyword arguments instead
                                    wrapped = MediaWrapper(media)
                                    wrapped.view_count = item.get('view_count', 0)
                                    wrapped.reposted_to = item.get('reposted_to', [])
                                    medias.append(wrapped)
                                except Exception as e:
                                    logger.warning(f"Failed to load cached media item: {str(e)}")
                            return medias
                except Exception as e:
                    logger.warning(f"Failed to load media cache: {str(e)}")
            
            # Try v1 API directly (more reliable than GraphQL)
            logger.info(f"Fetching media using v1 API")
            
            # Use a more direct approach to get media
            try:
                # Create directory for thumbnails if it doesn't exist
                if not os.path.exists("thumbnails"):
                    os.makedirs("thumbnails")
                    
                # Get media with v1 API with timeout
                start_time = time.time()
                
                # Use a shorter timeout and retry mechanism
                max_retries = 2
                retry_count = 0
                medias = []
                
                while retry_count <= max_retries and not medias:
                    try:
                        with concurrent.futures.ThreadPoolExecutor() as executor:
                            future = executor.submit(self.main_client.user_medias_v1, self.main_client.user_id, amount)
                            try:
                                # Reduce timeout to fail faster if there's an issue
                                medias = future.result(timeout=10)  # 10 second timeout (reduced from 15)
                                logger.info(f"Fetched {len(medias)} media items in {time.time() - start_time:.2f}s")
                            except concurrent.futures.TimeoutError:
                                retry_count += 1
                                logger.warning(f"Media fetch timed out after 10 seconds (attempt {retry_count}/{max_retries+1})")
                                if retry_count <= max_retries:
                                    # Wait a bit before retrying
                                    time.sleep(1)
                                    continue
                                else:
                                    logger.error("Media fetch timed out after all retries")
                                    return []
                    except Exception as e:
                        retry_count += 1
                        logger.warning(f"Error fetching media (attempt {retry_count}/{max_retries+1}): {str(e)}")
                        if retry_count <= max_retries:
                            # Wait a bit before retrying
                            time.sleep(1)
                            continue
                        else:
                            logger.error(f"Failed to get media after all retries: {str(e)}")
                            return []
                
                # If we still don't have any media after retries, return empty list
                if not medias:
                    logger.warning("No media found after retries")
                    return []
                
                # Process medias without additional API calls for each video
                processed_medias = []
                for media in medias:
                    # Create wrapper for the media object
                    wrapped_media = MediaWrapper(media)
                    
                    if wrapped_media.media_type == 2:  # Video
                        wrapped_media.view_count = (
                            getattr(media, 'view_count', None) or
                            getattr(media, 'play_count', None) or
                            getattr(media, 'video_view_count', None) or
                            0
                        )
                    else:
                        wrapped_media.view_count = 0
                    
                    # Add repost status to wrapped media object
                    try:
                        wrapped_media.reposted_to = self.check_repost_status(media)
                    except Exception as e:
                        logger.warning(f"Failed to check repost status for media {media.pk}: {str(e)}")
                        wrapped_media.reposted_to = []
                        
                    processed_medias.append(wrapped_media)
                
                # Cache the results
                try:
                    # Convert MediaWrapper objects to serializable dictionaries
                    cache_data = []
                    for media in processed_medias:
                        # Convert to dict and handle HttpUrl objects
                        media_dict = media._media.dict()
                        
                        # Convert HttpUrl objects to strings
                        for key, value in list(media_dict.items()):
                            if str(type(value)).find('HttpUrl') > -1:
                                media_dict[key] = str(value)
                            # Also handle nested dictionaries that might contain HttpUrl objects
                            elif isinstance(value, dict):
                                for k, v in list(value.items()):
                                    if str(type(v)).find('HttpUrl') > -1:
                                        value[k] = str(v)
                        
                        # Add additional properties
                        media_dict['view_count'] = media.view_count
                        media_dict['reposted_to'] = media.reposted_to
                        cache_data.append(media_dict)
                    
                    with open(cache_file, 'w') as f:
                        json.dump(cache_data, f, cls=DateTimeEncoder)
                    logger.info(f"Cached media data to {cache_file}")
                except Exception as e:
                    logger.warning(f"Failed to cache media data: {str(e)}")
                    
                return processed_medias
                
            except Exception as e:
                logger.error(f"Failed to get media with v1 API: {str(e)}")
                # If v1 API fails, return empty list instead of raising
                return []
            
        except Exception as e:
            logger.error(f"Failed to get user medias: {str(e)}")
            # Return empty list instead of raising
            return []

    def download_media(self, media_pk: int) -> Dict:
        """Download media and its metadata from main account."""
        try:
            start_time = time.time()
            logger.info(f"Downloading media {media_pk}")
            
            # Use a timeout for media_info
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(self.main_client.media_info, media_pk)
                try:
                    media_info = future.result(timeout=10)  # 10 second timeout
                except concurrent.futures.TimeoutError:
                    logger.error(f"Media info fetch timed out for {media_pk}")
                    raise Exception(f"Media info fetch timed out for {media_pk}")
            
            media_type = media_info.media_type
            
            # Use a timeout for download
            with concurrent.futures.ThreadPoolExecutor() as executor:
                if media_type == 2:  # Video
                    future = executor.submit(self.main_client.video_download, media_pk)
                    view_count = (
                        getattr(media_info, 'view_count', None) or
                        getattr(media_info, 'play_count', None) or
                        getattr(media_info, 'video_view_count', None) or
                        0
                    )
                else:
                    future = executor.submit(self.main_client.photo_download, media_pk)
                    view_count = 0
                
                try:
                    path = future.result(timeout=30)  # 30 second timeout
                except concurrent.futures.TimeoutError:
                    logger.error(f"Media download timed out for {media_pk}")
                    raise Exception(f"Media download timed out for {media_pk}")
            
            logger.info(f"Downloaded media {media_pk} in {time.time() - start_time:.2f}s")
            
            return {
                "path": path,
                "caption": media_info.caption_text,
                "media_type": media_type,
                "usertags": media_info.usertags,
                "location": media_info.location,
                "view_count": view_count
            }
        except Exception as e:
            logger.error(f"Failed to download media {media_pk}: {str(e)}")
            raise

    def repost_media(self, media_data: Dict) -> None:
        """Repost media to all alt accounts."""
        for client in self.alt_clients:
            try:
                start_time = time.time()
                logger.info(f"Reposting to {client.username}")
                
                # Use a timeout for upload
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    if media_data["media_type"] == 2:  # Video
                        future = executor.submit(
                            client.video_upload,
                            path=media_data["path"],
                            caption=media_data["caption"],
                            usertags=media_data["usertags"],
                            location=media_data["location"]
                        )
                    else:  # Photo
                        future = executor.submit(
                            client.photo_upload,
                            path=media_data["path"],
                            caption=media_data["caption"],
                            usertags=media_data["usertags"],
                            location=media_data["location"]
                        )
                    
                    try:
                        result = future.result(timeout=120)  # 2 minute timeout for upload
                        logger.info(f"Successfully reposted to {client.username} in {time.time() - start_time:.2f}s")
                    except concurrent.futures.TimeoutError:
                        logger.error(f"Repost to {client.username} timed out after 120 seconds")
                        continue
                
            except Exception as e:
                logger.error(f"Failed to repost to {client.username}: {str(e)}")

    def cleanup(self, path: str) -> None:
        """Clean up temporary files."""
        if os.path.exists(path):
            try:
                os.remove(path)
                logger.info(f"Cleaned up {path}")
            except Exception as e:
                logger.warning(f"Failed to clean up {path}: {str(e)}")

    def add_account(self, username: str, password: str) -> bool:
        """Add a new account to the config."""
        try:
            # First verify we can login with these credentials
            test_client = InstagramClient(username=username, verification_handler=lambda u, c, client: None)  # Initialize with dummy handler
            
            # If we have a parent window, set up proper verification handler
            if self.parent:
                def verification_handler(username, choice_type, client):
                    # Map Instagram's choice types to user-friendly names
                    choice_map = {
                        "email": "EMAIL",
                        "sms": "SMS",
                        "otp": "Authenticator App",
                        "choice": "EMAIL"  # Default to email for choice challenge
                    }
                    # Convert choice_type to string before using lower()
                    choice_str = str(choice_type).lower()
                    challenge_type = choice_map.get(choice_str, str(choice_type))
                    
                    # Show verification dialog
                    from components.verification_dialog import VerificationDialog
                    code = VerificationDialog.show_dialog(self.parent, username, challenge_type)
                    if not code:
                        raise Exception("Verification cancelled by user")
                    client.set_verification_code(code)
                
                test_client.verification_handler = verification_handler
            
            # Try to login
            test_client.login(password)
            
            # Add to config
            if self.config["main_account"] and username == self.config["main_account"]["username"]:
                raise ValueError("Account already exists as main account")
            
            for account in self.config["alt_accounts"]:
                if account["username"] == username:
                    raise ValueError("Account already exists as alt account")
            
            self.config["alt_accounts"].append({
                "username": username,
                "password": password
            })
            
            # Save config
            self._save_config()
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to add account {username}: {str(e)}")
            return False

    def test_connection(self, username: str, password: str) -> Tuple[bool, str]:
        """Test if a connection can be established with the provided credentials.
        
        Returns:
            Tuple[bool, str]: A tuple containing (success, message)
        """
        try:
            # Create a temporary client for testing
            test_client = InstagramClient(username=username, verification_handler=lambda u, c, client: None)
            
            # If we have a parent window, set up proper verification handler
            if self.parent:
                def verification_handler(username, choice_type, client):
                    # Map Instagram's choice types to user-friendly names
                    choice_map = {
                        "email": "EMAIL",
                        "sms": "SMS",
                        "otp": "Authenticator App",
                        "choice": "EMAIL"  # Default to email for choice challenge
                    }
                    # Convert choice_type to string before using lower()
                    choice_str = str(choice_type).lower()
                    challenge_type = choice_map.get(choice_str, str(choice_type))
                    
                    # Show verification dialog
                    from components.verification_dialog import VerificationDialog
                    code = VerificationDialog.show_dialog(self.parent, username, challenge_type)
                    if not code:
                        return False, "Verification cancelled by user"
                    client.set_verification_code(code)
                
                test_client.verification_handler = verification_handler
            
            # Try to login - we only pass password now since username is already set in the client
            test_client.login(password)
            
            # Verify login by fetching user info
            user_info = test_client.user_info(test_client.user_id)
            
            # If we get here, connection was successful
            return True, "Connection successful"
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Connection test failed for {username}: {error_msg}")
            return False, error_msg

    def connect_account(self, username: str, password: str) -> bool:
        """Connect to an existing account.
        
        Args:
            username: The username of the account to connect
            password: The password for the account
            
        Returns:
            bool: True if connection was successful, False otherwise
        """
        try:
            # Check if this is the main account
            is_main = (
                self.config["main_account"] and 
                username == self.config["main_account"]["username"]
            )
            
            # If it's the main account and already connected, do nothing
            if is_main and self.main_client and self.main_client.username == username:
                return True
                
            # If it's an alt account and already connected, do nothing
            if not is_main and any(client is not None and client.username == username for client in self.alt_clients):
                return True
                
            # Connect to the account
            if is_main:
                # Connect as main account
                self._login_selected_main(username)
            else:
                # Find the account in alt_accounts
                account = next(
                    (acc for acc in self.config["alt_accounts"] if acc["username"] == username),
                    None
                )
                if not account:
                    raise ValueError(f"Account {username} not found in config")
                    
                # Connect as alt account
                client = self._login(account["username"], account["password"])
                self.alt_clients.append(client)
                
                # After connecting an alt account, cache its posts and signal the app
                # to update repost statuses for currently displayed media
                if client:
                    # Cache alt posts in background
                    threading.Thread(
                        target=self._cache_alt_posts,
                        args=(client,),
                        daemon=True
                    ).start()
                    
                    # Signal repost status update (will be used by the main app)
                    self.repost_status_changed = True
                
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect account {username}: {str(e)}")
            return False
            
    def update_repost_status_for_displayed_media(self, media_list):
        """Update repost status for all currently displayed media.
        
        Args:
            media_list: List of media objects currently displayed
            
        Returns:
            dict: Dictionary mapping media PK to list of accounts it's reposted to
        """
        result = {}
        
        for media in media_list:
            try:
                # Get the PK of the media
                media_pk = getattr(media, "pk", None)
                if not media_pk:
                    continue
                    
                # Check repost status
                reposted_to = self.check_repost_status(media)
                result[media_pk] = reposted_to
            except Exception as e:
                # Log the error and continue with next media
                logger.error(f"Error checking repost status for media {getattr(media, 'pk', 'unknown')}: {str(e)}")
                # Add empty list as fallback
                result[getattr(media, "pk", "unknown")] = []
            
        return result

    def disconnect_account(self, username: str) -> bool:
        """Disconnect an account.
        
        Args:
            username: The username of the account to disconnect
            
        Returns:
            bool: True if disconnection was successful, False otherwise
        """
        try:
            # Check if this is the main account
            is_main = (
                self.config["main_account"] and 
                username == self.config["main_account"]["username"]
            )
            
            if is_main:
                # Disconnect main account
                self.main_client = None
            else:
                # Find and remove from alt_clients
                self.alt_clients = [
                    client for client in self.alt_clients 
                    if client.username != username
                ]
                
            return True
            
        except Exception as e:
            logger.error(f"Failed to disconnect account {username}: {str(e)}")
            return False

    def remove_account(self, username: str) -> bool:
        """Remove an account from the config and delete all associated data."""
        try:
            # If this is the main account, unset it first
            if self.config["main_account"] and username == self.config["main_account"]["username"]:
                logger.info(f"Unsetting {username} as main account before removal")
                self.config["main_account"] = None
                
                # Reset clients
                self.main_client = None
                self.alt_clients = []
                
                # Look for the account in alt_accounts
                found = False
                for i, acc in enumerate(self.config["alt_accounts"]):
                    if acc["username"] == username:
                        found = True
                        break
                
                # If not in alt_accounts, we're done
                if not found:
                    # Delete associated data before saving config
                    self._delete_account_data(username)
                    
                    # Save config and return
                    self._save_config()
                    logger.info(f"Successfully removed main account {username}")
                    return True
            
            # Find and remove from alt accounts
            original_length = len(self.config["alt_accounts"])
            self.config["alt_accounts"] = [
                acc for acc in self.config["alt_accounts"] 
                if acc["username"] != username
            ]
            
            # Check if any account was actually removed
            if len(self.config["alt_accounts"]) == original_length:
                logger.warning(f"Account {username} not found in alt accounts")
                
            # Delete all associated data
            self._delete_account_data(username)
            
            # Save config
            self._save_config()
            
            # If this was the current main account, reset clients
            if self.main_client and self.main_client.username == username:
                self.main_client = None
                self.alt_clients = []
            
            logger.info(f"Successfully removed account {username}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to remove account {username}: {str(e)}")
            return False
            
    def _delete_account_data(self, username: str) -> None:
        """Delete all data associated with an account."""
        try:
            # 1. Delete session file
            session_file = f"sessions/{username}.json"
            if os.path.exists(session_file):
                os.remove(session_file)
                logger.info(f"Deleted session file for {username}")
                
            # Check for backup session files
            backup_file = f"sessions/{username}.json.backup"
            if os.path.exists(backup_file):
                os.remove(backup_file)
                logger.info(f"Deleted backup session file for {username}")
                
            # 2. Delete media cache
            media_cache = f"thumbnails/media_cache_{username}.json"
            if os.path.exists(media_cache):
                os.remove(media_cache)
                logger.info(f"Deleted media cache for {username}")
                
            # 3. Delete any thumbnail files associated with this account
            if os.path.exists("thumbnails"):
                # Thumbnails might include the username and media ID
                deleted_count = 0
                for filename in os.listdir("thumbnails"):
                    # Look for patterns like username_12345.jpg or similar
                    if username in filename and (filename.endswith('.jpg') or filename.endswith('.mp4') or filename.endswith('.png')):
                        try:
                            os.remove(os.path.join("thumbnails", filename))
                            deleted_count += 1
                        except:
                            pass
                            
                if deleted_count > 0:
                    logger.info(f"Deleted {deleted_count} thumbnails associated with {username}")
                
            # 4. Delete any pending challenge files
            challenge_file = f"sessions/{username}_challenge.json"
            if os.path.exists(challenge_file):
                os.remove(challenge_file)
                logger.info(f"Deleted challenge file for {username}")
                
            # 5. Delete any other account-specific files that might exist
            # Delete any files in the temporary directory that might include this username
            temp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "temp")
            if os.path.exists(temp_dir):
                deleted_count = 0
                for filename in os.listdir(temp_dir):
                    if username in filename:
                        try:
                            os.remove(os.path.join(temp_dir, filename))
                            deleted_count += 1
                        except:
                            pass
                            
                if deleted_count > 0:
                    logger.info(f"Deleted {deleted_count} temporary files associated with {username}")
            
            logger.info(f"Successfully deleted all data associated with {username}")
        except Exception as e:
            logger.error(f"Error while deleting account data for {username}: {str(e)}")
            # Continue with removal even if data deletion fails

    def set_main_account(self, username: str, password: str = None) -> bool:
        """Set or update the main account."""
        try:
            if not password:
                # If no password provided, find it in alt accounts
                account = next(
                    (acc for acc in self.config["alt_accounts"] 
                     if acc["username"] == username),
                    None
                )
                if not account:
                    raise ValueError(f"Account {username} not found")
                password = account["password"]
            
            # First verify we can login with these credentials
            try:
                # Create a verification handler function for login verification
                def verification_handler(username, choice_type, client):
                    # Use the same verification handler as the main class
                    return self.verification_handler(username, choice_type, client)
                
                # Create test client with the verification handler
                test_client = InstagramClient(username=username, verification_handler=verification_handler)
                test_client.login(password)
            except Exception as e:
                error_msg = str(e)
                # Check for IP blacklist error
                if "change your IP address" in error_msg and "blacklist" in error_msg:
                    logger.error(f"Failed to set main account {username}: IP address is blacklisted by Instagram")
                    raise IPBlacklistError("Your IP address has been temporarily blacklisted by Instagram. " +
                                          "Please use a VPN to change your IP address and try again.")
                else:
                    logger.error(f"Failed to set main account {username}: {error_msg}")
                    raise
            
            # Update main account
            old_main = self.config["main_account"].copy() if self.config["main_account"] else None
            self.config["main_account"] = {
                "username": username,
                "password": password
            }
            
            # If old main account exists and isn't in alt accounts, add it there
            if old_main and old_main["username"] != username:
                exists_in_alt = any(
                    acc["username"] == old_main["username"] 
                    for acc in self.config["alt_accounts"]
                )
                if not exists_in_alt:
                    self.config["alt_accounts"].append(old_main)
            
            # Remove the new main account from alt accounts if it was there
            self.config["alt_accounts"] = [
                acc for acc in self.config["alt_accounts"]
                if acc["username"] != username
            ]
            
            # Save config
            self._save_config()
            
            # Set up the main client
            self.main_client = self._login_selected_main(username)
            if not self.main_client:
                logger.error(f"Failed to log in as {username} after setting as main account")
                return False
                
            # Initialize alt accounts
            self.initialize_alt_accounts(username)
            
            logger.info(f"Successfully set {username} as main account")
            return True
            
        except IPBlacklistError as e:
            # Re-raise the specific error so it can be handled at UI level
            raise
        except Exception as e:
            logger.error(f"Failed to set main account {username}: {str(e)}")
            return False

    def reconnect_client(self, client):
        """Attempt to reconnect a client if its session has become invalid."""
        try:
            if not client or not client.username:
                logger.warning("Cannot reconnect client with no username")
                return False
                
            username = client.username
            logger.info(f"Attempting to reconnect {username}")
            
            # Find account credentials
            account = None
            if self.config["main_account"] and self.config["main_account"]["username"] == username:
                account = self.config["main_account"]
            else:
                account = next(
                    (acc for acc in self.config["alt_accounts"] if acc["username"] == username),
                    None
                )
                
            if not account:
                logger.warning(f"Cannot reconnect {username}: account not found in config")
                return False
                
            # Try to login again
            try:
                # Create verification handler
                def verification_handler(username, choice_type, client):
                    if not self.parent:
                        raise Exception("Verification required but no UI parent available")
                        
                    # Map Instagram's choice types to user-friendly names
                    choice_map = {
                        "email": "EMAIL",
                        "sms": "SMS",
                        "otp": "Authenticator App",
                        "choice": "EMAIL"  # Default to email for choice challenge
                    }
                    # Convert choice_type to string before using lower()
                    choice_str = str(choice_type).lower()
                    challenge_type = choice_map.get(choice_str, str(choice_type))
                    
                    # Show verification dialog
                    from components.verification_dialog import VerificationDialog
                    code = VerificationDialog.show_dialog(self.parent, username, challenge_type)
                    if not code:
                        raise Exception("Verification cancelled by user")
                    client.set_verification_code(code)
                
                # Create new client
                new_client = InstagramClient(username=username, verification_handler=verification_handler)
                
                # Try to login
                new_client.login(account["password"])
                
                # Save session for future use
                new_client.save_session()
                logger.info(f"Successfully reconnected {username}")
                
                # Replace the old client with the new one
                if self.main_client and self.main_client.username == username:
                    self.main_client = new_client
                else:
                    # Find and replace in alt_clients
                    for i, alt_client in enumerate(self.alt_clients):
                        if alt_client.username == username:
                            self.alt_clients[i] = new_client
                            break
                
                return True
                
            except Exception as e:
                logger.error(f"Failed to reconnect {username}: {str(e)}")
                return False
                
        except Exception as e:
            logger.error(f"Error in reconnect_client: {str(e)}")
            return False

    def verification_handler(self, username, choice_type, client):
        """Handler for Instagram verification challenges (2FA).
        
        Args:
            username: The Instagram username being verified
            choice_type: The type of verification challenge (email, sms, etc.)
            client: The Instagram client instance
            
        Returns:
            None
        """
        # Map Instagram's choice types to user-friendly names
        choice_map = {
            "email": "EMAIL",
            "sms": "SMS",
            "otp": "Authenticator App",
            "choice": "EMAIL"  # Default to email for choice challenge
        }
        # Convert choice_type to string before using lower()
        choice_str = str(choice_type).lower()
        challenge_type = choice_map.get(choice_str, str(choice_type))
        
        logger.info(f"Handling verification challenge for {username}: {challenge_type}")
        
        # Show verification dialog
        if self.parent:
            try:
                # Import here to avoid circular imports
                from components.verification_dialog import VerificationDialog
                code = VerificationDialog.show_dialog(self.parent, username, challenge_type)
                if not code:
                    logger.warning(f"Verification cancelled by user for {username}")
                    raise Exception("Verification cancelled by user")
                
                # Set the verification code in the client
                client.set_verification_code(code)
                logger.info(f"Verification code submitted for {username}")
            except Exception as e:
                logger.error(f"Error in verification process for {username}: {str(e)}")
                raise
        else:
            # If no parent window is available, just log an error
            logger.error(f"Verification required for {username} but no parent window to show dialog")
            raise Exception("Verification required but cannot show dialog")

    def _shortcode_to_media_id(self, shortcode):
        """
        Convert an Instagram shortcode to a media ID.
        This is a custom implementation since the native method is failing.
        
        Args:
            shortcode: Instagram media shortcode
            
        Returns:
            media_id if successful, None otherwise
        """
        try:
            # First try: direct search by username
            if self.main_client and hasattr(self.main_client, 'username'):
                username = self.main_client.username
                logger.info(f"Trying to find media by username: {username}")
                
                # Get user ID
                user_id = self.main_client.user_id
                
                # Get recent media from user feed
                try:
                    # Try private API first (more reliable)
                    media_list = self.main_client.user_medias(user_id, amount=50)
                except Exception as e:
                    logger.warning(f"Error fetching user media: {str(e)}")
                    media_list = []
                
                # Check each media
                for media in media_list:
                    if hasattr(media, 'code') and media.code == shortcode:
                        logger.info(f"Found matching media: {media.pk}")
                        return media.pk
            
            # Second try: more general search
            # Let's parse the shortcode using the algorithm Instagram uses (base64 encoding with their custom alphabet)
            alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_'
            media_id = 0
            for char in shortcode:
                media_id = media_id * 64 + alphabet.find(char)
            
            # For newer posts, we need to add a user ID
            # This is just a best-effort approach and may not work for all posts
            if media_id:
                logger.info(f"Generated potential media ID from shortcode: {media_id}")
                return str(media_id)
                
            # If all else fails
            return None
            
        except Exception as e:
            logger.error(f"Error converting shortcode to media ID: {str(e)}")
            return None

    def fetch_content_by_url(self, url: str) -> Dict:
        """
        Fetch Instagram content by URL.
        
        Args:
            url: The Instagram URL (post, reel, story, etc.)
            
        Returns:
            Dictionary with content details
        """
        try:
            # Extract media identifier from URL
            import re
            
            # Remove any @ from the beginning of the URL if present
            if url.startswith('@'):
                url = url[1:]
                
            # Match different Instagram URL patterns
            match = re.search(r'instagram.com/(?:p|reel|stories|tv)/([^/?]+)', url)
            
            if not match:
                raise ValueError("Invalid Instagram URL. Please use a direct link to a post, reel, or story")
                
            shortcode = match.group(1)
            logger.info(f"Extracting content from shortcode: {shortcode}")
            
            # Check if it's a post/reel URL
            if '/p/' in url or '/reel/' in url:
                # First try to get media from user's posts
                # Convert shortcode to media_id
                media_id = self._shortcode_to_media_id(shortcode)
                
                if media_id:
                    try:
                        # Try to get media details
                        media_info = self.main_client.media_info(media_id)
                        
                        # Extract relevant information
                        if hasattr(media_info, 'dict'):
                            media_info = media_info.dict()
                            
                        return {
                            'media_pk': media_id,
                            'shortcode': shortcode,
                            'media_type': media_info.get('media_type', 1) if isinstance(media_info, dict) else getattr(media_info, 'media_type', 1),
                            'caption': media_info.get('caption_text', '') if isinstance(media_info, dict) else getattr(media_info, 'caption_text', ''),
                            'thumbnail_url': media_info.get('thumbnail_url') if isinstance(media_info, dict) else getattr(media_info, 'thumbnail_url', None),
                            'duration': media_info.get('video_duration', 0) if isinstance(media_info, dict) else getattr(media_info, 'video_duration', 0),
                            'username': media_info.get('user', {}).get('username', 'unknown') if isinstance(media_info, dict) else (getattr(media_info, 'user').username if hasattr(media_info, 'user') else 'unknown'),
                            'url': url
                        }
                    except Exception as e:
                        logger.warning(f"Error getting media details: {str(e)}")
                        
                # If we couldn't get the media directly, create a fallback info object
                return {
                    'media_pk': None,
                    'shortcode': shortcode,
                    'media_type': 1,  # Assume photo
                    'caption': '',
                    'thumbnail_url': None,
                    'duration': 0,
                    'username': 'unknown',
                    'url': url,
                    'error': 'Could not find media details for this post. You might not have permission to view it, or the post may be private or unavailable.'
                }
                
            # Handle stories - different API endpoint
            elif '/stories/' in url:
                # Stories require different handling
                raise NotImplementedError("Story downloads are not implemented yet")
                
            else:
                raise ValueError("Unsupported content type. Please use a direct link to a post, reel, or story")
                
        except Exception as e:
            logger.error(f"Error fetching content by URL: {str(e)}")
            raise

    def download_content_by_url(self, url: str, target_path: str = None) -> Dict:
        """
        Download Instagram content by URL.
        
        Args:
            url: The Instagram URL
            target_path: Optional target path; if None, a local Downloads folder will be used.
                         If provided, can be a full file path or just a directory.
            
        Returns:
            Dictionary with download details
        """
        try:
            # First fetch the content info
            content_info = self.fetch_content_by_url(url)
            media_pk = content_info.get('media_pk')
            shortcode = content_info.get('shortcode', '')
            
            # If we don't have a media_pk, we need to try another approach
            if media_pk is None:
                if not shortcode:
                    raise ValueError("Could not extract media shortcode from URL")
                    
                logger.warning(f"No media_pk found, creating placeholder for shortcode: {shortcode}")
                
                # Create a placeholder file path
                if target_path:
                    # Check if target_path is a directory or a file
                    if os.path.isdir(target_path) or not os.path.splitext(target_path)[1]:
                        # It's a directory or has no extension
                        os.makedirs(target_path, exist_ok=True)
                        output_path = os.path.join(target_path, f"downloaded_instagram_{shortcode}.txt")
                    else:
                        # It's a complete file path
                        os.makedirs(os.path.dirname(target_path), exist_ok=True)
                        output_path = target_path
                else:
                    # Create a path in the local Downloads directory
                    download_dir = os.path.join("Downloads")
                    os.makedirs(download_dir, exist_ok=True)
                    output_path = os.path.join(download_dir, f"downloaded_instagram_{shortcode}.txt")
                
                # Create a descriptive placeholder file
                with open(output_path, "w") as f:
                    f.write(f"Instagram Content: {shortcode}\n\n")
                    f.write(f"URL: {url}\n\n")
                    f.write(f"Error: {content_info.get('error', 'Media could not be downloaded directly')}\n\n")
                    f.write("This content could not be downloaded directly. Possible reasons:\n")
                    f.write("1. The post is from a private account you don't follow\n")
                    f.write("2. The post has been deleted or is no longer available\n")
                    f.write("3. Instagram API limitations prevent direct downloading\n")
                    f.write("4. You don't have permission to view this content\n\n")
                    f.write("Try visiting the URL directly in your browser.")
                    
                logger.warning(f"Created placeholder file at {output_path}")
                
                return {
                    'path': output_path,
                    'content_info': content_info,
                    'success': False,
                    'message': content_info.get('error', 'Media could not be downloaded directly')
                }
            
            # For direct downloads with a valid media_pk
            media_type = content_info.get('media_type', 1)
            username = content_info.get('username', 'instagram_user')
            
            # Handle the download based on whether target_path is a directory or full path
            if target_path:
                # Is it a directory?
                if os.path.isdir(target_path) or not os.path.splitext(target_path)[1]:
                    # Target is a directory - let the API handle the filename
                    os.makedirs(target_path, exist_ok=True)
                    download_dir = target_path
                    filename = None  # Let Instagram API create the filename
                else:
                    # Target is a file path - split into directory and filename
                    download_dir = os.path.dirname(target_path)
                    filename = os.path.basename(target_path)
                    os.makedirs(download_dir, exist_ok=True)
            else:
                # No target provided - use local Downloads folder
                download_dir = os.path.join("Downloads")
                os.makedirs(download_dir, exist_ok=True)
                filename = None  # Let Instagram API create the filename
            
            logger.info(f"Downloading media to directory: {download_dir}")
            
            # Determine naming format - for user downloads, use a more descriptive name
            # Include the username and timestamp for organization and to avoid overwriting
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            is_user_download = not target_path or os.path.normpath(download_dir) == os.path.normpath("Downloads")
            
            # Add prefix to downloaded files to distinguish them from temporary files
            download_prefix = "downloaded_" if is_user_download else ""
            
            # Let's download the media based on type
            try:
                if media_type == 1:  # Photo
                    if filename:
                        # Use the specified filename
                        output_path = os.path.join(download_dir, filename)
                        self.main_client.photo_download(media_pk, output_path)
                    else:
                        # If it's a user download, use a more descriptive name
                        if is_user_download:
                            custom_filename = f"{download_prefix}{username}_{shortcode}_{timestamp}.jpg"
                            output_path = os.path.join(download_dir, custom_filename)
                            self.main_client.photo_download(media_pk, output_path)
                        else:
                            # Let the API handle the filename for temporary downloads
                            output_path = self.main_client.photo_download(media_pk, folder=download_dir)
                
                elif media_type == 2:  # Video
                    if filename:
                        # Use the specified filename
                        output_path = os.path.join(download_dir, filename)
                        self.main_client.video_download(media_pk, output_path)
                    else:
                        # If it's a user download, use a more descriptive name with fixed path handling
                        if is_user_download:
                            custom_filename = f"{download_prefix}{username}_{shortcode}_{timestamp}.mp4"
                            output_path = os.path.join(download_dir, custom_filename)
                            
                            # Create a temporary path to handle the instagrapi bug where it appends a filename to the path
                            # Instead of passing the full path which causes issues, we'll cd to the directory and use just the filename
                            try:
                                # First save the current directory
                                current_dir = os.getcwd()
                                # Change to the download directory
                                os.chdir(download_dir)
                                # Download using only the filename
                                final_path = self.main_client.video_download(media_pk, custom_filename)
                                # Restore the original directory
                                os.chdir(current_dir)
                                # Update the output path to the full path
                                output_path = os.path.join(download_dir, os.path.basename(final_path))
                            except Exception as e:
                                # If the workaround fails, try the original method with folder parameter
                                logger.warning(f"Custom path download failed, falling back to folder method: {str(e)}")
                                os.chdir(current_dir) if 'current_dir' in locals() else None
                                output_path = self.main_client.video_download(media_pk, folder=download_dir)
                        else:
                            # Let the API handle the filename for temporary downloads
                            output_path = self.main_client.video_download(media_pk, folder=download_dir)
                
                elif media_type == 8:  # Album
                    album_items = self.main_client.media_info(media_pk).get('resources', [])
                    if album_items:
                        first_item = album_items[0]
                        first_item_pk = first_item['pk']
                        first_item_type = first_item.get('media_type', 1)
                        
                        if first_item_type == 1:  # Photo
                            if filename:
                                output_path = os.path.join(download_dir, filename)
                                self.main_client.photo_download(first_item_pk, output_path)
                            else:
                                # If it's a user download, use a more descriptive name
                                if is_user_download:
                                    custom_filename = f"{download_prefix}{username}_{shortcode}_album_{timestamp}.jpg"
                                    output_path = os.path.join(download_dir, custom_filename)
                                    self.main_client.photo_download(first_item_pk, output_path)
                                else:
                                    output_path = self.main_client.photo_download(first_item_pk, folder=download_dir)
                        elif first_item_type == 2:  # Video
                            if filename:
                                output_path = os.path.join(download_dir, filename)
                                self.main_client.video_download(first_item_pk, output_path)
                            else:
                                # If it's a user download, use a more descriptive name with fixed path handling
                                if is_user_download:
                                    custom_filename = f"{download_prefix}{username}_{shortcode}_album_{timestamp}.mp4"
                                    
                                    # Use the same workaround for album videos
                                    try:
                                        # First save the current directory
                                        current_dir = os.getcwd()
                                        # Change to the download directory
                                        os.chdir(download_dir)
                                        # Download using only the filename
                                        final_path = self.main_client.video_download(first_item_pk, custom_filename)
                                        # Restore the original directory
                                        os.chdir(current_dir)
                                        # Update the output path to the full path
                                        output_path = os.path.join(download_dir, os.path.basename(final_path))
                                    except Exception as e:
                                        # If the workaround fails, try the original method with folder parameter
                                        logger.warning(f"Custom path download failed, falling back to folder method: {str(e)}")
                                        os.chdir(current_dir) if 'current_dir' in locals() else None
                                        output_path = self.main_client.video_download(first_item_pk, folder=download_dir)
                                else:
                                    output_path = self.main_client.video_download(first_item_pk, folder=download_dir)
                    else:
                        raise ValueError("Album has no items")
                else:
                    raise ValueError(f"Unsupported media type: {media_type}")
                
                # If we get here, the download was successful
                logger.info(f"Successfully downloaded media to {output_path}")
                
                # Return download info
                return {
                    'path': output_path,
                    'content_info': content_info,
                    'success': True
                }
                
            except Exception as download_error:
                # Handle download failure
                logger.error(f"Download failed: {str(download_error)}")
                
                # Create a placeholder error file
                error_path = os.path.join(download_dir, f"error_{shortcode}_{timestamp}.txt")
                with open(error_path, "w") as f:
                    f.write(f"Failed to download Instagram content: {shortcode}\n\n")
                    f.write(f"URL: {url}\n\n")
                    f.write(f"Error: {str(download_error)}\n\n")
                    f.write("This content could not be downloaded. Please try again later.")
                
                # Return error info
                return {
                    'path': error_path,
                    'content_info': content_info,
                    'success': False,
                    'message': str(download_error)
                }
            
        except Exception as e:
            logger.error(f"Error downloading content by URL: {str(e)}")
            raise

    def repost_content_by_url(self, url: str, caption: str = None, remove_watermark: bool = False, add_watermark: bool = False, credit_original: bool = True) -> Dict:
        """
        Download and repost Instagram content by URL.
        
        Args:
            url: The Instagram URL
            caption: Optional caption to use (if None, original caption is used)
            remove_watermark: Whether to attempt to remove original watermarks
            add_watermark: Whether to add your own watermark
            credit_original: Whether to credit the original creator
            
        Returns:
            Dictionary with repost details
        """
        try:
            # First download the content
            download_result = self.download_content_by_url(url)
            
            # Check if download was successful
            if not download_result.get('success', True):
                message = download_result.get('message', 'Unknown error')
                logger.warning(f"Download not fully successful: {message}")
                
                # Return informative error
                return {
                    'success': False,
                    'message': f"Could not download content: {message}",
                    'shortcode': download_result.get('content_info', {}).get('shortcode')
                }
            
            # Get content info
            content_info = download_result['content_info']
            media_path = download_result['path']
            
            # Prepare caption
            final_caption = caption or content_info.get('caption', '')
            
            # Create the upload dict
            media_data = {
                'path': media_path,
                'caption': final_caption
            }
            
            # Upload the media
            self.repost_media(media_data)
            
            # Clean up
            self.cleanup(media_path)
            
            return {
                'success': True,
                'media_pk': content_info.get('media_pk'),
                'shortcode': content_info.get('shortcode')
            }
            
        except Exception as e:
            logger.error(f"Error reposting content by URL: {str(e)}")
            raise

    def repost_media(self, media_data: Dict) -> None:
        """
        Repost media to Instagram.
        
        Args:
            media_data: Dictionary with 'path' and 'caption' keys
        """
        try:
            # Ensure we have the necessary data
            if 'path' not in media_data:
                raise ValueError("Media path not provided")
                
            path = media_data['path']
            caption = media_data.get('caption', '')
            
            # Check if this is a downloaded file (either in Downloads directory or has downloaded_ prefix)
            filename = os.path.basename(path)
            is_downloaded_file = (os.path.normpath(os.path.dirname(path)) == os.path.normpath("Downloads") or 
                                 filename.startswith("downloaded_"))
            
            # Create a temporary copy to avoid deleting the original file if it's a user download
            if os.path.exists(path) and is_downloaded_file:
                # This is a downloaded file, create a temp copy for posting
                import shutil
                temp_dir = "temp"
                os.makedirs(temp_dir, exist_ok=True)
                
                # Generate a name for the temp file - ensure it doesn't start with downloaded_
                # to differentiate it from user downloads
                base_filename = filename
                if base_filename.startswith("downloaded_"):
                    base_filename = base_filename[len("downloaded_"):]
                
                temp_filename = f"temp_post_{base_filename}"
                temp_path = os.path.join(temp_dir, temp_filename)
                
                # Copy the file
                shutil.copy2(path, temp_path)
                logger.info(f"Created temporary copy for posting: {temp_path}")
                
                # Use the temp path for posting
                post_path = temp_path
            else:
                # Use the original path
                post_path = path
            
            # Log the path to identify any issues
            logger.info(f"Reposting media from path: {post_path}")
            
            # Check file exists
            if not os.path.exists(post_path):
                raise FileNotFoundError(f"Media file not found: {post_path}")
                
            # Check file extension to determine media type
            extension = os.path.splitext(post_path)[1].lower()
            
            # 1. Post the media
            if extension in ['.jpg', '.jpeg', '.png']:
                # Photo
                logger.info("Reposting as photo...")
                self.main_client.photo_upload(post_path, caption)
                
            elif extension in ['.mp4', '.mov']:
                # Video
                logger.info("Reposting as video...")
                self.main_client.video_upload(post_path, caption)
                
            else:
                raise ValueError(f"Unsupported file extension: {extension}")
                
            logger.info("Media reposted successfully")
            
            # Clean up temp files, but not downloaded files
            # Check both directory and filename prefix to ensure downloads are preserved
            filename = os.path.basename(post_path)
            is_temp_file = (os.path.normpath(os.path.dirname(post_path)) == os.path.normpath("temp") and
                          not filename.startswith("downloaded_"))
            
            if is_temp_file:
                # Only clean up temp files, not downloaded files
                self.cleanup(post_path)
                
        except Exception as e:
            logger.error(f"Failed to repost media: {str(e)}")
            # Clean up temp files even if there's an error
            if 'post_path' in locals():
                filename = os.path.basename(post_path)
                is_temp_file = (os.path.normpath(os.path.dirname(post_path)) == os.path.normpath("temp") and
                            not filename.startswith("downloaded_"))
                if is_temp_file:
                    self.cleanup(post_path)
            raise

class MediaWrapper:
    """Wrapper class for Media objects to add additional attributes."""
    def __init__(self, media):
        self._media = media
        self.reposted_to = []
        
    def __getattr__(self, name):
        """Delegate attribute access to wrapped media object."""
        return getattr(self._media, name)

    def download_media(self, media_pk: int) -> Dict:
        """Download media and its metadata from main account."""
        try:
            media_info = self.main_client.media_info(media_pk)
            media_type = media_info.media_type
            
            if media_type == 2:  # Video
                path = self.main_client.video_download(media_pk)
                view_count = (
                    getattr(media_info, 'view_count', None) or
                    getattr(media_info, 'play_count', None) or
                    getattr(media_info, 'video_view_count', None) or
                    0
                )
            else:
                path = self.main_client.photo_download(media_pk)
                view_count = 0
            
            return {
                "path": path,
                "caption": media_info.caption_text,
                "media_type": media_type,
                "usertags": media_info.usertags,
                "location": media_info.location,
                "view_count": view_count
            }
        except Exception as e:
            logger.error(f"Failed to download media {media_pk}: {str(e)}")
            raise

    def repost_media(self, media_data: Dict) -> None:
        """Repost media to all alt accounts."""
        for client in self.alt_clients:
            try:
                if media_data["media_type"] == 2:  # Video
                    client.video_upload(
                        path=media_data["path"],
                        caption=media_data["caption"],
                        usertags=media_data["usertags"],
                        location=media_data["location"]
                    )
                else:  # Photo
                    client.photo_upload(
                        path=media_data["path"],
                        caption=media_data["caption"],
                        usertags=media_data["usertags"],
                        location=media_data["location"]
                    )
                logger.info(f"Successfully reposted to {client.username}")
            except Exception as e:
                logger.error(f"Failed to repost to {client.username}: {str(e)}")

    def cleanup(self, path: str) -> None:
        """Clean up downloaded media files."""
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception as e:
            logger.error(f"Failed to cleanup file {path}: {str(e)}")

    def add_account(self, username: str, password: str) -> bool:
        """Add a new account to the config."""
        try:
            # First verify we can login with these credentials
            test_client = InstagramClient(username=username)
            test_client.login(password)
            
            # Add to config
            if self.config["main_account"] and username == self.config["main_account"]["username"]:
                raise ValueError("Account already exists as main account")
            
            for account in self.config["alt_accounts"]:
                if account["username"] == username:
                    raise ValueError("Account already exists as alt account")
            
            self.config["alt_accounts"].append({
                "username": username,
                "password": password
            })
            
            # Save config
            self._save_config()
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to add account {username}: {str(e)}")
            raise

    def remove_account(self, username: str) -> bool:
        """Remove an account from the config."""
        try:
            # Just delegate to the reposter's implementation since MediaWrapper wraps methods
            # We'll use the reposter class to ensure consistent behavior
            from instagram_utils import InstagramReposter
            reposter = InstagramReposter()
            return reposter.remove_account(username)
            
        except Exception as e:
            logger.error(f"Failed to remove account {username}: {str(e)}")
            return False

    def set_main_account(self, username: str, password: str = None) -> bool:
        """Set or update the main account."""
        try:
            if not password:
                # If no password provided, find it in alt accounts
                account = next(
                    (acc for acc in self.config["alt_accounts"] 
                     if acc["username"] == username),
                    None
                )
                if not account:
                    raise ValueError(f"Account {username} not found")
                password = account["password"]
            
            # First verify we can login with these credentials
            try:
                # Create a verification handler function for login verification
                def verification_handler(username, choice_type, client):
                    # Use the same verification handler as the main class
                    return self.verification_handler(username, choice_type, client)
                
                # Create test client with the verification handler
                test_client = InstagramClient(username=username, verification_handler=verification_handler)
                test_client.login(password)
            except Exception as e:
                error_msg = str(e)
                # Check for IP blacklist error
                if "change your IP address" in error_msg and "blacklist" in error_msg:
                    logger.error(f"Failed to set main account {username}: IP address is blacklisted by Instagram")
                    raise IPBlacklistError("Your IP address has been temporarily blacklisted by Instagram. " +
                                          "Please use a VPN to change your IP address and try again.")
                else:
                    logger.error(f"Failed to set main account {username}: {error_msg}")
                    raise
            
            # Update main account
            old_main = self.config["main_account"].copy() if self.config["main_account"] else None
            self.config["main_account"] = {
                "username": username,
                "password": password
            }
            
            # If old main account exists and isn't in alt accounts, add it there
            if old_main and old_main["username"] != username:
                exists_in_alt = any(
                    acc["username"] == old_main["username"] 
                    for acc in self.config["alt_accounts"]
                )
                if not exists_in_alt:
                    self.config["alt_accounts"].append(old_main)
            
            # Remove the new main account from alt accounts if it was there
            self.config["alt_accounts"] = [
                acc for acc in self.config["alt_accounts"]
                if acc["username"] != username
            ]
            
            # Save config
            self._save_config()
            
            # Switch to the new main account
            self._login_selected_main(username)
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to set main account {username}: {str(e)}")
            raise 

def show_verification_dialog(username: str, choice_type: str, client: Any, parent: Any = None) -> None:
    """
    Show a verification dialog to the user and handle the verification process.
    
    Args:
        username: The Instagram username being verified
        choice_type: The type of verification (email, sms, etc.)
        client: The Instagram client instance
        parent: The parent UI widget for the dialog
    """
    if not parent:
        raise Exception("Verification required but no UI parent available")
        
    # Map Instagram's choice types to user-friendly names
    choice_map = {
        "email": "EMAIL",
        "sms": "SMS",
        "otp": "Authenticator App",
        "choice": "EMAIL"  # Default to email for choice challenge
    }
    
    # Convert choice_type to string before using lower()
    choice_str = str(choice_type).lower()
    challenge_type = choice_map.get(choice_str, str(choice_type))
    
    # Import locally to avoid circular imports
    from components.verification_dialog import VerificationDialog
    
    # Show verification dialog
    code = VerificationDialog.show_dialog(parent, username, challenge_type)
    if not code:
        raise Exception("Verification cancelled by user")
    
    # Set the verification code in the client
    client.set_verification_code(code)

def encrypt_existing_sessions():
    """
    Utility function to encrypt all existing session files.
    Returns the count of encrypted files.
    """
    try:
        if not os.path.exists("sessions"):
            logger.info("No sessions directory found, creating one")
            os.makedirs("sessions")
            return 0
            
        # Initialize password manager
        password_manager = PasswordManager()
        
        # Get all JSON files in the sessions directory
        session_files = [f for f in os.listdir("sessions") if f.endswith(".json")]
        
        encrypted_count = 0
        for filename in session_files:
            file_path = os.path.join("sessions", filename)
            username = os.path.splitext(filename)[0]
            
            try:
                # Read the file
                with open(file_path, "r") as f:
                    file_data = json.load(f)
                
                # Skip already encrypted files
                if "encrypted_data" in file_data and "encryption_version" in file_data:
                    logger.info(f"Session file for {username} is already encrypted")
                    continue
                    
                # Convert to JSON string
                json_str = json.dumps(file_data, cls=DateTimeEncoder)
                
                # Encrypt the data
                encrypted_data = password_manager.encrypt_password(json_str)
                
                # Create encrypted file structure
                encrypted_file = {
                    "encrypted_data": encrypted_data,
                    "encryption_version": 1
                }
                
                # Create backup of original file
                backup_path = file_path + ".backup"
                os.rename(file_path, backup_path)
                
                # Write encrypted data to original filename
                with open(file_path, "w") as f:
                    json.dump(encrypted_file, f, indent=2)
                    
                encrypted_count += 1
                logger.info(f"Encrypted session file for {username}")
                
            except Exception as e:
                logger.error(f"Failed to encrypt session file {filename}: {str(e)}")
                # Try to restore from backup if available
                backup_path = file_path + ".backup"
                if os.path.exists(backup_path):
                    os.rename(backup_path, file_path)
        
        logger.info(f"Encrypted {encrypted_count} session files")
        return encrypted_count
        
    except Exception as e:
        logger.error(f"Error encrypting session files: {str(e)}")
        return 0 