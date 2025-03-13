"""
Settings dialog component for the Instagram Repost tool.
"""
import customtkinter as ctk
import json
import tkinter.messagebox as tkmb
from utils.constants import HAS_CTK_MESSAGEBOX

# Import CTkMessagebox if available
if HAS_CTK_MESSAGEBOX:
    from CTkMessagebox import CTkMessagebox

class SettingsDialog(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Settings")
        self.geometry("400x500")
        
        # Load settings
        self.settings = self.load_settings()
        
        # Create UI
        self.setup_ui()
        
    def setup_ui(self):
        # Auto-repost settings
        auto_frame = ctk.CTkFrame(self)
        auto_frame.pack(fill="x", padx=20, pady=10)
        
        ctk.CTkLabel(auto_frame, text="Auto-Repost Settings", 
                    font=ctk.CTkFont(size=16, weight="bold")).pack(pady=5)
        
        self.interval_var = ctk.StringVar(value=str(self.settings.get("auto_repost_interval", 5)))
        interval_frame = ctk.CTkFrame(auto_frame)
        interval_frame.pack(fill="x", padx=10, pady=5)
        ctk.CTkLabel(interval_frame, text="Check interval (minutes):").pack(side="left", padx=5)
        ctk.CTkEntry(interval_frame, textvariable=self.interval_var, width=50).pack(side="right", padx=5)
        
        # Appearance settings
        appearance_frame = ctk.CTkFrame(self)
        appearance_frame.pack(fill="x", padx=20, pady=10)
        
        ctk.CTkLabel(appearance_frame, text="Appearance", 
                    font=ctk.CTkFont(size=16, weight="bold")).pack(pady=5)
        
        theme_frame = ctk.CTkFrame(appearance_frame)
        theme_frame.pack(fill="x", padx=10, pady=5)
        ctk.CTkLabel(theme_frame, text="Theme:").pack(side="left", padx=5)
        theme_menu = ctk.CTkOptionMenu(theme_frame, values=["dark", "light", "system"],
                                     command=self.change_theme)
        theme_menu.pack(side="right", padx=5)
        theme_menu.set(self.settings.get("theme", "dark"))
        
        # Save button
        ctk.CTkButton(self, text="Save Settings", 
                     command=self.save_settings).pack(pady=20)
        
    def change_theme(self, theme):
        ctk.set_appearance_mode(theme)
        self.settings["theme"] = theme
        
    def load_settings(self):
        try:
            with open("settings.json", "r") as f:
                return json.load(f)
        except:
            return {"auto_repost_interval": 5, "theme": "dark"}
            
    def save_settings(self):
        try:
            self.settings["auto_repost_interval"] = int(self.interval_var.get())
            with open("settings.json", "w") as f:
                json.dump(self.settings, f)
            self.destroy()
        except ValueError:
            self.show_error("Invalid interval value")
            
    def show_error(self, message):
        if HAS_CTK_MESSAGEBOX:
            CTkMessagebox(self, title="Error", message=message, icon="cancel")
        else:
            tkmb.showerror("Error", message) 