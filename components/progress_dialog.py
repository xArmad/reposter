"""
Progress dialog component for displaying progress during operations in the Instagram Repost tool.
"""
import customtkinter as ctk
from utils.constants import COLORS

class ProgressDialog(ctk.CTkToplevel):
    def __init__(self, parent, title="Progress"):
        super().__init__(parent)
        self.title(title)
        self.geometry("350x180")
        self.configure(fg_color=COLORS["bg_medium"])
        
        # Make dialog modal and on top
        self.transient(parent)
        self.grab_set()
        self.attributes('-topmost', True)
        
        self.progress_var = ctk.DoubleVar()
        self.setup_ui()
        
        # Bind close button to cancel
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        
    def on_close(self):
        """Handle window close event."""
        self.grab_release()
        self.destroy()
        
    def setup_ui(self):
        # Center the dialog on parent
        self.update_idletasks()
        parent = self.master
        x = parent.winfo_x() + (parent.winfo_width() - self.winfo_width()) // 2
        y = parent.winfo_y() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")
        
        # Main container with padding
        container = ctk.CTkFrame(self, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Title
        title_label = ctk.CTkLabel(
            container, 
            text=self.title(),
            font=ctk.CTkFont(family="Helvetica", size=18, weight="bold"),
            text_color=COLORS["text_primary"]
        )
        title_label.pack(pady=(0, 15))
        
        # Status text
        self.status_label = ctk.CTkLabel(
            container, 
            text="Processing...",
            font=ctk.CTkFont(family="Helvetica", size=14),
            text_color=COLORS["text_secondary"]
        )
        self.status_label.pack(pady=10)
        
        # Progress bar
        self.progressbar = ctk.CTkProgressBar(
            container,
            height=12,
            corner_radius=6,
            fg_color=COLORS["bg_light"],
            progress_color=COLORS["accent"]
        )
        self.progressbar.pack(pady=15, fill="x")
        self.progressbar.set(0)
        
    def update_progress(self, value, status=None):
        if not self.winfo_exists():
            return
            
        try:
            self.progressbar.set(value)
            if status:
                self.status_label.configure(text=status)
        except Exception:
            pass  # Handle case where dialog is being destroyed 