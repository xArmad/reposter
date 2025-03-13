"""
Verification dialog component for handling Instagram verification codes.
"""
import customtkinter as ctk
import tkinter.messagebox as tkmb
from utils.constants import COLORS, HAS_CTK_MESSAGEBOX
import time
import logging

# Import CTkMessagebox if available
if HAS_CTK_MESSAGEBOX:
    from CTkMessagebox import CTkMessagebox

class VerificationDialog(ctk.CTkToplevel):
    def __init__(self, parent, username, challenge_type, title=None, message=None, has_cancel=False):
        super().__init__(parent)
        
        self.username = username
        self.challenge_type = challenge_type
        self.custom_title = title
        self.custom_message = message
        self.has_cancel = has_cancel
        
        # Configure dialog
        if self.custom_title:
            self.title(self.custom_title)
        else:
            self.title(f"Verification Required")
        
        self.geometry("400x240")
        self.configure(fg_color=COLORS["bg_medium"])
        
        # Make dialog modal
        self.transient(parent)
        self.grab_set()
        self.focus_set()
        
        # Initialize code
        self.verification_code = None
        
        # Setup UI
        self.setup_ui()

    def setup_ui(self):
        # Center the dialog on parent
        if self.master:
            x = self.master.winfo_rootx() + (self.master.winfo_width() - 400) // 2
            y = self.master.winfo_rooty() + (self.master.winfo_height() - 240) // 2
            self.geometry(f"+{x}+{y}")
        
        # Main container with padding
        container = ctk.CTkFrame(self, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Title
        title_text = self.custom_title if self.custom_title else f"Verification for @{self.username}"
        title = ctk.CTkLabel(
            container,
            text=title_text,
            font=ctk.CTkFont(family="Helvetica", size=16, weight="bold"),
            text_color=COLORS["text_primary"]
        )
        title.pack(pady=(0, 15))
        
        # Message
        if self.custom_message:
            message_text = self.custom_message
        else:
            message_text = f"Instagram is requesting {self.challenge_type} verification.\nPlease enter the code sent to you:"
            
        message = ctk.CTkLabel(
            container,
            text=message_text,
            font=ctk.CTkFont(family="Helvetica", size=12),
            text_color=COLORS["text_secondary"],
            justify="center"
        )
        message.pack(pady=(0, 20))
        
        # Code input
        code_frame = ctk.CTkFrame(container, fg_color="transparent")
        code_frame.pack(pady=(0, 20))
        
        # Code label
        code_label = ctk.CTkLabel(
            code_frame,
            text="Code:",
            font=ctk.CTkFont(family="Helvetica", size=12),
            text_color=COLORS["text_primary"]
        )
        code_label.pack(side="left", padx=(0, 10))
        
        # Code entry
        self.code_var = ctk.StringVar()
        code_entry = ctk.CTkEntry(
            code_frame,
            textvariable=self.code_var,
            width=200
        )
        code_entry.pack(side="left")
        code_entry.focus_set()
        
        # Buttons container
        btn_frame = ctk.CTkFrame(container, fg_color="transparent")
        btn_frame.pack(pady=(10, 0), fill="x")
        
        # Submit button
        submit_btn = ctk.CTkButton(
            btn_frame,
            text="Submit",
            command=self.submit_code,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            width=100
        )
        submit_btn.pack(side="right", padx=5)
        
        # Cancel button if requested
        if self.has_cancel:
            cancel_btn = ctk.CTkButton(
                btn_frame,
                text="Cancel",
                command=self.cancel,
                fg_color=COLORS["bg_dark"],
                hover_color=COLORS["bg_light"],
                width=100
            )
            cancel_btn.pack(side="right", padx=5)
        
        # Bind enter key to submit
        self.bind("<Return>", lambda event: self.submit_code())

    def submit_code(self):
        code = self.code_var.get().strip()
        if not code or len(code) != 6 or not code.isdigit():
            if HAS_CTK_MESSAGEBOX:
                CTkMessagebox(self, title="Error", message="Please enter a valid 6-digit code", icon="cancel")
            else:
                tkmb.showerror("Error", "Please enter a valid 6-digit code")
            return
            
        self.verification_code = code
        self.destroy()
        
    def cancel(self):
        self.verification_code = None
        self.destroy()
        
    @staticmethod
    def show_dialog(parent, username, challenge_type, title=None, message=None, has_cancel=False):
        """Show a verification dialog and wait for the result.
        
        Args:
            parent: The parent window
            username: The Instagram username
            challenge_type: The type of verification challenge
            title: Optional custom title
            message: Optional custom message
            has_cancel: Whether to include a cancel button
            
        Returns:
            str: The verification code entered by the user, or None if cancelled
        """
        try:
            # Create dialog and make sure it's displayed
            dialog = VerificationDialog(parent, username, challenge_type, title, message, has_cancel)
            
            # Use a more robust waiting approach that doesn't rely on the window path
            try:
                dialog.wait_window()
            except Exception as e:
                # If wait_window fails, use a polling approach
                logging.warning(f"wait_window failed, using polling approach: {str(e)}")
                while dialog.winfo_exists():
                    parent.update()
                    time.sleep(0.1)
            
            return dialog.verification_code
        except Exception as e:
            logging.error(f"Error showing verification dialog: {str(e)}")
            # Fallback to a simple text entry dialog
            if HAS_CTK_MESSAGEBOX:
                from CTkMessagebox import CTkInputDialog
                result = CTkInputDialog(
                    title=f"Verification for {username}",
                    text=f"Enter the verification code sent via {challenge_type}:",
                ).get_input()
                return result
            else:
                return tkmb.askstring(
                    f"Verification for {username}",
                    f"Enter the verification code sent via {challenge_type}:"
                ) 