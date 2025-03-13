"""
Constants used throughout the application.
"""

# Define custom colors for modern UI
COLORS = {
    "bg_dark": "#1a1a1a",
    "bg_darker": "#151515",  # Even darker background for inputs
    "bg_medium": "#2a2a2a",
    "bg_light": "#333333",
    "text_primary": "#ffffff",
    "text_secondary": "#aaaaaa",
    "accent": "#3498db",
    "accent_hover": "#2980b9",
    "success": "#2ecc71",
    "success_hover": "#27ae60",
    "warning": "#f39c12",
    "warning_hover": "#e67e22",
    "danger": "#e74c3c",
    "danger_hover": "#c0392b",
    "error": "#e74c3c",
    "card_border": "#444444"
}

# Flag for CTkMessagebox availability
try:
    from CTkMessagebox import CTkMessagebox
    HAS_CTK_MESSAGEBOX = True
except ImportError:
    HAS_CTK_MESSAGEBOX = False 