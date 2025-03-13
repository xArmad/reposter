"""
Account management dialog component for managing Instagram accounts in the Instagram Repost tool.
"""
import os
import tkinter as tk
import tkinter.messagebox as tkmb
import customtkinter as ctk
import logging
from PIL import Image, ImageTk
import threading
from utils.constants import COLORS
from components.progress_dialog import ProgressDialog
from instagram_utils import InstagramReposter, IPBlacklistError

class AccountManagementDialog(ctk.CTkToplevel):
    _instance = None
    
    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(AccountManagementDialog, cls).__new__(cls)
        return cls._instance
        
    def __init__(self, parent, reposter):
        if not hasattr(self, 'initialized'):
            super().__init__(parent)
            self.initialized = True
            self.title("Account Management")
            self.geometry("700x750")
            self.configure(fg_color=COLORS["bg_medium"])
            
            # Make dialog appear on top
            self.transient(parent)  # Set parent window
            self.grab_set()  # Make window modal
            
            # Ensure it appears on top on Windows
            self.attributes('-topmost', True)
            
            self.reposter = reposter
            self.parent = parent
            
            # Set this dialog as the parent for the reposter's verification dialogs
            if self.reposter:
                self.reposter.parent = self
            
            # Configure grid
            self.grid_columnconfigure(0, weight=1)
            self.grid_rowconfigure(1, weight=1)
            
            self.setup_ui()
            
            # Bind the close event
            self.protocol("WM_DELETE_WINDOW", self.on_close)
            
            # After setup, lift window and force focus
            self.after(100, self._ensure_on_top)
        
        # Always update these even if already initialized
        self.reposter = reposter
        self.parent = parent
        self.load_accounts()
        self.lift()  # Bring window to front
        self.focus_force()  # Force focus
        
    def _ensure_on_top(self):
        """Ensure window is on top after initialization."""
        self.lift()  # Bring window to front
        self.focus_force()  # Force focus
        self.attributes('-topmost', False)  # Disable always on top after showing
        
    def on_close(self):
        """Handle window close event."""
        AccountManagementDialog._instance = None
        self.destroy()
        
    def setup_ui(self):
        # Main container with padding
        container = ctk.CTkFrame(self, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=30, pady=30)
        container.grid_columnconfigure(0, weight=1)
        container.grid_rowconfigure(1, weight=1)
        
        # Title
        title = ctk.CTkLabel(
            container,
            text="Instagram Account Management",
            font=ctk.CTkFont(family="Helvetica", size=24, weight="bold"),
            text_color=COLORS["text_primary"]
        )
        title.grid(row=0, column=0, pady=20, padx=20, sticky="ew")
        
        # Main container
        main_frame = ctk.CTkFrame(container, fg_color=COLORS["bg_light"], corner_radius=15)
        main_frame.grid(row=1, column=0, sticky="nsew", padx=0, pady=(0, 20))
        main_frame.grid_columnconfigure(0, weight=1)
        main_frame.grid_rowconfigure(1, weight=1)
        
        # Add account section
        add_frame = ctk.CTkFrame(main_frame, fg_color=COLORS["bg_medium"], corner_radius=10)
        add_frame.grid(row=0, column=0, sticky="ew", padx=20, pady=20)
        
        add_title = ctk.CTkLabel(
            add_frame, 
            text="Add New Account", 
            font=ctk.CTkFont(family="Helvetica", size=16, weight="bold"),
            text_color=COLORS["text_primary"]
        )
        add_title.pack(pady=(15, 10))
        
        # Username/password entries
        entry_frame = ctk.CTkFrame(add_frame, fg_color="transparent")
        entry_frame.pack(fill="x", padx=20, pady=10)
        
        self.username_var = ctk.StringVar()
        self.password_var = ctk.StringVar()
        
        # Username entry with label
        username_container = ctk.CTkFrame(entry_frame, fg_color="transparent")
        username_container.pack(side="left", fill="both", expand=True, padx=5)
        
        ctk.CTkLabel(
            username_container,
            text="Username",
            font=ctk.CTkFont(family="Helvetica", size=12),
            text_color=COLORS["text_secondary"],
            anchor="w"
        ).pack(fill="x", pady=(0, 5))
        
        username_entry = ctk.CTkEntry(
            username_container, 
            placeholder_text="Enter Instagram username",
            textvariable=self.username_var,
            height=40,
            corner_radius=8,
            border_width=0,
            fg_color=COLORS["bg_dark"],
            text_color=COLORS["text_primary"],
            font=ctk.CTkFont(family="Helvetica", size=13)
        )
        username_entry.pack(fill="x")
        
        # Password entry with label
        password_container = ctk.CTkFrame(entry_frame, fg_color="transparent")
        password_container.pack(side="left", fill="both", expand=True, padx=5)
        
        ctk.CTkLabel(
            password_container,
            text="Password",
            font=ctk.CTkFont(family="Helvetica", size=12),
            text_color=COLORS["text_secondary"],
            anchor="w"
        ).pack(fill="x", pady=(0, 5))
        
        password_entry = ctk.CTkEntry(
            password_container,
            placeholder_text="Enter password",
            textvariable=self.password_var,
            show="•",
            height=40,
            corner_radius=8,
            border_width=0,
            fg_color=COLORS["bg_dark"],
            text_color=COLORS["text_primary"],
            font=ctk.CTkFont(family="Helvetica", size=13)
        )
        password_entry.pack(fill="x")
        
        # Button container
        btn_frame = ctk.CTkFrame(add_frame, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=(10, 15))
        
        ctk.CTkButton(
            btn_frame,
            text="Add Account",
            command=self.add_account,
            height=40,
            corner_radius=8,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            text_color=COLORS["text_primary"],
            font=ctk.CTkFont(family="Helvetica", size=14, weight="bold")
        ).pack(side="left", padx=5, expand=True, fill="x")
        
        # Accounts list
        list_frame = ctk.CTkFrame(main_frame, fg_color=COLORS["bg_medium"], corner_radius=10)
        list_frame.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 20))
        list_frame.grid_columnconfigure(0, weight=1)
        list_frame.grid_rowconfigure(1, weight=1)
        
        ctk.CTkLabel(
            list_frame,
            text="Managed Accounts",
            font=ctk.CTkFont(family="Helvetica", size=16, weight="bold"),
            text_color=COLORS["text_primary"]
        ).grid(row=0, column=0, pady=15)
        
        # Scrollable account list
        self.accounts_frame = ctk.CTkScrollableFrame(
            list_frame,
            fg_color=COLORS["bg_dark"],
            corner_radius=8
        )
        self.accounts_frame.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 20))
        self.accounts_frame.grid_columnconfigure(0, weight=1)
        
    def load_accounts(self):
        """Load accounts from the reposter."""
        # Clear frame
        for widget in self.accounts_frame.winfo_children():
            widget.destroy()
            
        # Get accounts
        if self.reposter:
            accounts = self.reposter.get_accounts()
            
            # Process accounts - the API returns a list, not a dictionary
            if accounts and len(accounts) > 0:
                # First account is treated as main if it exists
                main_found = False
                for i, account in enumerate(accounts):
                    # Check if this is the main account from the config
                    is_main = (self.reposter.config.get("main_account") and 
                              self.reposter.config["main_account"] and
                              account["username"] == self.reposter.config["main_account"].get("username"))
                    
                    if is_main:
                        main_found = True
                        self._add_account_row(account, is_main=True)
                    else:
                        self._add_account_row(account, is_main=False)
                
                # Show a message if no accounts are available
                if not main_found and len(accounts) == 0:
                    no_accounts_label = ctk.CTkLabel(
                        self.accounts_frame,
                        text="No accounts configured",
                        text_color=COLORS["text_secondary"]
                    )
                    no_accounts_label.pack(pady=20)
            else:
                # Show a message if no accounts are available
                no_accounts_label = ctk.CTkLabel(
                    self.accounts_frame,
                    text="No accounts configured",
                    text_color=COLORS["text_secondary"]
                )
                no_accounts_label.pack(pady=20)
                
    def _add_account_row(self, account, is_main):
        """Add an account row to the account list."""
        account_card = ctk.CTkFrame(
            self.accounts_frame,
            fg_color=COLORS["bg_medium"],
            corner_radius=8,
            height=80
        )
        account_card.pack(fill="x", pady=5, padx=5)
        account_card.pack_propagate(False)
        
        # Account info container
        info_frame = ctk.CTkFrame(account_card, fg_color="transparent")
        info_frame.pack(side="left", fill="both", expand=True, padx=15, pady=10)
        
        # Username with bold font and main account badge if applicable
        username_container = ctk.CTkFrame(info_frame, fg_color="transparent")
        username_container.pack(anchor="w", fill="x")
        
        username_label = ctk.CTkLabel(
            username_container,
            text=account.get("username", "Unknown"),
            font=ctk.CTkFont(family="Helvetica", size=14, weight="bold"),
            text_color=COLORS["text_primary"],
            anchor="w"
        )
        username_label.pack(side="left")
        
        # Add "MAIN" badge if this is the main account
        if is_main:
            main_badge = ctk.CTkLabel(
                username_container,
                text="MAIN",
                font=ctk.CTkFont(family="Helvetica", size=10, weight="bold"),
                text_color=COLORS["bg_dark"],
                bg_color="transparent",
                fg_color=COLORS["accent"],
                corner_radius=4,
                width=40,
                height=16
            )
            main_badge.pack(side="left", padx=10)
        
        # Status indicator
        status_text = "Connected" if account.get("is_logged_in", False) else "Disconnected"
        status_color = COLORS["success"] if account.get("is_logged_in", False) else COLORS["warning"]
        
        status_frame = ctk.CTkFrame(info_frame, fg_color="transparent", height=25)
        status_frame.pack(fill="x", pady=(5, 0))
        
        status_indicator = ctk.CTkFrame(
            status_frame,
            width=8,
            height=8,
            corner_radius=4,
            fg_color=status_color
        )
        status_indicator.pack(side="left", padx=(0, 5))
        
        status_label = ctk.CTkLabel(
            status_frame,
            text=status_text,
            font=ctk.CTkFont(family="Helvetica", size=12),
            text_color=COLORS["text_secondary"],
            anchor="w"
        )
        status_label.pack(side="left", fill="x")
        
        # Action buttons container
        btn_container = ctk.CTkFrame(account_card, fg_color="transparent")
        btn_container.pack(side="right", fill="y", padx=10)
        
        # Connect button
        connect_btn = ctk.CTkButton(
            btn_container,
            text="Connect" if not account.get("is_logged_in", False) else "Disconnect",
            command=lambda acc=account: self.toggle_connection(acc),
            width=100,
            height=26,
            corner_radius=6,
            fg_color=COLORS["accent"] if not account.get("is_logged_in", False) else COLORS["bg_dark"],
            hover_color=COLORS["accent_hover"] if not account.get("is_logged_in", False) else COLORS["bg_light"],
            text_color=COLORS["text_primary"],
            font=ctk.CTkFont(family="Helvetica", size=12)
        )
        connect_btn.pack(side="top", pady=2)
        
        # Load Posts button (only show for connected accounts)
        if account.get("is_logged_in", False):
            load_posts_btn = ctk.CTkButton(
                btn_container,
                text="Load Posts",
                command=lambda acc=account: self.load_posts(acc),
                width=100,
                height=26,
                corner_radius=6,
                fg_color=COLORS["success"],
                hover_color="#1e7c3a",  # Darker green
                text_color=COLORS["text_primary"],
                font=ctk.CTkFont(family="Helvetica", size=12)
            )
            load_posts_btn.pack(side="top", pady=2)
        
        # Set as main account button (only for non-main accounts)
        if not is_main:
            set_main_btn = ctk.CTkButton(
                btn_container,
                text="Set as Main",
                command=lambda acc=account: self.set_as_main(acc),
                width=100,
                height=26,
                corner_radius=6,
                fg_color=COLORS["bg_light"],
                hover_color=COLORS["accent_hover"],
                text_color=COLORS["text_primary"],
                font=ctk.CTkFont(family="Helvetica", size=12)
            )
            set_main_btn.pack(side="top", pady=2)
        
        # Remove button
        remove_btn = ctk.CTkButton(
            btn_container,
            text="Remove",
            command=lambda acc=account: self.remove_account(acc),
            width=100,
            height=26,
            corner_radius=6,
            fg_color=COLORS["danger"],
            hover_color=COLORS["danger_hover"],
            text_color=COLORS["text_primary"],
            font=ctk.CTkFont(family="Helvetica", size=12)
        )
        remove_btn.pack(side="bottom", pady=2)
        
    def toggle_connection(self, account):
        """Toggle the connection status of an account."""
        username = account.get("username", "")
        
        if account.get("is_logged_in", False):
            # Disconnect the account
            try:
                self.reposter.disconnect_account(username)
                tkmb.showinfo("Success", f"Account '{username}' disconnected")
                self.load_accounts()
            except Exception as e:
                tkmb.showerror("Error", f"Failed to disconnect account: {str(e)}")
        else:
            # Connect the account
            try:
                success = self.reposter.connect_account(username)
                if success:
                    tkmb.showinfo("Success", f"Account '{username}' connected")
                    self.load_accounts()
                    
                    # Check if this is the main account and update parent window status if needed
                    is_main = (self.reposter.config.get("main_account") and 
                              self.reposter.config["main_account"] and
                              username == self.reposter.config["main_account"].get("username"))
                    
                    # Update main window connection status if this was the main account
                    if is_main and hasattr(self.parent, 'refresh_connection_status'):
                        self.parent.after(100, self.parent.refresh_connection_status)
                else:
                    tkmb.showerror("Error", f"Failed to connect to account '{username}'")
            except IPBlacklistError as e:
                self._show_ip_blacklist_error(str(e))
            except Exception as e:
                tkmb.showerror("Error", f"Failed to connect account: {str(e)}")
                
    def load_posts(self, account):
        """Load posts for a connected account."""
        username = account.get("username", "")
        
        # Check if this is an alt account
        is_main = (
            self.reposter.config.get("main_account") and 
            username == self.reposter.config["main_account"].get("username")
        )
        
        # For main account, refresh posts in the main app
        if is_main and self.parent:
            if hasattr(self.parent, "refresh_posts"):
                self.parent.refresh_posts()
        # For alt accounts, update repost statuses in the main app
        elif not is_main and self.parent:
            # Signal the parent app to update repost statuses
            if hasattr(self.parent, "update_repost_statuses"):
                self.after(100, self.parent.update_repost_statuses)
        
    def remove_account(self, account):
        """Remove an account from the list."""
        username = account.get("username", "")
        
        # Extra confirmation for main account
        is_main = self.reposter.config.get("main_account") and self.reposter.config["main_account"] and username == self.reposter.config["main_account"].get("username")
        
        if is_main:
            confirm = tkmb.askyesno(
                "Confirm Main Account Removal", 
                f"Warning: {username} is currently set as your main account.\n\n"
                f"Removing it will disconnect all accounts and reset your configuration.\n\n"
                f"Are you sure you want to remove this account?",
                icon="warning"
            )
        else:
            # Standard confirmation for alt account
            confirm = tkmb.askyesno(
                "Confirm Removal", 
                f"Are you sure you want to remove the account '{username}'?"
            )
        
        if confirm and self.reposter:
            try:
                if self.reposter.remove_account(username):
                    if is_main:
                        tkmb.showinfo(
                            "Account Removed", 
                            f"Main account '{username}' has been removed.\n\n"
                            f"Please connect a new main account to continue using the application."
                        )
                    else:
                        tkmb.showinfo("Account Removed", f"Account '{username}' has been removed.")
                else:
                    tkmb.showerror("Error", f"Failed to remove account '{username}'.")
            except Exception as e:
                tkmb.showerror("Error", f"Failed to remove account: {str(e)}")
            finally:
                self.load_accounts()
            
    def add_account(self):
        """Add an account to the configuration."""
        username = self.username_var.get().strip()
        password = self.password_var.get()
        
        # Validate inputs
        if not username or not password:
            tkmb.showerror("Error", "Username and password are required")
            return
            
        if self.reposter:
            # Check if this is the first account (auto-set as main)
            is_first_account = len(self.reposter.get_accounts()) == 0
            
            try:
                # Add the account
                result = self.reposter.add_account(username, password)
                
                if result:
                    # If this is the first account, set it as main
                    if is_first_account:
                        try:
                            self.reposter.set_main_account(username)
                            tkmb.showinfo("Success", f"Account '{username}' added successfully as main account")
                        except IPBlacklistError as e:
                            self._show_ip_blacklist_error(str(e))
                    else:
                        tkmb.showinfo("Success", f"Account '{username}' added successfully")
                    
                    self.username_var.set("")
                    self.password_var.set("")
                    self.load_accounts()
                else:
                    tkmb.showerror("Error", f"Failed to add account '{username}'")
            except IPBlacklistError as e:
                self._show_ip_blacklist_error(str(e))
                
    def set_as_main(self, account):
        """Set an account as the main account."""
        username = account.get("username", "")
        
        # Ask for confirmation
        confirm = tkmb.askyesno(
            "Set as Main Account", 
            f"Are you sure you want to set '{username}' as your main account?\n\n"
            f"The main account is used to browse content."
        )
        
        if confirm and self.reposter:
            try:
                # Actually set as main
                self.reposter.set_main_account(username)
                
                # Refresh the accounts list
                self.load_accounts()
                
                # Update main window connection status
                if hasattr(self.parent, 'refresh_connection_status'):
                    self.parent.after(100, self.parent.refresh_connection_status)
                
                tkmb.showinfo("Success", f"'{username}' is now the main account")
            except IPBlacklistError as e:
                self._show_ip_blacklist_error(str(e))
            except Exception as e:
                tkmb.showerror("Error", f"Failed to set as main account: {str(e)}")
                
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
                self.master.quit()
                
    def test_connection(self, username, password):
        """Test connection with provided credentials."""
        if not username or not password:
            tkmb.showerror("Error", "Username and password are required")
            return
            
        if self.reposter:
            # Show progress dialog
            progress = ProgressDialog(self, "Testing Connection")
            progress.update_progress(0, "Initializing...")
            
            def test_task():
                try:
                    # Update progress
                    progress.update_progress(30, "Connecting to Instagram...")
                    
                    # Test connection
                    result, message = self.reposter.test_connection(username, password)
                    
                    # Update progress
                    progress.update_progress(100, "Connection test completed")
                    
                    # Close progress dialog
                    progress.destroy()
                    
                    # Show result
                    if result:
                        tkmb.showinfo("Success", "Connection successful")
                    else:
                        tkmb.showerror("Error", f"Connection failed: {message}")
                except Exception as e:
                    progress.destroy()
                    tkmb.showerror("Error", f"An error occurred: {str(e)}")
                    
            # Run test in a separate thread
            threading.Thread(target=test_task, daemon=True).start() 