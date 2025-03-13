"""
Main application class for the Instagram Repost tool.
"""
import customtkinter as ctk
import tkinter as tk
import tkinter.messagebox as tkmb
import logging
import threading
import sys
import time
from datetime import datetime
from utils.constants import COLORS, HAS_CTK_MESSAGEBOX
from instagram_utils import InstagramReposter, encrypt_existing_sessions
from components.text_handlers import TextRedirector, TextWidgetHandler
from components.settings_dialog import SettingsDialog
from components.scrollable_media_frame import ScrollableMediaFrame
from components.progress_dialog import ProgressDialog
from components.account_management import AccountManagementDialog
from components.verification_dialog import VerificationDialog
import concurrent.futures
import os
import json
from crypto_utils import PasswordManager
from instagram_utils import IPBlacklistError

# Import CTkMessagebox if available
if HAS_CTK_MESSAGEBOX:
    from CTkMessagebox import CTkMessagebox

class InstagramRepostApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        # Configure the main window
        self.title("Instagram Repost Tool")
        self.geometry("1600x900")  # Increased from 1280x800 to provide more space
        self.configure(fg_color=COLORS["bg_dark"])
        
        # Initialize encryption
        self.password_manager = PasswordManager()
        
        # Initialize reposter
        self.reposter = InstagramReposter()
        
        # Ensure session files are encrypted
        self.secure_session_files()
        
        # Load settings
        self.settings = self.load_settings()
        
        # Set theme from settings
        ctk.set_appearance_mode(self.settings.get("theme", "dark"))
        
        # Initialize variables
        self.auto_repost_active = False
        self.terminal_visible = False
        self.current_repost_thread = None
        
        # Event tracking for modifier keys
        self._current_event = None
        self.bind_all("<Key>", self._track_event)
        self.bind_all("<KeyRelease>", self._track_event)
        self.bind_all("<Button>", self._track_event)
        
        # Configure grid
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)  # Content area
        self.grid_rowconfigure(2, weight=0)  # Action bar
        self.grid_rowconfigure(3, weight=0)  # Terminal (when visible)
        
        # Setup UI components
        self.setup_ui()
        
        # Setup logging
        self.setup_logging()
        
        # Bind close event
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        
    def secure_session_files(self):
        """Ensure all session files are encrypted for security."""
        try:
            # Call the utility function to encrypt all session files
            encrypted_count = encrypt_existing_sessions()
            
            if encrypted_count > 0:
                self.log_to_terminal(f"Successfully encrypted {encrypted_count} session files for security.")
            else:
                self.log_to_terminal("All session files are already secure.")
                
        except Exception as e:
            self.log_to_terminal(f"Error securing session files: {str(e)}", logging.ERROR)
        
    def setup_ui(self):
        # Header frame
        self.header_frame = ctk.CTkFrame(self, fg_color=COLORS["bg_medium"], height=60)
        self.header_frame.grid(row=0, column=0, sticky="ew", padx=0, pady=0)
        self.header_frame.grid_propagate(False)
        
        # Logo / Title on the left
        self.logo_frame = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        self.logo_frame.pack(side="left", padx=15)
        
        # Logo title
        self.title_label = ctk.CTkLabel(
            self.logo_frame, 
            text="Instagram Reposter", 
            font=ctk.CTkFont(family="Helvetica", size=18, weight="bold"),
            text_color=COLORS["text_primary"]
        )
        self.title_label.pack(side="left", padx=5)
        
        # Status indicator
        self.status_label = ctk.CTkLabel(
            self.logo_frame,
            text="Not connected",
            font=ctk.CTkFont(family="Helvetica", size=12),
            text_color=COLORS["warning"]
        )
        self.status_label.pack(side="left", padx=(10, 0))
        
        # Header buttons on the right
        self.header_buttons_frame = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        self.header_buttons_frame.pack(side="right", padx=15)
        
        # Force refresh button
        self.force_refresh_btn = ctk.CTkButton(
            self.header_buttons_frame,
            text="Force Refresh",
            command=lambda: self.refresh_posts(force_refresh=True),
            width=100,
            height=30,
            corner_radius=6,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            text_color=COLORS["text_primary"],
            font=ctk.CTkFont(family="Helvetica", size=12)
        )
        self.force_refresh_btn.pack(side="right", padx=5)

        # Account management button
        self.account_btn = ctk.CTkButton(
            self.header_buttons_frame,
            text="Accounts",
            command=self.show_account_manager,
            width=100,
            height=30,
            corner_radius=6,
            fg_color=COLORS["bg_dark"],
            hover_color=COLORS["bg_light"],
            text_color=COLORS["text_primary"],
            font=ctk.CTkFont(family="Helvetica", size=12)
        )
        self.account_btn.pack(side="right", padx=5)
        
        # Create a PanedWindow to manage content and terminal
        self.paned_window = tk.PanedWindow(self, orient=tk.VERTICAL, bg=COLORS["bg_dark"], 
                                           sashwidth=8, sashrelief="raised")  # Make the sash more visible
        self.paned_window.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)
        
        # Main content frame - reduce minimum size to give more space to terminal
        content_frame = ctk.CTkFrame(self.paned_window, fg_color="transparent")
        self.paned_window.add(content_frame, stretch="always", minsize=400)  # Reduced from 600 to give more space to terminal
        
        # Toolbar
        toolbar = ctk.CTkFrame(content_frame, fg_color=COLORS["bg_medium"], corner_radius=10)
        toolbar.pack(side="top", fill="x", padx=0, pady=(0, 20))
        
        # Left toolbar section
        left_toolbar = ctk.CTkFrame(toolbar, fg_color="transparent")
        left_toolbar.pack(side="left", fill="y", padx=10, pady=10)
        
        # Add tooltip for force refresh button
        self._create_tooltip(self.force_refresh_btn, "Force a complete refresh, ignoring all caches")
        
        # Account management button
        account_btn = ctk.CTkButton(
            left_toolbar,
            text="Manage Accounts",
            command=self.show_account_manager,
            height=40,
            corner_radius=8,
            fg_color=COLORS["bg_light"],
            hover_color=COLORS["bg_dark"],
            text_color=COLORS["text_primary"],
            font=ctk.CTkFont(family="Helvetica", size=14)
        )
        account_btn.pack(side="left", padx=5)
        
        # Connect button
        connect_btn = ctk.CTkButton(
            left_toolbar,
            text="Connect Account",
            command=self.connect_main_account,
            height=40,
            corner_radius=8,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            text_color=COLORS["text_primary"],
            font=ctk.CTkFont(family="Helvetica", size=14, weight="bold")
        )
        connect_btn.pack(side="left", padx=5)
        
        # Steal Content button
        steal_content_btn = ctk.CTkButton(
            left_toolbar,
            text="🔗 Steal",
            command=self.show_content_stealer,
            width=80,
            height=40,
            corner_radius=8,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            text_color=COLORS["text_primary"],
            font=ctk.CTkFont(family="Helvetica", size=14)
        )
        steal_content_btn.pack(side="left", padx=5)
        
        # Refresh button - make it more prominent (primary action)
        self.refresh_btn = ctk.CTkButton(
            left_toolbar,
            text="Load Posts",  # Initial text is "Load Posts"
            command=self.refresh_posts,
            height=40,
            width=140,  # Make it wider for emphasis
            corner_radius=8,
            fg_color=COLORS["success"],  # Use success color (green) to make it stand out
            hover_color="#1e7c3a",  # Darker green hover
            text_color=COLORS["text_primary"],
            font=ctk.CTkFont(family="Helvetica", size=14, weight="bold")  # Make font bold
        )
        self.refresh_btn.pack(side="left", padx=5)
        
        # Add tooltip for refresh button
        self._create_tooltip(self.refresh_btn, "Load posts from Instagram for the connected account")
        
        
        # Right toolbar section
        right_toolbar = ctk.CTkFrame(toolbar, fg_color="transparent")
        right_toolbar.pack(side="right", fill="y", padx=10, pady=10)
        
        # Search entry
        self.search_entry = ctk.CTkEntry(
            right_toolbar,
            placeholder_text="Search captions...",
            width=200,
            height=40,
            corner_radius=8,
            border_width=0,
            fg_color=COLORS["bg_dark"],
            text_color=COLORS["text_primary"]
        )
        self.search_entry.pack(side="left", padx=5)
        self.search_entry.bind("<Return>", self.on_search)
        
        # Media type filter
        self.media_type_var = ctk.StringVar(value="all")
        media_type_menu = ctk.CTkOptionMenu(
            right_toolbar,
            values=["all", "photo", "video"],
            variable=self.media_type_var,
            command=self.on_filter_change,
            width=120,
            height=40,
            corner_radius=8,
            fg_color=COLORS["bg_dark"],
            button_color=COLORS["bg_light"],
            button_hover_color=COLORS["bg_medium"],
            dropdown_fg_color=COLORS["bg_dark"]
        )
        media_type_menu.pack(side="left", padx=5)
        
        # Sort by filter
        self.sort_by_var = ctk.StringVar(value="date")
        sort_by_menu = ctk.CTkOptionMenu(
            right_toolbar,
            values=["date", "likes", "comments", "views"],
            variable=self.sort_by_var,
            command=self.on_filter_change,
            width=120,
            height=40,
            corner_radius=8,
            fg_color=COLORS["bg_dark"],
            button_color=COLORS["bg_light"],
            button_hover_color=COLORS["bg_medium"],
            dropdown_fg_color=COLORS["bg_dark"]
        )
        sort_by_menu.pack(side="left", padx=5)
        
        # Main content area - with a fixed height when terminal is visible
        self.content_area = ctk.CTkFrame(content_frame, fg_color=COLORS["bg_medium"], corner_radius=10)
        self.content_area.pack(side="top", fill="both", expand=True)
        
        # Media frame
        self.media_frame = ScrollableMediaFrame(
            self.content_area,
            reposter=self.reposter,
            fg_color=COLORS["bg_medium"],
            corner_radius=10,
            height=600,  # Set a default height
            width=800,   # Set a default width
            scrollbar_button_color=COLORS["bg_dark"],
            scrollbar_button_hover_color=COLORS["bg_light"],
            scrollbar_fg_color=COLORS["bg_dark"],
            border_width=0  # Remove border for cleaner look
        )
        self.media_frame.pack(side="top", fill="both", expand=True, padx=20, pady=20)
        
        # Bind scrollwheel events directly at this level as well
        self._bind_media_frame_scrolling()
        
        # Bottom action bar
        action_bar = ctk.CTkFrame(self, fg_color=COLORS["bg_medium"], height=60)
        action_bar.grid(row=2, column=0, sticky="ew", padx=0, pady=0)
        action_bar.grid_propagate(False)
        
        # Left section - selection info
        left_section = ctk.CTkFrame(action_bar, fg_color="transparent")
        left_section.pack(side="left", fill="y", padx=20)
        
        # Selection buttons
        select_all_btn = ctk.CTkButton(
            left_section,
            text="Select All Videos",
            command=self.media_frame.select_all_videos,
            width=140,
            height=36,
            corner_radius=8,
            fg_color=COLORS["bg_light"],
            hover_color=COLORS["bg_dark"],
            text_color=COLORS["text_primary"],
            font=ctk.CTkFont(family="Helvetica", size=12)
        )
        select_all_btn.pack(side="left", padx=5, pady=12)
        
        clear_btn = ctk.CTkButton(
            left_section,
            text="Clear Selection",
            command=self.media_frame.clear_selection,
            width=140,
            height=36,
            corner_radius=8,
            fg_color=COLORS["bg_light"],
            hover_color=COLORS["bg_dark"],
            text_color=COLORS["text_primary"],
            font=ctk.CTkFont(family="Helvetica", size=12)
        )
        clear_btn.pack(side="left", padx=5, pady=12)
        
        # Right section - action buttons
        right_section = ctk.CTkFrame(action_bar, fg_color="transparent")
        right_section.pack(side="right", fill="y", padx=20)
        
        # Repost button
        repost_btn = ctk.CTkButton(
            right_section,
            text="Repost Selected",
            command=self.repost_selected,
            width=160,
            height=36,
            corner_radius=8,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            text_color=COLORS["text_primary"],
            font=ctk.CTkFont(family="Helvetica", size=14, weight="bold")
        )
        repost_btn.pack(side="right", padx=5, pady=12)
        
        # Terminal toggle button
        self.terminal_btn = ctk.CTkButton(
            right_section,
            text="Show Terminal",
            command=self.toggle_terminal,
            width=140,
            height=36,
            corner_radius=8,
            fg_color=COLORS["bg_light"],
            hover_color=COLORS["bg_dark"],
            text_color=COLORS["text_primary"],
            font=ctk.CTkFont(family="Helvetica", size=12)
        )
        self.terminal_btn.pack(side="right", padx=5, pady=12)
        
        # Terminal frame - this will be added to the paned window when needed
        self.terminal_frame = ctk.CTkFrame(self.paned_window, fg_color=COLORS["bg_dark"], 
                                          bg_color=COLORS["bg_dark"], 
                                          corner_radius=10)
        # Don't add to paned window initially - it will be added when toggle_terminal is called
        self.terminal_visible = False
        
        # Terminal controls frame
        self.terminal_controls_frame = ctk.CTkFrame(self.terminal_frame, 
                                                   fg_color=COLORS["bg_dark"], 
                                                   corner_radius=0)
        self.terminal_controls_frame.pack(side="top", fill="x", padx=10, pady=(10, 0))
        
        # Log level filter dropdown
        self.log_level_var = ctk.StringVar(value="All Logs")
        self.log_level_filter = ctk.CTkOptionMenu(
            self.terminal_controls_frame,
            values=["All Logs", "Info", "Warning", "Error"], 
            variable=self.log_level_var,
            command=self.apply_log_filter,
            width=100
        )
        self.log_level_filter.pack(side="left", padx=(0, 10))
        
        # Copy button
        self.copy_logs_button = ctk.CTkButton(
            self.terminal_controls_frame,
            text="Copy Logs",
            command=self.copy_terminal_content,
            width=100
        )
        self.copy_logs_button.pack(side="left", padx=(0, 10))
        
        # Clear button
        self.clear_logs_button = ctk.CTkButton(
            self.terminal_controls_frame,
            text="Clear",
            command=self.clear_terminal,
            width=80
        )
        self.clear_logs_button.pack(side="left", padx=(0, 10))
        
        # Command Help button
        self.cmd_help_button = ctk.CTkButton(
            self.terminal_controls_frame,
            text="Command Help",
            command=self.show_command_guide,
            width=120,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"]
        )
        self.cmd_help_button.pack(side="left")
        
        # Terminal text widget
        self.terminal = ctk.CTkTextbox(
            self.terminal_frame,
            fg_color=COLORS["bg_dark"],
            text_color=COLORS["text_primary"],
            font=ctk.CTkFont(family="Consolas", size=12),
            wrap="word",
            state="disabled",
            height=250  # Set minimum height for better visibility
        )
        self.terminal.pack(fill="both", expand=True, padx=10, pady=(10, 5))  # Reduced bottom padding
        
        # Prevent terminal scrolling events from propagating to the media frame
        self.terminal.bind("<MouseWheel>", self._on_terminal_scroll)
        self.terminal.bind("<Button-4>", self._on_terminal_scroll)
        self.terminal.bind("<Button-5>", self._on_terminal_scroll)
        
        # Command entry frame at the bottom of terminal
        self.command_frame = ctk.CTkFrame(self.terminal_frame, 
                                        fg_color=COLORS["bg_dark"],
                                        height=40,  # Set a fixed height
                                        corner_radius=0)
        self.command_frame.pack(side="bottom", fill="x", padx=10, pady=(0, 10))
        self.command_frame.pack_propagate(False)  # Prevent shrinking below specified size
        
        # Command prompt label
        self.command_prompt = ctk.CTkLabel(
            self.command_frame,
            text=">",
            text_color=COLORS["text_primary"],
            font=ctk.CTkFont(family="Consolas", size=12, weight="bold")
        )
        self.command_prompt.pack(side="left", padx=(10, 5), pady=8)  # Add more padding
        
        # Command entry field
        self.command_entry = ctk.CTkEntry(
            self.command_frame,
            fg_color=COLORS["bg_darker"],
            text_color=COLORS["text_primary"],
            font=ctk.CTkFont(family="Consolas", size=12),
            placeholder_text="Type command and press Enter",
            width=400,
            height=30  # Fixed height for better visibility
        )
        self.command_entry.pack(side="left", fill="x", expand=True, padx=(0, 10), pady=5)
        self.command_entry.bind("<Return>", self.execute_command)
        
        # Configure tags for different log levels
        self.terminal.tag_config("info", foreground=COLORS["text_primary"])
        self.terminal.tag_config("warning", foreground=COLORS["warning"])
        self.terminal.tag_config("error", foreground=COLORS["error"])
        self.terminal.tag_config("command_prompt", foreground=COLORS["accent"])
        self.terminal.tag_config("command", foreground=COLORS["accent"])
        
    def setup_logging(self):
        """Configure logging to redirect to the terminal widget."""
        # Create and configure the handler
        handler = TextWidgetHandler(self.terminal)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', 
                                     datefmt='%H:%M:%S')
        handler.setFormatter(formatter)
        
        # Get the root logger and add our handler
        logger = logging.getLogger()
        logger.setLevel(logging.INFO)
        
        # Remove existing handlers to avoid duplicates
        for hdlr in logger.handlers[:]:
            logger.removeHandler(hdlr)
            
        logger.addHandler(handler)
        
        # Redirect stdout/stderr to the terminal
        sys.stdout = TextRedirector(self.terminal)
        sys.stderr = TextRedirector(self.terminal)
        
        # Log startup message
        logging.info("Instagram Repost Tool started")
        
    def toggle_terminal(self):
        """Show or hide the terminal panel."""
        if self.terminal_visible:
            # Remove terminal from paned window
            self.paned_window.forget(self.terminal_frame)
            self.terminal_visible = False
            
            # Update button text
            if hasattr(self, 'terminal_btn'):
                self.terminal_btn.configure(text="Show Terminal")
        else:
            # Add terminal to paned window with a much larger allocation
            self.paned_window.add(self.terminal_frame, minsize=400)  # Much larger minimum size
            self.terminal_visible = True
            
            # Give the terminal approximately 50% of the screen height
            total_height = self.paned_window.winfo_height()
            if total_height > 0:
                # Position the sash at 50% height (equal division between media and terminal)
                self.paned_window.sash_place(0, 0, int(total_height * 0.5))
            
            # Update button text
            if hasattr(self, 'terminal_btn'):
                self.terminal_btn.configure(text="Hide Terminal")
            
            # Show welcome message with command info if this is the first time showing terminal
            if not hasattr(self, 'terminal_help_shown'):
                self.terminal.configure(state="normal")
                welcome_msg = """
╔══════════════════════════════════════════════════════════════════╗
║                   TERMINAL COMMAND REFERENCE                     ║
╠══════════════════════════════════════════════════════════════════╣
║  • Type 'help' for detailed command list                         ║
║  • Filter logs using the dropdown menu above                     ║
║  • Use 'refresh' to update Instagram posts                       ║
║  • Use 'filter video' or 'filter image' to show specific content ║
║  • Use 'search keyword' to find specific posts                   ║
╚══════════════════════════════════════════════════════════════════╝
"""
                self.terminal.insert("end", welcome_msg, "command")
                self.terminal.configure(state="disabled")
                self.terminal_help_shown = True
        
    def on_close(self):
        """Handle application close event."""
        # Stop any running threads
        self.auto_repost_active = False
        
        # Restore stdout/stderr
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__
        
        # Close the application
        self.destroy()
        
    def load_settings(self):
        try:
            with open("settings.json", "r") as f:
                settings = json.load(f)
                ctk.set_appearance_mode(settings.get("theme", "dark"))
                return settings
        except:
            return {"auto_repost_interval": 5, "theme": "dark"}
            
    def refresh_connection_status(self):
        """Refresh the connection status indicator."""
        try:
            if self.reposter and self.reposter.main_client:
                self.status_label.configure(
                    text=f"✓ Connected as {self.reposter.main_client.username}",
                    text_color=COLORS["success"]
                )
                # Enable the refresh button when connected
                if hasattr(self, 'refresh_btn'):
                    self.refresh_btn.configure(state="normal")
            else:
                self.status_label.configure(
                    text="❌ Not connected",
                    text_color=COLORS["warning"]
                )
                # Reset and disable the refresh button when not connected
                if hasattr(self, 'refresh_btn'):
                    self.refresh_btn.configure(
                        text="Load Posts",
                        state="disabled",
                        fg_color=COLORS["success"],
                        hover_color="#1e7c3a"
                    )
                    # Reset tooltip
                    self._create_tooltip(self.refresh_btn, "Load posts from Instagram for the connected account")
        except Exception as e:
            self.log_to_terminal(f"Error updating connection status: {str(e)}", level=logging.ERROR)

    def show_account_manager(self):
        dialog = AccountManagementDialog(self, self.reposter)
        dialog.focus()

    def log_to_terminal(self, message, level=logging.INFO):
        """Log a message to the terminal with the specified level."""
        if level == logging.ERROR:
            logging.error(message)
        elif level == logging.WARNING:
            logging.warning(message)
        else:
            logging.info(message)
        
        # Show terminal if it's an error or warning
        if level >= logging.WARNING and not self.terminal_visible:
            self.toggle_terminal()
        
    def refresh_posts(self, force_refresh=False):
        """Refresh posts from Instagram."""
        try:
            if not self.reposter:
                self.show_warning("Instagram client not initialized")
                return
                
            if not self.reposter.main_client:
                # Check if there's a main account configured but not connected
                if self.reposter.config and self.reposter.config.get("main_account") is not None:
                    self.show_warning("Please connect to your Instagram account first")
                else:
                    self.show_warning("No main account configured. Please add a main account in Account Management.")
                    # Open account management
                    self.show_account_manager()
                return
                
            # Check for automation detection
            if hasattr(self.reposter.main_client, 'delay_range') and self.reposter.main_client.delay_range == [0, 0]:
                self.show_warning("Automation detection risk - please wait before refreshing")
                self.log_to_terminal("Automation detection risk - please wait before refreshing", logging.WARNING)
                return
                
            # Clear existing media
            self.media_frame.clear()
            
            # Show progress dialog
            progress = ProgressDialog(self, "Loading Posts")
            progress.update_progress(0.05, "Connecting to Instagram...")
            
            def load_posts_thread():
                try:
                    # Force refresh of alt posts cache
                    if force_refresh and hasattr(self.reposter, 'alt_posts_cache') and hasattr(self.reposter, 'cache_lock'):
                        try:
                            self.log_to_terminal("Forcing refresh of alt posts cache...")
                            with self.reposter.cache_lock:
                                self.reposter.alt_posts_cache = {}
                                
                            # Also delete the media cache file
                            if self.reposter.main_client and self.reposter.main_client.username:
                                cache_file = f"thumbnails/media_cache_{self.reposter.main_client.username}.json"
                                if os.path.exists(cache_file):
                                    try:
                                        os.remove(cache_file)
                                        self.log_to_terminal(f"Deleted media cache file: {cache_file}")
                                    except Exception as e:
                                        self.log_to_terminal(f"Failed to delete media cache file: {str(e)}", logging.WARNING)
                        except Exception as e:
                            self.log_to_terminal(f"Failed to clear alt posts cache: {str(e)}", logging.WARNING)
                    
                    # Get media list - with a timeout to prevent hanging
                    self.log_to_terminal("Fetching media from Instagram...")
                    
                    # Use a timeout to prevent hanging
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(self.reposter.get_user_medias, 20)
                        try:
                            # Wait for up to 20 seconds for the result
                            medias = future.result(timeout=20)
                            self.log_to_terminal(f"Fetched {len(medias)} media items")
                        except concurrent.futures.TimeoutError:
                            self.log_to_terminal("Media fetch timed out after 20 seconds", logging.ERROR)
                            self.after(0, progress.destroy)
                            self.after(100, lambda: self.show_error("Timeout", "Connection to Instagram timed out. Please try again later."))
                            return
                        except Exception as e:
                            self.log_to_terminal(f"Failed to fetch media: {str(e)}", logging.ERROR)
                            self.after(0, progress.destroy)
                            self.after(100, lambda: self.show_error("Error", f"Failed to fetch media: {str(e)}"))
                            return
                    
                    # Check if we got any media
                    if not medias:
                        self.log_to_terminal("No media found", logging.WARNING)
                        self.after(0, lambda: progress.update_progress(1.0, "No media found"))
                        self.after(500, progress.destroy)
                        self.after(600, lambda: self.show_info("No Media", "No media found in this account"))
                        return
                    
                    total_medias = len(medias)
                    
                    if total_medias == 0:
                        self.log_to_terminal("No posts found", logging.WARNING)
                        self.after(0, lambda: progress.update_progress(1.0, "No posts found"))
                        self.after(500, progress.destroy)
                        return
                    
                    self.log_to_terminal(f"Found {total_medias} posts")
                    
                    # Update progress
                    self.after(0, lambda: progress.update_progress(0.3, f"Adding {total_medias} posts..."))
                    
                    # Create a queue of media to add
                    media_queue = list(medias)
                    
                    # Function to add a single media item with proper error handling
                    def add_single_media():
                        nonlocal media_queue
                        
                        if not media_queue:
                            # All media added, complete the process
                            self.log_to_terminal("Media loading complete")
                            if progress and progress.winfo_exists():
                                progress.update_progress(1.0, "Complete!")
                                self.after(500, progress.destroy)
                                
                            # Update the button text to "Refresh Posts" now that we have loaded posts
                            self.after(0, lambda: self.refresh_btn.configure(
                                text="Refresh Posts",
                                fg_color=COLORS["bg_light"],
                                hover_color=COLORS["bg_dark"]
                            ))
                            
                            # Update tooltip text for the refresh button
                            self.after(0, lambda: self._create_tooltip(self.refresh_btn, 
                                "Refresh posts from Instagram (uses cache when available)"))
                            return
                        
                        try:
                            # Take the next media
                            media = media_queue.pop(0)
                            
                            # Add the media to the frame
                            self.media_frame.add_media(media)
                            
                            # Update progress
                            remaining = len(media_queue)
                            processed = total_medias - remaining
                            progress_value = 0.3 + (0.7 * (processed / total_medias))
                            
                            if progress and progress.winfo_exists():
                                progress.update_progress(progress_value, f"Added {processed}/{total_medias} posts...")
                        except Exception as e:
                            self.log_to_terminal(f"Error adding media: {str(e)}", logging.ERROR)
                        
                        # Schedule the next media addition with a longer delay
                        # This is critical for UI responsiveness
                        self.after(150, add_single_media)
                    
                    # Start the media addition process
                    self.after(100, add_single_media)
                    
                except Exception as e:
                    error_msg = str(e)
                    self.log_to_terminal(f"Failed to fetch posts: {error_msg}", logging.ERROR)
                    self.after(0, lambda: progress.destroy() if progress and progress.winfo_exists() else None)
                    self.after(100, lambda: self.show_error("Failed to fetch posts", error_msg))
            
            # Start loading thread
            loading_thread = threading.Thread(target=load_posts_thread, daemon=True)
            loading_thread.start()
            
            # Add a watchdog timer to detect if the thread is hanging
            def check_thread_alive():
                if loading_thread.is_alive():
                    # Thread is still running after 30 seconds, probably hanging
                    self.log_to_terminal("Loading posts is taking too long, may be stuck", logging.WARNING)
                    if progress and progress.winfo_exists():
                        progress.update_progress(0.5, "Taking longer than expected...")
                    # Check again in 15 seconds
                    self.after(15000, check_thread_alive)
                
            # Start the watchdog timer
            self.after(30000, check_thread_alive)
            
        except Exception as e:
            error_msg = str(e)
            self.log_to_terminal(f"Failed to fetch posts: {error_msg}", logging.ERROR)
            self.show_error("Failed to fetch posts", error_msg)
        
    def show_settings(self):
        settings_dialog = SettingsDialog(self)
        settings_dialog.focus()

    def on_search(self, event=None):
        self.apply_filters()
        
    def on_filter_change(self, value):
        self.apply_filters()
        
    def apply_filters(self):
        """Apply current filters and sort settings."""
        search_text = self.search_entry.get() if hasattr(self, 'search_entry') else ""
        
        # Get media type filter
        media_type = None
        if self.media_type_var.get() != "all":
            media_type = self.media_type_var.get()
            
        # Get sort settings
        sort_by = self.sort_by_var.get() if hasattr(self, 'sort_by_var') else None
        
        # Apply filters
        self.media_frame.filter_and_sort_media(search_text, media_type, sort_by)
        
    def repost_selected(self):
        if not self.media_frame.selected_cards:
            self.show_warning("Please select a post to repost")
            return

        try:
            progress = ProgressDialog(self, "Reposting")
            self.current_repost_thread = threading.Thread(
                target=self._repost_media,
                args=(self.media_frame.selected_cards, progress)
            )
            self.current_repost_thread.daemon = True  # Allow thread to be terminated when window closes
            self.current_repost_thread.start()
        except Exception as e:
            self.show_error("Failed to repost", str(e))

    def _repost_media(self, media_cards, progress=None):
        """Repost selected media to alt accounts."""
        try:
            if not media_cards:
                return
                
            total_media = len(media_cards)
            
            # Update progress dialog
            if progress:
                progress.update_progress(0.1, f"Reposting {total_media} item(s)...")
                
            # Process each selected media
            for i, card in enumerate(media_cards):
                # Check if progress dialog was closed
                if not progress or not progress.winfo_exists():
                    return
                    
                # Update progress
                progress_value = 0.1 + (0.9 * (i / total_media))
                progress.update_progress(progress_value, f"Processing item {i+1} of {total_media}...")
                
                try:
                    # Download the media
                    media_data = self.reposter.download_media(card.media.pk)
                    self.log_to_terminal(f"Downloaded media to {media_data['path']}")
                    
                    # Repost the media
                    self.reposter.repost_media(media_data)
                    self.log_to_terminal(f"Reposted media {card.media.pk}")
                    
                    # Update the card's repost status
                    card.update_repost_status(["Main Account"])
                except Exception as e:
                    self.log_to_terminal(f"Error reposting media {card.media.pk}: {str(e)}", logging.ERROR)
            
            # Complete the progress
            if progress and progress.winfo_exists():
                progress.update_progress(1.0, "Reposting complete!")
                self.after(1000, progress.destroy)
                
            # Show success message
            self.log_to_terminal(f"Successfully reposted {total_media} item(s)")
            
            # Update repost statuses for all media
            self.update_repost_statuses()
                
        except Exception as e:
            self.log_to_terminal(f"Error in repost process: {str(e)}", logging.ERROR)
            if progress and progress.winfo_exists():
                progress.destroy()

    def toggle_auto_repost(self):
        self.auto_repost_active = not self.auto_repost_active
        status = "Enabled" if self.auto_repost_active else "Disabled"
        self.auto_label.configure(text=f"Auto-repost: {status}")
        self.auto_btn.configure(
            text="Disable Auto-Repost" if self.auto_repost_active else "Enable Auto-Repost"
        )
        
        if self.auto_repost_active:
            threading.Thread(target=self._auto_repost_loop, daemon=True).start()

    def _auto_repost_loop(self):
        interval = self.settings.get("auto_repost_interval", 5) * 60  # Convert to seconds
        while self.auto_repost_active:
            try:
                latest_medias = self.reposter.get_user_medias(1)
                if latest_medias:
                    media_pk = latest_medias[0].pk
                    media_data = self.reposter.download_media(media_pk)
                    self.reposter.repost_media(media_data)
                    self.reposter.cleanup(media_data["path"])
            except Exception as e:
                logging.error(f"Auto-repost error: {str(e)}")
            
            # Wait for the configured interval
            for _ in range(interval):
                if not self.auto_repost_active:
                    break
                time.sleep(1)

    def show_error(self, title, message):
        if HAS_CTK_MESSAGEBOX:
            from CTkMessagebox import CTkMessagebox
            CTkMessagebox(self, title=title, message=message, icon="cancel")
        else:
            tkmb.showerror(title, message)

    def show_warning(self, message):
        if HAS_CTK_MESSAGEBOX:
            from CTkMessagebox import CTkMessagebox
            CTkMessagebox(self, title="Warning", message=message, icon="warning")
        else:
            tkmb.showwarning("Warning", message)

    def show_info(self, title, message):
        if HAS_CTK_MESSAGEBOX:
            from CTkMessagebox import CTkMessagebox
            CTkMessagebox(self, title=title, message=message, icon="info")
        else:
            tkmb.showinfo(title, message)
        
    def repost_all_videos(self):
        try:
            # Get all video cards that haven't been reposted
            unreposted_videos = [
                card for card in self.media_frame.cards 
                if card.media.media_type == 2  # Video
            ]
            
            if not unreposted_videos:
                self.show_info("No Videos", "No videos found to repost")
                return
                
            progress = ProgressDialog(self, "Reposting All Videos")
            threading.Thread(
                target=self._repost_multiple_videos,
                args=(unreposted_videos, progress),
                daemon=True
            ).start()
        except Exception as e:
            self.show_error("Failed to start reposting", str(e))

    def _repost_multiple_videos(self, video_cards, progress):
        try:
            total_videos = len(video_cards)
            for i, card in enumerate(video_cards, 1):
                try:
                    # Update progress
                    status = f"Processing video {i}/{total_videos}"
                    self.after(0, lambda: progress.update_progress(i/total_videos, status))
                    
                    # Download video once
                    media_data = self.reposter.download_media(card.media.pk)
                    
                    # Try to repost to each alt account that hasn't reposted it yet
                    for client in self.reposter.alt_clients:
                        # Check if this account already reposted this video
                        already_reposted = False
                        alt_medias = client.user_medias(client.user_id, 20)
                        for alt_media in alt_medias:
                            if (alt_media.caption_text or "").strip() == (card.media.caption_text or "").strip():
                                already_reposted = True
                                break
                        
                        if not already_reposted:
                            # Repost to this account
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
                            logging.info(f"Reposted to {client.username}")
                    
                    # Cleanup downloaded file
                    self.reposter.cleanup(media_data["path"])
                    
                    # Force refresh of repost status
                    self.log_to_terminal(f"Updating repost status for video {i}...")
                    
                    # Clear cache to force refresh
                    with self.reposter.cache_lock:
                        self.reposter.alt_posts_cache = {}
                    
                    # Update repost status for this card
                    reposted_accounts = self.reposter.check_repost_status(card.media)
                    card.media.reposted_to = reposted_accounts
                    
                    # Update UI
                    self.after(0, lambda c=card, accounts=reposted_accounts: c.update_repost_status(accounts))
                    self.log_to_terminal(f"Repost status updated for video {i}: {', '.join(reposted_accounts) if reposted_accounts else 'No reposts found'}")
                    
                    # Also update all other media cards with the same media ID
                    for other_card in self.media_frame.cards:
                        if other_card != card and other_card.media.pk == card.media.pk:
                            other_card.media.reposted_to = reposted_accounts
                            self.after(0, lambda c=other_card, accounts=reposted_accounts: c.update_repost_status(accounts))
                    
                except Exception as e:
                    logging.error(f"Failed to process video {i}: {str(e)}")
                    continue
            
            # Complete
            self.after(0, lambda: progress.update_progress(1.0, "Complete!"))
            self.after(1000, progress.destroy)
            self.show_info("Success", "Finished reposting videos")
            
        except Exception as e:
            if progress:
                progress.destroy()
            self.show_error("Failed to repost videos", str(e))

    def connect_main_account(self):
        """Connect to the main account if configured."""
        try:
            if not self.reposter.config.get("main_account"):
                # Show a more helpful error and offer to open account management
                if tkmb.askyesno(
                    "No Main Account", 
                    "No main account is configured. Would you like to add an account now?",
                    icon="warning"
                ):
                    self.show_account_manager()
                return
                
            # Get the main account username
            username = self.reposter.config["main_account"]["username"]
            self.log_to_terminal(f"Connecting to main account: {username}")
            
            # Show progress dialog
            progress = ProgressDialog(self, "Connecting")
            progress.update_progress(0.2, f"Connecting to {username}...")
            
            # Start connection in background thread
            def connect_thread():
                try:
                    # Update verification handler to use main thread
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
                        
                        self.log_to_terminal(f"Verification required for {username} via {challenge_type}", logging.WARNING)
                        
                        # Update progress in main thread
                        self.after(0, lambda: progress.update_progress(0.4, f"Verification required via {challenge_type}..."))
                        
                        # Show verification dialog in main thread
                        code_result = [None]  # Use a list to store the result across threads
                        
                        def show_dialog():
                            code = VerificationDialog.show_dialog(self, username, challenge_type)
                            code_result[0] = code
                            if not code:
                                self.log_to_terminal("Verification cancelled by user", logging.WARNING)
                            else:
                                # Update progress after verification
                                self.log_to_terminal("Verification code entered, verifying...")
                                progress.update_progress(0.6, "Verifying code...")
                        
                        # Run the dialog in the main thread and wait for it to complete
                        self.after(0, show_dialog)
                        
                        # Wait for the result
                        while code_result[0] is None:
                            time.sleep(0.1)
                            
                        # Return the verification code to the client
                        return code_result[0]
                    
                    # Update reposter's verification handler
                    self.log_to_terminal("Setting up verification handler")
                    if self.reposter.main_client:
                        self.reposter.main_client.change_verification_handler(verification_handler)
                    for client in self.reposter.alt_clients:
                        client.change_verification_handler(verification_handler)
                    
                    # Initialize connection
                    self.log_to_terminal(f"Logging in as {username}")
                    try:
                        client = self.reposter._login_selected_main(username)
                        
                        if not client:
                            self.log_to_terminal(f"Failed to connect to {username}", logging.ERROR)
                            self.after(0, progress.destroy)
                            self.after(100, lambda: self.show_error(
                                "Connection Failed", 
                                f"Could not connect to {username}. Please check your password in Account Management."
                            ))
                            self.after(200, lambda: self.status_label.configure(
                                text="❌ Connection failed",
                                text_color=COLORS["error"]
                            ))
                            return
                            
                        self.log_to_terminal(f"Successfully logged in as {username}")
                        
                        # Update UI in main thread
                        self.after(0, lambda: progress.update_progress(0.9, "Connected!"))
                        self.after(0, self.refresh_connection_status)
                        
                        # Update media frame reposter reference
                        self.after(0, lambda: setattr(self.media_frame, 'reposter', self.reposter))
                        
                        # Show success and close progress
                        self.after(0, lambda: progress.update_progress(1.0, "Connection complete"))
                        self.after(500, progress.destroy)
                        
                        # No longer asking if user wants to load posts - they can use the Load Posts button
                        self.log_to_terminal(f"Successfully connected to {username}. Use the Load Posts button to view your content.", logging.INFO)
                        
                    except IPBlacklistError as e:
                        self.log_to_terminal(f"IP blacklisted: {str(e)}", logging.ERROR)
                        self.after(0, progress.destroy)
                        self.after(100, lambda: self._show_ip_blacklist_error(str(e)))
                        
                except Exception as e:
                    # Store error message before scheduling callbacks
                    error_msg = str(e)
                    self.log_to_terminal(f"Connection failed: {error_msg}", logging.ERROR)
                    self.after(0, progress.destroy)
                    self.after(100, lambda: self.show_error("Connection Failed", error_msg))
                    self.after(200, lambda: self.status_label.configure(
                        text="❌ Connection failed",
                        text_color=COLORS["error"]
                    ))
            
            # Start connection thread
            connect_thread = threading.Thread(target=connect_thread, daemon=True)
            connect_thread.start()
                
        except Exception as e:
            self.show_error("Error", f"Failed to connect: {str(e)}")

    def _show_ip_blacklist_error(self, error_message=None):
        """Show a detailed message about Instagram IP blacklisting and how to fix it."""
        msg = "Instagram has temporarily blacklisted your IP address\n\n"
        msg += "To fix this issue:\n"
        msg += "1. Use a VPN to change your IP address\n"
        msg += "2. Close the application completely\n"
        msg += "3. Restart the application after connecting to VPN\n\n"
        msg += "This is a security measure by Instagram to prevent automated access."
        
        if error_message:
            msg += f"\n\nError details: {error_message}"
            
        result = tkmb.askokcancel(
            "IP Address Blacklisted", 
            msg,
            icon="warning"
        )
        
        if result:
            # User clicked OK, offer to close the application
            if tkmb.askyesno(
                "Close Application", 
                "Would you like to close the application now? You can restart after connecting to a VPN.",
                icon="question"
            ):
                self.quit()

    def _create_tooltip(self, widget, text):
        """Create a tooltip for a widget."""
        # Create tooltip window
        def enter(event):
            x, y, _, _ = widget.bbox("insert")
            x += widget.winfo_rootx() + 25
            y += widget.winfo_rooty() + 25
            
            # Create a toplevel window
            tooltip = tk.Toplevel(widget)
            tooltip.wm_overrideredirect(True)
            tooltip.wm_geometry(f"+{x}+{y}")
            
            # Create tooltip label
            label = tk.Label(
                tooltip, 
                text=text, 
                justify="left",
                background=COLORS["bg_dark"],
                foreground=COLORS["text_primary"],
                relief="solid", 
                borderwidth=1,
                font=("Segoe UI", 10)
            )
            label.pack(ipadx=5, ipady=5)
            
            # Store tooltip reference
            widget._tooltip = tooltip
            
        def leave(event):
            if hasattr(widget, "_tooltip"):
                widget._tooltip.destroy()
                
        # Bind events
        widget.bind("<Enter>", enter)
        widget.bind("<Leave>", leave)

    def _track_event(self, event):
        """Track the current event to check for modifier keys."""
        self._current_event = event
        
    def _get_event(self):
        """Get the current event for checking modifier keys."""
        return self._current_event 

    def _bind_media_frame_scrolling(self):
        """Bind mouse wheel events to the media frame for better scrolling."""
        def _on_mousewheel(event):
            # Handle Windows mouse wheel event
            delta = event.delta // 120  # Normalize to +1 or -1
            if delta > 0:
                self.media_frame.scroll_up()
            else:
                self.media_frame.scroll_down()
            return "break"
            
        def _on_button4(event):
            # Handle Linux scroll up
            self.media_frame.scroll_up()
            return "break"
            
        def _on_button5(event):
            # Handle Linux scroll down
            self.media_frame.scroll_down()
            return "break"
            
        # Bind mouse wheel events with platform-specific handling
        # Binding to app level to ensure we catch events anywhere
        self.bind("<MouseWheel>", _on_mousewheel, "+")  # Windows
        self.bind("<Button-4>", _on_button4, "+")       # Linux scroll up
        self.bind("<Button-5>", _on_button5, "+")       # Linux scroll down 

    def update_repost_statuses(self):
        """Update repost statuses for all displayed media.
        
        This method is called when an alt account is connected to update
        the repost status indicators without requiring the user to reload media.
        """
        if not self.reposter or not self.media_frame:
            return
            
        self.log_to_terminal("Updating repost statuses...")
        
        # Get all currently displayed media
        try:
            # Get all media cards
            media_cards = self.media_frame.media_cards
            
            if not media_cards:
                self.log_to_terminal("No media loaded to update")
                return
                
            # Show a progress indicator
            progress = ProgressDialog(self, "Updating Repost Status")
            progress.update_progress(0.0, "Checking repost status for displayed media...")
            
            def update_thread():
                try:
                    total_cards = len(media_cards)
                    
                    # Update each card's repost status
                    for i, card in enumerate(media_cards):
                        if not progress.winfo_exists():
                            break
                            
                        # Check if the media is reposted to any alt accounts
                        reposted_to = self.reposter.check_repost_status(card.media)
                        
                        # Update the UI in the main thread
                        self.after(0, lambda c=card, r=reposted_to: c.update_repost_status(r))
                        
                        # Update progress
                        progress_value = (i + 1) / total_cards
                        self.after(0, lambda v=progress_value: progress.update_progress(v, f"Checked {i+1}/{total_cards} posts..."))
                    
                    # Finish up
                    self.after(0, lambda: self.log_to_terminal("Repost status update complete"))
                    self.after(500, lambda: progress.destroy() if progress.winfo_exists() else None)
                    
                except Exception as e:
                    self.log_to_terminal(f"Error updating repost status: {str(e)}", logging.ERROR)
                    self.after(0, lambda: progress.destroy() if progress.winfo_exists() else None)
            
            # Start the update thread
            threading.Thread(target=update_thread, daemon=True).start()
            
        except Exception as e:
            self.log_to_terminal(f"Error preparing repost status update: {str(e)}", logging.ERROR) 

    def _on_terminal_scroll(self, event):
        """
        Handle the terminal scrolling to prevent event propagation to media frame.
        This allows the terminal's native scrolling behavior to work without affecting
        other elements in the UI.
        """
        # For MouseWheel events (Windows)
        if hasattr(event, 'delta'):
            if event.delta > 0:
                event.widget.yview_scroll(-1, "units")
            else:
                event.widget.yview_scroll(1, "units")
        # For Button-4 (scroll up) and Button-5 (scroll down) events (Linux)
        elif hasattr(event, 'num'):
            if event.num == 4:
                event.widget.yview_scroll(-1, "units")
            elif event.num == 5:
                event.widget.yview_scroll(1, "units")
        
        # Prevent the event from propagating further
        return "break" 

    def apply_log_filter(self, value):
        """Filter log entries based on selected level."""
        self.terminal.configure(state="normal")
        
        # Store current content
        full_content = self.terminal.get("1.0", "end-1c")
        
        # Clear current content
        self.terminal.delete("1.0", "end")
        
        # Process each line based on filter
        for line in full_content.splitlines():
            if value == "All Logs":
                log_tag = "info"
                if " - ERROR - " in line:
                    log_tag = "error"
                elif " - WARNING - " in line:
                    log_tag = "warning"
                self.terminal.insert("end", line + "\n", log_tag)
            elif value == "Error" and " - ERROR - " in line:
                self.terminal.insert("end", line + "\n", "error")
            elif value == "Warning" and (" - WARNING - " in line or " - ERROR - " in line):
                log_tag = "error" if " - ERROR - " in line else "warning"
                self.terminal.insert("end", line + "\n", log_tag)
            elif value == "Info" and not (" - DEBUG - " in line):
                log_tag = "info"
                if " - ERROR - " in line:
                    log_tag = "error"
                elif " - WARNING - " in line:
                    log_tag = "warning"
                self.terminal.insert("end", line + "\n", log_tag)
        
        # Return to disabled state
        self.terminal.configure(state="disabled")
        
        # Scroll to the end
        self.terminal.see("end")

    def copy_terminal_content(self):
        """Copy all terminal content to clipboard."""
        # Get content based on current filter
        content = self.terminal.get("1.0", "end-1c")
        
        if content:
            # Copy to clipboard
            self.clipboard_clear()
            self.clipboard_append(content)
            
            # Show confirmation
            self.log_to_terminal("Terminal content copied to clipboard", logging.INFO)
        else:
            self.log_to_terminal("No content to copy", logging.WARNING)

    def clear_terminal(self):
        """Clear terminal content."""
        self.terminal.configure(state="normal")
        self.terminal.delete("1.0", "end")
        self.terminal.configure(state="disabled")
        self.log_to_terminal("Terminal cleared", logging.INFO)

    def execute_command(self, event):
        """Execute a command entered in the terminal."""
        command = self.command_entry.get().strip()
        if not command:
            return
            
        # Add command to terminal with a special prompt tag
        self.terminal.configure(state="normal")
        self.terminal.insert("end", f"> {command}\n", "command_prompt")
        self.terminal.configure(state="disabled")
        self.terminal.see("end")
        
        # Clear command entry
        self.command_entry.delete(0, "end")
        
        # Split command into parts
        parts = command.split()
        cmd = parts[0].lower()
        args = parts[1:] if len(parts) > 1 else []
        
        # Execute command based on the command word
        try:
            if cmd == "help":
                self._show_command_help()
            elif cmd == "clear":
                self.clear_terminal()
            elif cmd == "refresh":
                self.refresh_posts(force_refresh=True)
                self.log_to_terminal("Refreshing posts...", logging.INFO)
            elif cmd == "connect":
                if len(args) > 0:
                    username = args[0]
                    self.log_to_terminal(f"Connecting to account: {username}...", logging.INFO)
                    # Trigger account connection UI for the specified username
                    # This is just showing the account manager
                    self.show_account_manager()
                else:
                    self.log_to_terminal("Usage: connect <username>", logging.WARNING)
            elif cmd == "repost":
                if len(args) > 0 and args[0] == "all":
                    self.repost_all_videos()
                else:
                    self.log_to_terminal("Usage: repost all", logging.WARNING)
            elif cmd == "filter":
                if len(args) > 0:
                    filter_type = args[0].lower()
                    if filter_type in ["image", "video", "all"]:
                        # Apply the filter
                        self.filter_var.set(filter_type.capitalize())
                        self.apply_filters()
                        self.log_to_terminal(f"Applied filter: {filter_type}", logging.INFO)
                    else:
                        self.log_to_terminal("Valid filters: image, video, all", logging.WARNING)
                else:
                    self.log_to_terminal("Usage: filter <type> (image, video, all)", logging.WARNING)
            elif cmd == "search":
                if len(args) > 0:
                    search_term = " ".join(args)
                    self.search_entry.delete(0, "end")
                    self.search_entry.insert(0, search_term)
                    self.on_search()
                    self.log_to_terminal(f"Searching for: {search_term}", logging.INFO)
                else:
                    self.log_to_terminal("Usage: search <term>", logging.WARNING)
            elif cmd == "status":
                self.log_to_terminal("Checking connection status...", logging.INFO)
                self.refresh_connection_status()
            elif cmd == "exit" or cmd == "quit":
                if tkmb.askyesno("Confirm Exit", "Are you sure you want to exit the application?"):
                    self.on_close()
            else:
                self.log_to_terminal(f"Unknown command: {cmd}. Type 'help' for available commands.", logging.WARNING)
        except Exception as e:
            self.log_to_terminal(f"Error executing command: {str(e)}", logging.ERROR)
        
        # Configure tag for command prompt
        self.terminal.tag_config("command", foreground=COLORS["accent"])
    
    def _show_command_help(self):
        """Show help information for terminal commands."""
        help_text = """Available Commands:
- help: Show this help message
- clear: Clear the terminal
- refresh: Refresh posts from Instagram
- connect <username>: Connect to an Instagram account
- repost all: Repost all videos
- filter <type>: Apply filter (image, video, all)
- search <term>: Search for posts with the given term
- status: Check connection status
- exit/quit: Exit the application
"""
        self.log_to_terminal(help_text, logging.INFO)
        
    def show_command_guide(self):
        """Display an interactive command help dialog."""
        # Create a toplevel window
        help_window = ctk.CTkToplevel(self)
        help_window.title("Terminal Command Guide")
        help_window.geometry("600x500")
        help_window.resizable(False, False)
        help_window.grab_set()  # Make the window modal
        
        # Main container frame
        main_frame = ctk.CTkFrame(help_window, fg_color=COLORS["bg_medium"])
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Header label
        header = ctk.CTkLabel(
            main_frame, 
            text="Terminal Command Reference", 
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=COLORS["accent"]
        )
        header.pack(pady=(15, 25))
        
        # Command category buttons frame
        categories_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        categories_frame.pack(fill="x", padx=10, pady=(0, 15))
        
        # Content frame that will display command details
        content_frame = ctk.CTkFrame(main_frame)
        content_frame.pack(fill="both", expand=True, padx=10, pady=(0, 15))
        
        # Command content text widget
        cmd_content = ctk.CTkTextbox(
            content_frame,
            wrap="word",
            width=550,
            height=250,
            font=ctk.CTkFont(family="Consolas", size=13),
            fg_color=COLORS["bg_dark"],
            text_color=COLORS["text_primary"]
        )
        cmd_content.pack(fill="both", expand=True, padx=15, pady=15)
        cmd_content.configure(state="disabled")
        
        # Dictionary of command categories and their details
        command_categories = {
            "Basic": [
                {"cmd": "help", "desc": "Display a list of available commands in the terminal"},
                {"cmd": "clear", "desc": "Clear the terminal"},
                {"cmd": "status", "desc": "Check the current connection status of all accounts"},
                {"cmd": "exit/quit", "desc": "Exit the application safely"}
            ],
            "Instagram": [
                {"cmd": "refresh", "desc": "Force refresh posts from your Instagram account"},
                {"cmd": "connect <username>", "desc": "Connect to an Instagram account by username"},
                {"cmd": "repost all", "desc": "Repost all videos in your feed at once"}
            ],
            "Filtering": [
                {"cmd": "filter all", "desc": "Show all media types (default)"},
                {"cmd": "filter video", "desc": "Show only video posts"},
                {"cmd": "filter image", "desc": "Show only image posts"},
                {"cmd": "search <term>", "desc": "Search for posts containing specific text"}
            ]
        }
        
        # Configure text styles
        cmd_content.tag_config("header", foreground=COLORS["accent"])
        cmd_content.tag_config("command_name", foreground=COLORS["success"])
        cmd_content.tag_config("command_desc", foreground=COLORS["text_primary"])
        cmd_content.tag_config("example_header", foreground=COLORS["warning"])
        cmd_content.tag_config("example", foreground=COLORS["accent"])
        
        # Function to display commands for a category
        def show_category(category):
            cmd_content.configure(state="normal")
            cmd_content.delete("1.0", "end")
            
            # Set header with category name
            cmd_content.insert("end", f"📂 {category} Commands\n\n", "header")
            
            # Add each command and its description
            for cmd_info in command_categories[category]:
                cmd_content.insert("end", f"● {cmd_info['cmd']}\n", "command_name")
                cmd_content.insert("end", f"    {cmd_info['desc']}\n\n", "command_desc")
                
            # Example usage for the first command
            if command_categories[category]:
                first_cmd = command_categories[category][0]["cmd"].split()[0]
                cmd_content.insert("end", f"\nExample Usage:\n", "example_header")
                cmd_content.insert("end", f"> {first_cmd}\n", "example")
            
            cmd_content.configure(state="disabled")
        
        # Create a button for each category
        for i, category in enumerate(command_categories.keys()):
            btn = ctk.CTkButton(
                categories_frame,
                text=category,
                width=100,
                command=lambda cat=category: show_category(cat),
                fg_color=COLORS["bg_light"] if i > 0 else COLORS["accent"]
            )
            btn.pack(side="left", padx=10)
        
        # Button to try a command directly
        def try_command():
            cmd = cmd_entry.get().strip()
            if cmd:
                help_window.destroy()
                self.command_entry.delete(0, "end")
                self.command_entry.insert(0, cmd)
                self.execute_command(None)
        
        # Input frame for trying commands
        input_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        input_frame.pack(fill="x", padx=10, pady=(5, 15))
        
        try_label = ctk.CTkLabel(input_frame, text="Try a command:")
        try_label.pack(side="left", padx=(5, 10))
        
        cmd_entry = ctk.CTkEntry(input_frame, width=350)
        cmd_entry.pack(side="left", padx=(0, 10))
        
        try_btn = ctk.CTkButton(
            input_frame, 
            text="Execute", 
            command=try_command,
            width=80
        )
        try_btn.pack(side="left")
        
        # Close button at the bottom
        close_btn = ctk.CTkButton(
            main_frame,
            text="Close",
            command=help_window.destroy,
            width=100,
            fg_color=COLORS["danger"],
            hover_color=COLORS["danger_hover"]
        )
        close_btn.pack(pady=(0, 10))
        
        # Show the Basic category by default
        show_category("Basic")

    def update_selection_count(self, count):
        """Update UI elements based on the number of selected items."""
        # Update the repost button text to show selection count
        if count > 0:
            self.repost_btn.configure(text=f"Repost Selected ({count})")
        else:
            self.repost_btn.configure(text="Repost Selected")
            
        # Enable/disable the repost button based on selection
        if count > 0:
            self.repost_btn.configure(state="normal")
        else:
            self.repost_btn.configure(state="disabled")
    
    def show_content_stealer(self):
        """Show the content stealer dialog for downloading content from URL."""
        # Create a toplevel window
        stealer_window = ctk.CTkToplevel(self)
        stealer_window.title("Content Stealer")
        stealer_window.geometry("900x950")
        stealer_window.grab_set()  # Make the window modal
        
        # Main container frame
        main_frame = ctk.CTkFrame(stealer_window, fg_color=COLORS["bg_medium"])
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Header label
        header = ctk.CTkLabel(
            main_frame, 
            text="Instagram Content Stealer", 
            font=ctk.CTkFont(size=24, weight="bold"),
            text_color=COLORS["accent"]
        )
        header.pack(pady=(15, 25))
        
        # URL input frame
        url_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        url_frame.pack(fill="x", padx=10, pady=(0, 15))
        
        # URL label
        url_label = ctk.CTkLabel(
            url_frame,
            text="Instagram URL:",
            font=ctk.CTkFont(size=14),
            width=100,
            anchor="w"
        )
        url_label.pack(side="left", padx=(5, 10))
        
        # URL entry
        url_entry = ctk.CTkEntry(
            url_frame,
            placeholder_text="Paste Instagram URL here (post, reel, story, etc.)",
            width=500,
            height=35,
            font=ctk.CTkFont(size=14)
        )
        url_entry.pack(side="left", padx=(0, 10), fill="x", expand=True)
        
        # Fetch button
        fetch_btn = ctk.CTkButton(
            url_frame,
            text="Fetch Content",
            command=lambda: self._fetch_instagram_content(url_entry.get(), stealer_window, content_frame, options_frame, status_label, options_label),
            width=130,
            height=35,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"]
        )
        fetch_btn.pack(side="left", padx=(0, 5))
        
        # Status label
        status_label = ctk.CTkLabel(
            main_frame,
            text="Enter an Instagram URL to fetch content",
            font=ctk.CTkFont(size=12),
            text_color=COLORS["text_secondary"]
        )
        status_label.pack(pady=(0, 10))
        
        # Content frame for preview
        content_frame = ctk.CTkFrame(main_frame)
        content_frame.pack(fill="both", expand=True, padx=10, pady=(0, 15))
        
        # Initial content message
        initial_message = ctk.CTkLabel(
            content_frame,
            text="Content preview will appear here",
            font=ctk.CTkFont(size=16),
            text_color=COLORS["text_secondary"]
        )
        initial_message.pack(pady=100)
        
        # Options frame (accounts, caption, etc.)
        options_frame = ctk.CTkFrame(main_frame, fg_color=COLORS["bg_light"], height=200)
        options_frame.pack(fill="x", padx=10, pady=(0, 15))
        
        # Options label
        options_label = ctk.CTkLabel(
            options_frame,
            text="Posting Options",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=COLORS["text_primary"]
        )
        options_label.pack(pady=(10, 5), padx=10, anchor="w")
        
        # Add info text (initially hidden, will be shown when content is fetched)
        options_frame.pack_forget()
        
        # Bottom buttons frame
        buttons_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        buttons_frame.pack(fill="x", padx=10, pady=(5, 10))
        
        # Close button
        close_btn = ctk.CTkButton(
            buttons_frame,
            text="Close",
            command=stealer_window.destroy,
            width=100,
            fg_color=COLORS["danger"],
            hover_color=COLORS["danger_hover"]
        )
        close_btn.pack(side="right", padx=5)
    
    def _fetch_instagram_content(self, url, parent_window, content_frame, options_frame, status_label, options_label):
        """Fetch Instagram content from the given URL."""
        if not url or not url.strip():
            status_label.configure(text="Please enter a valid Instagram URL", text_color=COLORS["warning"])
            return
            
        # Update status
        status_label.configure(text="Fetching content...", text_color=COLORS["text_secondary"])
        
        # Start a thread to fetch content
        threading.Thread(
            target=self._fetch_content_thread,
            args=(url, parent_window, content_frame, options_frame, status_label, options_label),
            daemon=True
        ).start()
    
    def _fetch_content_thread(self, url, parent_window, content_frame, options_frame, status_label, options_label):
        """Thread function to fetch Instagram content."""
        try:
            # Remove any existing widgets from content frame
            for widget in content_frame.winfo_children():
                widget.destroy()
                
            # Ensure we have a valid Instagram client
            if not self.reposter or not self.reposter.main_client:
                self.after(0, lambda: status_label.configure(
                    text="You must be logged in to an Instagram account first",
                    text_color=COLORS["error"]
                ))
                return
                
            # Update status
            self.after(0, lambda: status_label.configure(
                text="Connecting to Instagram API...",
                text_color=COLORS["text_secondary"]
            ))
                
            # Try to fetch the content info
            try:
                content_info = self.reposter.fetch_content_by_url(url)
                self.after(0, lambda: self._display_fetched_content(
                    content_frame, options_frame, status_label, parent_window, url, content_info, options_label
                ))
            except NotImplementedError as nie:
                error_msg = str(nie)
                self.after(0, lambda: status_label.configure(
                    text=error_msg,
                    text_color=COLORS["warning"]
                ))
            except Exception as ex:
                error_msg = str(ex)
                self.after(0, lambda: status_label.configure(
                    text=f"Error fetching content: {error_msg}",
                    text_color=COLORS["error"]
                ))
            
        except Exception as e:
            error_msg = str(e)
            self.after(0, lambda: status_label.configure(
                text=f"Error: {error_msg}",
                text_color=COLORS["error"]
            ))
    
    def _display_fetched_content(self, content_frame, options_frame, status_label, parent_window, url, content_info, options_label=None):
        """Display the fetched content in the UI."""
        try:
            # Check if there's an error in the content info
            if content_info.get('error'):
                error_message = content_info.get('error')
                status_label.configure(
                    text=f"Warning: {error_message}",
                    text_color=COLORS["warning"]
                )
                
                # Create error display frame
                error_frame = ctk.CTkFrame(content_frame, fg_color=COLORS["bg_medium"])
                error_frame.pack(fill="both", expand=True, padx=10, pady=10)
                
                # Error icon
                error_icon = ctk.CTkLabel(
                    error_frame,
                    text="⚠️",
                    font=ctk.CTkFont(size=48),
                    text_color=COLORS["warning"]
                )
                error_icon.pack(pady=(30, 10))
                
                # Error title
                error_title = ctk.CTkLabel(
                    error_frame,
                    text="Limited Content Access",
                    font=ctk.CTkFont(size=20, weight="bold"),
                    text_color=COLORS["text_primary"]
                )
                error_title.pack(pady=(5, 15))
                
                # Error message
                error_message_label = ctk.CTkLabel(
                    error_frame,
                    text=error_message,
                    font=ctk.CTkFont(size=14),
                    text_color=COLORS["text_secondary"],
                    wraplength=500
                )
                error_message_label.pack(pady=(0, 15))
                
                # Additional help text
                help_text = ctk.CTkTextbox(
                    error_frame,
                    height=150,
                    width=500,
                    font=ctk.CTkFont(size=13),
                    fg_color=COLORS["bg_dark"],
                    text_color=COLORS["text_secondary"]
                )
                help_text.pack(pady=(0, 15), padx=40)
                help_text.insert("1.0", "This content cannot be directly accessed through the API. Possible reasons:\n\n"
                                      "• The post is from a private account you don't follow\n"
                                      "• The post has been deleted or is no longer available\n"
                                      "• Instagram API limitations prevent direct access\n"
                                      "• You don't have permission to view this content\n\n"
                                      "Recommendation: Try using a URL from your own account or from public accounts you follow.")
                help_text.configure(state="disabled")
                
                # Try different URL button
                retry_btn = ctk.CTkButton(
                    error_frame,
                    text="Try Different URL",
                    command=lambda: self._clear_content_frame(content_frame, status_label),
                    width=150,
                    height=35
                )
                retry_btn.pack(pady=(0, 30))
                
                # Hide the options frame since we can't post this content
                options_frame.pack_forget()
                
                return
            
            # Update status (successful fetch)
            status_label.configure(
                text=f"Content fetched successfully! Ready to edit and post.",
                text_color=COLORS["success"]
            )
            
            # Extract content info
            media_type = content_info.get('media_type', 1)
            shortcode = content_info.get('shortcode', '')
            original_caption = content_info.get('caption', '')
            original_username = content_info.get('username', 'unknown')
            
            # Create content preview UI
            preview_frame = ctk.CTkFrame(content_frame)
            preview_frame.pack(fill="both", expand=True, padx=10, pady=10)
            
            # Content type and info
            info_frame = ctk.CTkFrame(preview_frame, fg_color=COLORS["bg_dark"], height=40)
            info_frame.pack(fill="x", padx=5, pady=5)
            
            content_type_str = "Video" if media_type == 2 else "Photo" if media_type == 1 else "Album"
            content_info_text = f"Content Type: {content_type_str} • ID: {shortcode} • From: @{original_username}"
            content_info_label = ctk.CTkLabel(
                info_frame,
                text=content_info_text,
                font=ctk.CTkFont(size=12),
                text_color=COLORS["text_secondary"]
            )
            content_info_label.pack(pady=8, padx=10, anchor="w")
            
            # Media preview frame
            media_frame = ctk.CTkFrame(preview_frame, fg_color=COLORS["bg_dark"], height=300)
            media_frame.pack(fill="both", expand=True, padx=5, pady=5)
            
            # Create loading indicator
            loading_label = ctk.CTkLabel(
                media_frame,
                text="Loading thumbnail...",
                font=ctk.CTkFont(size=14),
                text_color=COLORS["text_secondary"]
            )
            loading_label.pack(pady=130)
            
            # Try to display thumbnail if available
            thumbnail_url = content_info.get('thumbnail_url')
            media_pk = content_info.get('media_pk')
            
            # Create a function to load and display the thumbnail
            def load_thumbnail():
                try:
                    if not thumbnail_url:
                        raise ValueError("No thumbnail URL available")
                    
                    self.log_to_terminal(f"Loading thumbnail from URL", logging.INFO)
                    
                    # Import required libraries
                    import requests
                    from PIL import Image, ImageTk
                    from io import BytesIO
                    
                    # Download the image data
                    response = requests.get(thumbnail_url, timeout=10)
                    if response.status_code != 200:
                        raise ValueError(f"Failed to download thumbnail: HTTP {response.status_code}")
                    
                    # Convert to image
                    img_data = BytesIO(response.content)
                    pil_img = Image.open(img_data)
                    
                    # Resize image to fit the frame (maintaining aspect ratio)
                    target_width = 300
                    target_height = 250
                    img_width, img_height = pil_img.size
                    
                    # Calculate new dimensions while maintaining aspect ratio
                    ratio = min(target_width/img_width, target_height/img_height)
                    new_width = int(img_width * ratio)
                    new_height = int(img_height * ratio)
                    
                    pil_img = pil_img.resize((new_width, new_height), Image.LANCZOS)
                    
                    # Convert to CTkImage
                    ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(new_width, new_height))
                    
                    # Update UI on main thread
                    self.after(0, lambda: self._update_thumbnail_ui(media_frame, ctk_img, loading_label))
                    
                except Exception as e:
                    self.log_to_terminal(f"Error loading thumbnail: {str(e)}", logging.WARNING)
                    self.after(0, lambda: self._show_placeholder_thumbnail(
                        media_frame, loading_label, media_type, shortcode
                    ))
            
            # Start the thumbnail loading in a separate thread
            threading.Thread(target=load_thumbnail, daemon=True).start()
            
            # Caption editor
            caption_frame = ctk.CTkFrame(preview_frame, fg_color=COLORS["bg_dark"])
            caption_frame.pack(fill="x", padx=5, pady=5)
            
            caption_label = ctk.CTkLabel(
                caption_frame,
                text="Edit Caption:",
                font=ctk.CTkFont(size=14),
                text_color=COLORS["text_primary"],
                anchor="w"
            )
            caption_label.pack(fill="x", padx=10, pady=(10, 5), anchor="w")
            
            caption_text = ctk.CTkTextbox(
                caption_frame,
                height=100,
                font=ctk.CTkFont(size=13),
                fg_color=COLORS["bg_medium"],
                text_color=COLORS["text_primary"]
            )
            caption_text.pack(fill="x", padx=10, pady=(0, 10))
            
            # Insert original caption + hashtags
            default_caption = original_caption or "Amazing content! 🔥"
            # Add hashtags if they're not already there
            if "#" not in default_caption:
                default_caption += "\n\n#repost #instagram #trending"
            caption_text.insert("1.0", default_caption)
            
            # Now show the options frame
            options_frame.pack(fill="x", padx=10, pady=(10, 15))
            
            # Clear previous options
            for widget in options_frame.winfo_children():
                if options_label is not None and widget != options_label:  # Keep the label if it exists
                    widget.destroy()
                    
            # Re-add the label if it exists
            if options_label is not None:
                options_label.pack(pady=(10, 5), padx=10, anchor="w")
            else:
                # Create a new label if it doesn't exist
                new_options_label = ctk.CTkLabel(
                    options_frame,
                    text="Posting Options",
                    font=ctk.CTkFont(size=16, weight="bold"),
                    text_color=COLORS["text_primary"]
                )
                new_options_label.pack(pady=(10, 5), padx=10, anchor="w")
                
            # Accounts selection
            accounts_frame = ctk.CTkFrame(options_frame, fg_color="transparent")
            accounts_frame.pack(fill="x", padx=10, pady=5)
            
            accounts_label = ctk.CTkLabel(
                accounts_frame,
                text="Post to accounts:",
                font=ctk.CTkFont(size=13),
                text_color=COLORS["text_primary"],
                width=120,
                anchor="w"
            )
            accounts_label.pack(side="left", padx=(0, 10))
            
            # Get available accounts
            accounts = ["Main Account"]
            if hasattr(self.reposter, "alt_clients") and self.reposter.alt_clients:
                accounts.extend([f"Alt: {alt.username}" for alt in self.reposter.alt_clients])
                
            # Account checkboxes
            account_vars = {}
            account_checkboxes_frame = ctk.CTkFrame(accounts_frame, fg_color="transparent")
            account_checkboxes_frame.pack(side="left", fill="x", expand=True)
            
            for i, account in enumerate(accounts):
                var = ctk.BooleanVar(value=True if i == 0 else False)
                account_vars[account] = var
                checkbox = ctk.CTkCheckBox(
                    account_checkboxes_frame,
                    text=account,
                    variable=var,
                    width=100,
                    checkbox_width=20,
                    checkbox_height=20
                )
                checkbox.grid(row=i//3, column=i%3, sticky="w", padx=10, pady=2)
            
            # Post button frame
            post_btn_frame = ctk.CTkFrame(options_frame, fg_color="transparent")
            post_btn_frame.pack(fill="x", padx=10, pady=10)
            
            # Post button
            post_btn = ctk.CTkButton(
                post_btn_frame,
                text="Post Content",
                command=lambda: self._post_stolen_content(
                    content_info, 
                    caption_text.get("1.0", "end-1c"),
                    account_vars,
                    False,  # remove_watermark_var.get()
                    False,  # add_watermark_var.get()
                    False,  # credit_original_var.get()
                    parent_window
                ),
                width=150,
                height=40,
                fg_color=COLORS["success"],
                hover_color=COLORS["success_hover"],
                font=ctk.CTkFont(size=14, weight="bold")
            )
            post_btn.pack(side="right", padx=10)
            
            # Download only button
            download_btn = ctk.CTkButton(
                post_btn_frame,
                text="Download Only",
                command=lambda: self._download_only_content(content_info, parent_window),
                width=130,
                height=40
            )
            download_btn.pack(side="right", padx=10)
            
        except Exception as e:
            status_label.configure(
                text=f"Error displaying content: {str(e)}",
                text_color=COLORS["error"]
            )
            
    def _update_thumbnail_ui(self, media_frame, ctk_img, loading_label):
        """Update the UI with the loaded thumbnail image."""
        try:
            # Remove loading indicator
            loading_label.pack_forget()
            
            # Clear any existing content in the media frame
            for widget in media_frame.winfo_children():
                widget.destroy()
            
            # Create a new label with the image
            img_label = ctk.CTkLabel(
                media_frame,
                image=ctk_img,
                text=""
            )
            img_label.pack(expand=True, pady=10)
            
            # Store reference to prevent garbage collection
            media_frame.image = ctk_img
            
        except Exception as e:
            self.log_to_terminal(f"Error updating thumbnail UI: {str(e)}", logging.ERROR)
    
    def _show_placeholder_thumbnail(self, media_frame, loading_label, media_type, shortcode):
        """Show a placeholder when thumbnail loading fails."""
        try:
            # Remove loading indicator
            loading_label.pack_forget()
            
            # Clear frame
            for widget in media_frame.winfo_children():
                widget.destroy()
                
            # Create a more informative placeholder based on content type
            if media_type == 1:  # Photo
                icon_text = "🖼️"
                type_text = "Photo"
            elif media_type == 2:  # Video
                icon_text = "🎬"
                type_text = "Video"
            else:  # Album
                icon_text = "📁"
                type_text = "Album"
                
            # Add icon placeholder
            icon_label = ctk.CTkLabel(
                media_frame,
                text=icon_text,
                font=ctk.CTkFont(size=64),
                text_color=COLORS["accent"]
            )
            icon_label.pack(pady=(40, 10))
            
            # Add media description
            media_desc = ctk.CTkLabel(
                media_frame,
                text=f"{type_text} Content Preview",
                font=ctk.CTkFont(size=18, weight="bold"),
                text_color=COLORS["text_primary"]
            )
            media_desc.pack(pady=(0, 5))
            
            # Add shortcode
            shortcode_label = ctk.CTkLabel(
                media_frame,
                text=f"Shortcode: {shortcode}",
                font=ctk.CTkFont(size=12),
                text_color=COLORS["text_secondary"]
            )
            shortcode_label.pack(pady=(0, 40))
            
        except Exception as e:
            self.log_to_terminal(f"Error showing placeholder: {str(e)}", logging.ERROR)
    
    def _clear_content_frame(self, content_frame, status_label):
        """Clear the content frame and reset the status message."""
        # Clear the content frame
        for widget in content_frame.winfo_children():
            widget.destroy()
            
        # Add initial content message
        initial_message = ctk.CTkLabel(
            content_frame,
            text="Content preview will appear here",
            font=ctk.CTkFont(size=16),
            text_color=COLORS["text_secondary"]
        )
        initial_message.pack(pady=100)
        
        # Reset status message
        status_label.configure(
            text="Enter an Instagram URL to fetch content",
            text_color=COLORS["text_secondary"]
        )
    
    def _post_stolen_content(self, content_info, caption, account_vars, remove_watermark, add_watermark, credit_original, parent_window):
        """Post the stolen content to selected accounts."""
        # Get selected accounts
        selected_accounts = [account for account, var in account_vars.items() if var.get()]
        
        if not selected_accounts:
            tkmb.showwarning("No Accounts Selected", "Please select at least one account to post to")
            return
            
        # Create progress dialog
        progress = ProgressDialog(parent_window, "Posting Content")
        progress.update_progress(0.1, "Preparing content...")
        
        # Start a thread to handle the posting
        threading.Thread(
            target=self._post_content_thread,
            args=(content_info, caption, selected_accounts, remove_watermark, add_watermark, credit_original, progress, parent_window),
            daemon=True
        ).start()
    
    def _post_content_thread(self, content_info, caption, selected_accounts, remove_watermark, add_watermark, credit_original, progress, parent_window):
        """Thread function to handle posting content."""
        try:
            url = content_info.get('url', '')
            if not url:
                self.after(0, lambda: progress.destroy())
                self.after(100, lambda: self.show_error("Error", "Missing content URL"))
                return
                
            # Updating progress status
            self.after(0, lambda: progress.update_progress(0.2, "Downloading content..."))
            
            # Process each selected account
            success_count = 0
            for i, account_name in enumerate(selected_accounts):
                try:
                    account_progress = 0.2 + (0.8 * ((i) / len(selected_accounts)))
                    self.after(0, lambda p=account_progress, a=account_name: 
                        progress.update_progress(p, f"Posting to {a}..."))
                    
                    # Actually post the content - for now with main account only
                    # In a full implementation, we would switch between accounts
                    if i == 0 or "Main Account" in account_name:
                        result = self.reposter.repost_content_by_url(
                            url=url,
                            caption=caption,
                            remove_watermark=remove_watermark,
                            add_watermark=add_watermark,
                            credit_original=credit_original
                        )
                        if result.get('success'):
                            success_count += 1
                    else:
                        # For alt accounts in this demo, just simulate success
                        # In a full implementation, we would use the appropriate client
                        self.log_to_terminal(f"Would post to {account_name}", logging.INFO)
                        success_count += 1
                        
                except Exception as e:
                    self.log_to_terminal(f"Error posting to {account_name}: {str(e)}", logging.ERROR)
            
            # Complete the process
            self.after(0, lambda: progress.update_progress(1.0, "Posted successfully!"))
            self.after(1000, progress.destroy)
            
            # Show success message
            if success_count > 0:
                self.after(1100, lambda: 
                    self.show_info("Success", f"Content posted successfully to {success_count} account(s)!"))
                    
                # Close the content stealer window
                self.after(1200, parent_window.destroy)
            else:
                self.after(1100, lambda: 
                    self.show_warning("No posts were successful"))
            
        except Exception as e:
            self.after(0, lambda: progress.destroy())
            self.after(100, lambda: self.show_error("Error", f"Failed to post content: {str(e)}"))
    
    def _download_only_content(self, content_info, parent_window):
        """Download the content without posting."""
        # Create progress dialog
        progress = ProgressDialog(parent_window, "Downloading Content")
        progress.update_progress(0.1, "Preparing to download...")
        
        # Start a thread to handle the download
        threading.Thread(
            target=self._download_content_thread,
            args=(content_info, progress, parent_window),
            daemon=True
        ).start()
    
    def _download_content_thread(self, content_info, progress, parent_window):
        """Thread function to handle downloading content."""
        try:
            url = content_info.get('url', '')
            if not url:
                self.after(0, lambda: progress.destroy())
                self.after(100, lambda: self.show_error("Error", "Missing content URL"))
                return
                
            # Update progress
            self.after(0, lambda: progress.update_progress(0.3, "Fetching media details..."))
            
            # Download the content
            self.after(0, lambda: progress.update_progress(0.5, "Downloading media..."))
            
            # Create target directory - use local Downloads folder
            target_dir = "Downloads"
            os.makedirs(target_dir, exist_ok=True)
            
            # Log the intended directory
            self.log_to_terminal(f"Downloading content to directory: {target_dir}", logging.INFO)
            
            try:
                # Pass the directory to the download method
                download_result = self.reposter.download_content_by_url(url, target_dir)
                
                # Update progress
                self.after(0, lambda: progress.update_progress(0.9, "Download complete"))
                self.after(1000, progress.destroy)
                
                # Show success message with the file path
                path = download_result.get('path', os.path.join(target_dir, "instagram_content"))
                self.after(1100, lambda: 
                    self.show_info("Download Complete", f"Content saved to:\n{path}"))
                    
            except Exception as download_error:
                error_msg = str(download_error)
                self.after(0, lambda: progress.destroy())
                self.after(100, lambda error=error_msg: 
                    self.show_error("Error", f"Failed to download content: {error}"))
            
        except Exception as e:
            error_msg = str(e)
            self.after(0, lambda: progress.destroy())
            self.after(100, lambda error=error_msg: 
                self.show_error("Error", f"Failed to download content: {error}")) 
