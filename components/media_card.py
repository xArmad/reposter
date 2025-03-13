"""
MediaCard component for displaying media items in the Instagram Repost tool.
"""
import customtkinter as ctk
import tkinter as tk
from PIL import Image
import threading
import concurrent.futures
import logging
import io
import requests
import time
from utils.constants import COLORS

class MediaCard(ctk.CTkFrame):
    # Create a thread pool for thumbnail loading (shared across all cards)
    _thumbnail_executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)  # Reduced from 4 to 2
    # Add a class-level cache for thumbnails to avoid duplicate downloads
    _thumbnail_cache = {}
    _cache_lock = threading.Lock()
    
    # Add a class variable to track active thumbnail loads
    _active_loads = 0
    _active_loads_lock = threading.Lock()
    
    # Maximum concurrent thumbnail loads
    _max_concurrent_loads = 1  # Reduced from 2 to 1
    
    def __init__(self, parent, media, reposter, on_select=None, **kwargs):
        super().__init__(parent, **kwargs)
        
        self.parent = parent
        self.media = media
        self.reposter = reposter
        self.on_select = on_select
        self.selected = False
        self.thumbnail_image = None
        self.thumbnail_future = None
        self._thumbnail_loaded = False
        self._hover = False
        
        # Set up UI
        self.setup_ui()
        
        # Bind events
        self._bind_click_events()
        
        # Check repost status
        self.reposted_to = []
        
        # Defer thumbnail loading and repost status check to prevent UI freezing
        self.after(100, self.load_thumbnail)
        self.after(200, self.check_repost_status)
        
        # Set up a timeout for thumbnail loading
        def check_thumbnail_timeout():
            if not self._thumbnail_loaded and self.winfo_exists():
                self.thumb_label.configure(text="Timeout", font=("Segoe UI", 12))
                
        # Check thumbnail timeout after 10 seconds
        self.after(10000, check_thumbnail_timeout)
        
    def setup_ui(self):
        # Main layout is a grid with rows for thumbnail, info/stats, caption, and repost status
        self.columnconfigure(0, weight=1)
        self.rowconfigure((0, 1, 2, 3), weight=0)
        
        # 1. Thumbnail container - SMALLER SIZE
        self.thumb_container = ctk.CTkFrame(
            self,
            fg_color=COLORS["bg_medium"],
            width=140,  # Reduced from 180
            height=140,  # Reduced from 180
            corner_radius=8   # Reduced from 12
        )
        self.thumb_container.grid(row=0, column=0, sticky="nsew", padx=8, pady=(8, 4))  # Reduced padding
        self.thumb_container.grid_propagate(False)
        
        # Thumbnail
        self.thumb_label = ctk.CTkLabel(
            self.thumb_container,
            text="",
            width=140,  # Reduced from 180
            height=140   # Reduced from 180
        )
        self.thumb_label.place(relx=0.5, rely=0.5, anchor="center")
        
        # Selection overlay (initially hidden)
        self.selection_overlay = ctk.CTkFrame(
            self.thumb_container,
            fg_color=COLORS["accent"],  # Remove the alpha transparency
            corner_radius=8,   # Reduced from 12
            width=140,         # Reduced from 180
            height=140,        # Reduced from 180
            border_width=3,    # Border width
            border_color=COLORS["accent"]
        )
        self.selection_overlay.place(relx=0.5, rely=0.5, anchor="center")
        
        # Make the overlay semi-transparent using configure
        self.selection_overlay.configure(fg_color=COLORS["bg_dark"])
        
        # Selection checkmark
        self.checkmark = ctk.CTkLabel(
            self.selection_overlay,
            text="✓",
            font=("Segoe UI", 40, "bold"),
            text_color="#ffffff"
        )
        self.checkmark.place(relx=0.5, rely=0.5, anchor="center")
        
        # Add additional selection indicator with badge in corner
        self.selection_badge = ctk.CTkLabel(
            self.selection_overlay,
            text="",
            width=24,
            height=24,
            corner_radius=12,
            fg_color=COLORS["accent"],
            text_color="#ffffff",
            font=("Segoe UI", 12, "bold")
        )
        self.selection_badge.place(relx=0.92, rely=0.08, anchor="center")
        
        # Hide the selection elements initially
        self.selection_overlay.lower()
        self.checkmark.lower()
        self.selection_badge.lower()
        
        # 2. Info strip - contains media type and stats
        info_strip = ctk.CTkFrame(
            self,
            fg_color=COLORS["bg_medium"],
            corner_radius=6,  # Reduced from 8
            height=30         # Reduced from 40
        )
        info_strip.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 4))  # Reduced padding
        info_strip.grid_propagate(False)
        
        # Media type indicator (left side)
        type_label = ctk.CTkLabel(
            info_strip,
            text="🎥" if self.media.media_type == 2 else "📷",
            font=("Segoe UI", 14),  # Reduced from 16
            fg_color=COLORS["bg_dark"],
            corner_radius=8,  # Reduced from 10
            width=24,         # Reduced from 30
            height=24,        # Reduced from 30
            text_color=COLORS["text_primary"]
        )
        type_label.grid(row=0, column=0, padx=4, pady=3, sticky="w")  # Reduced padding
        
        # Stats in the center/right
        if self.media.media_type == 2:  # Video
            # Set up a 3-column grid layout for the info strip
            info_strip.columnconfigure(0, weight=1)  # Media type icon
            info_strip.columnconfigure(1, weight=0)  # Likes
            info_strip.columnconfigure(2, weight=0)  # Views
            
            # Likes with icon
            likes = getattr(self.media, 'like_count', 0) or 0
            likes_frame = ctk.CTkFrame(info_strip, fg_color="transparent")
            likes_frame.grid(row=0, column=1, sticky="e", padx=(0, 4), pady=3)  # Reduced padding
            
            likes_icon = ctk.CTkLabel(
                likes_frame,
                text="❤️",
                font=("Segoe UI", 12),  # Reduced from 14
                text_color=COLORS["text_primary"]
            )
            likes_icon.pack(side="left", padx=(0, 1))
            
            likes_count = ctk.CTkLabel(
                likes_frame,
                text=f"{likes:,}",
                font=ctk.CTkFont(family="Helvetica", size=10, weight="bold"),  # Reduced from 12
                text_color=COLORS["text_primary"]
            )
            likes_count.pack(side="left")
        else:
            # For photos, just show likes - configure the grid for 2 columns
            info_strip.columnconfigure(0, weight=1)  # Media type icon
            info_strip.columnconfigure(1, weight=0)  # Likes
            
            # For photos, just show likes
            likes = getattr(self.media, 'like_count', 0) or 0
            
            likes_frame = ctk.CTkFrame(info_strip, fg_color="transparent")
            likes_frame.grid(row=0, column=1, sticky="e", padx=(0, 8), pady=5)
            
            likes_icon = ctk.CTkLabel(
                likes_frame,
                text="❤️",
                font=("Segoe UI", 14),
                text_color=COLORS["text_primary"]
            )
            likes_icon.pack(side="left", padx=(0, 1))
            
            likes_count = ctk.CTkLabel(
                likes_frame,
                text=f"{likes:,}",
                font=ctk.CTkFont(family="Helvetica", size=12, weight="bold"),
                text_color=COLORS["text_primary"]
            )
            likes_count.pack(side="left")

        # 3. Caption area
        caption_container = ctk.CTkFrame(
            self,
            fg_color=COLORS["bg_medium"],
            corner_radius=6,  # Reduced from 8
            height=40        # Reduced from 60
        )
        caption_container.grid(row=2, column=0, sticky="ew", padx=8, pady=(0, 4))  # Reduced padding
        caption_container.grid_propagate(False)  # Prevent resizing based on content
        
        # Get caption text or placeholder
        caption_text = getattr(self.media, 'caption_text', None) or "No caption"
        
        # Truncate caption if too long to ensure consistent display
        if len(caption_text) > 80:  # Reduced from 100
            caption_text = caption_text[:77] + "..."  # Reduced from 97
        
        # Caption label
        caption_label = ctk.CTkLabel(
            caption_container,
            text=caption_text,
            font=ctk.CTkFont(family="Helvetica", size=10),  # Reduced from 11
            text_color=COLORS["text_secondary"],
            wraplength=120,  # Reduced from 160
            justify="left",
            anchor="w"
        )
        caption_label.pack(fill="both", expand=True, padx=8, pady=4)  # Reduced padding
        
        # 4. Repost status container - at the bottom with fixed height
        self.repost_container = ctk.CTkFrame(
            self,
            fg_color=COLORS["bg_medium"],
            corner_radius=6,  # Reduced from 8
            height=24         # Reduced from 30
        )
        self.repost_container.grid(row=3, column=0, sticky="ew", padx=8, pady=(0, 8))  # Reduced padding
        self.repost_container.grid_propagate(False)  # Prevent resizing based on content
        
        # Initialize with default status
        status_label = ctk.CTkLabel(
            self.repost_container,
            text="Not reposted",
            font=ctk.CTkFont(family="Helvetica", size=10),  # Reduced from 11
            text_color=COLORS["text_secondary"]
        )
        status_label.pack(side="left", padx=8, pady=2)  # Reduced padding
        
        # Bind click events to all elements
        self._bind_click_events()
        
        # Add hover effect
        self.bind("<Enter>", self._on_hover_enter)
        self.bind("<Leave>", self._on_hover_leave)
        
    def _on_hover_enter(self, event):
        """Add hover effect to the card"""
        if not self.selected:
            # Use a stronger hover effect
            self.configure(border_color=COLORS["accent"], border_width=2)
            
    def _on_hover_leave(self, event):
        """Remove hover effect from the card"""
        if not self.selected:
            # Restore normal appearance
            self.configure(border_color=COLORS["card_border"], border_width=1)

    def _bind_click_events(self):
        """Bind click events to all child widgets recursively."""
        self._bind_widget_and_children(self)
    
    def _bind_widget_and_children(self, widget):
        """Recursively bind click events to a widget and all its children."""
        # Bind to this widget
        widget.bind("<Button-1>", self.toggle_select)
        
        # Recursively bind to all children
        try:
            for child in widget.winfo_children():
                self._bind_widget_and_children(child)
        except:
            # Some widgets may not have winfo_children method
            pass

    def toggle_select(self, event=None):
        """
        Toggle selection state with visual feedback.
        
        Also notifies the parent frame about the selection change.
        
        Args:
            event: The event that triggered this method, or None
            force_state: If provided, forces the selection to this state (True/False)
        """
        # If event is a boolean, it's being used as force_state
        force_state = None
        if isinstance(event, bool):
            force_state = event
            event = None
            
        # Toggle or set the selected state
        if force_state is not None:
            self.selected = force_state
        else:
            self.selected = not self.selected
        
        # Update the visual state based on selection
        self.update_selection_state()
            
        # Notify the parent about the selection change
        if self.on_select:
            self.on_select(self)
        
        # Prevent event propagation
        if event:
            return "break"
            
    def update_selection_state(self):
        """Update the visual state of the card based on selection state."""
        if self.selected:
            self.configure(border_width=2, border_color=COLORS["accent"])
            self.selection_overlay.lift()  # Show selection overlay
            self.checkmark.lift()  # Show checkmark
            self.selection_badge.lift()  # Show selection badge
        else:
            self.configure(border_width=1, border_color=COLORS["card_border"])
            self.selection_overlay.lower()  # Hide selection overlay
            self.checkmark.lower()  # Hide checkmark
            self.selection_badge.lower()  # Hide selection badge

    def load_thumbnail(self):
        """Load thumbnail image from Instagram."""
        try:
            # Check if we already have this thumbnail in cache
            with MediaCard._cache_lock:
                if self.media.pk in MediaCard._thumbnail_cache:
                    # Use cached thumbnail
                    self.thumbnail_image = MediaCard._thumbnail_cache[self.media.pk]
                    self.thumb_label.configure(image=self.thumbnail_image, text="")
                    self._thumbnail_loaded = True
                    return
            
            # Show loading indicator
            self.thumb_label.configure(text="Loading...")
            
            # Check if we're already at max concurrent loads
            with MediaCard._active_loads_lock:
                if MediaCard._active_loads >= MediaCard._max_concurrent_loads:
                    # Too many active loads, schedule retry after a delay
                    self.after(500, self.load_thumbnail)
                    return
                # Increment active loads counter
                MediaCard._active_loads += 1
            
            # Start loading thumbnail in background
            def load_thumbnail_task():
                try:
                    # Create a placeholder image first
                    placeholder = Image.new('RGB', (180, 180), color=(50, 50, 50))
                    
                    # Get thumbnail URL
                    thumbnail_url = self.media.thumbnail_url
                    
                    # Download thumbnail with timeout
                    response = requests.get(thumbnail_url, timeout=3)  # Reduced timeout
                    if response.status_code != 200:
                        raise Exception(f"Failed to download thumbnail: HTTP {response.status_code}")
                    
                    # Create PIL image from response content
                    image = Image.open(io.BytesIO(response.content))
                    
                    # Resize image to fit thumbnail container (maintain aspect ratio)
                    image.thumbnail((180, 180))
                    
                    # Convert to CTkImage
                    ctk_image = ctk.CTkImage(light_image=image, dark_image=image, size=(180, 180))
                    
                    # Cache the thumbnail
                    with MediaCard._cache_lock:
                        MediaCard._thumbnail_cache[self.media.pk] = ctk_image
                    
                    # Update UI in main thread
                    self.after(0, lambda: self._update_thumbnail(ctk_image))
                    
                except Exception as e:
                    # Log error and update UI in main thread
                    error_msg = str(e)
                    self.after(0, lambda: self._handle_thumbnail_error(error_msg))
                finally:
                    # Decrement active loads counter
                    with MediaCard._active_loads_lock:
                        MediaCard._active_loads -= 1
            
            # Submit task to executor
            self.thumbnail_future = MediaCard._thumbnail_executor.submit(load_thumbnail_task)
            
        except Exception as e:
            self._handle_thumbnail_error(str(e))
    
    def _update_thumbnail(self, ctk_image):
        """Update thumbnail in UI thread."""
        try:
            if not self.winfo_exists():
                return
            self.thumbnail_image = ctk_image
            self.thumb_label.configure(image=ctk_image, text="")
            self._thumbnail_loaded = True
        except Exception as e:
            self.log_to_terminal(f"Error updating thumbnail: {str(e)}")
    
    def _handle_thumbnail_error(self, error_msg):
        """Handle thumbnail loading error in UI thread."""
        try:
            if not self.winfo_exists():
                return
            self.log_to_terminal(f"Failed to load thumbnail: {error_msg}")
            # Set a placeholder image or error indicator
            self.thumb_label.configure(text="❌", font=("Segoe UI", 24))
        except Exception as e:
            pass

    def log_to_terminal(self, message):
        """Log a message to the terminal if available."""
        try:
            # Try to access the parent's log_to_terminal method
            parent = self.winfo_toplevel()
            if hasattr(parent, 'log_to_terminal'):
                parent.log_to_terminal(message)
            else:
                # Fallback to standard logging
                logging.info(message)
        except:
            # If anything fails, use standard logging
            logging.info(message)

    def check_repost_status(self):
        """Check if this media has been reposted to any alt accounts."""
        try:
            if not self.reposter:
                return
                
            # Get repost status
            self.reposted_to = self.reposter.check_repost_status(self.media)
            
            # Update UI in main thread
            self.after(0, self.update_repost_status)
        except Exception as e:
            self.log_to_terminal(f"Error checking repost status: {str(e)}")
            
    def update_repost_status(self, reposted_to=None):
        """Update the UI to show repost status.
        
        Args:
            reposted_to: Optional list of usernames where this media was reposted.
                         If provided, updates self.reposted_to.
        """
        try:
            if not self.winfo_exists():
                return
            
            # Update reposted_to if provided
            if reposted_to is not None:
                self.reposted_to = reposted_to
                
            # Clear existing repost status
            for widget in self.repost_container.winfo_children():
                widget.destroy()
                
            # Create repost status label
            if not self.reposted_to:
                status_label = ctk.CTkLabel(
                    self.repost_container,
                    text="Not reposted",
                    font=ctk.CTkFont(family="Helvetica", size=10),  # Reduced from 11
                    text_color=COLORS["text_secondary"]
                )
                status_label.pack(side="left", padx=8, pady=2)
            else:
                # Create a label showing repost count for consistency
                status_text = f"Reposted to {len(self.reposted_to)} account(s)"
                status_label = ctk.CTkLabel(
                    self.repost_container,
                    text=status_text,
                    font=ctk.CTkFont(family="Helvetica", size=10, weight="bold"),
                    text_color=COLORS["success"]
                )
                status_label.pack(side="left", padx=8, pady=2)
                
                # Only show first username if there are multiple to maintain consistent layout
                if len(self.reposted_to) > 0:
                    username = self.reposted_to[0]
                    if len(self.reposted_to) > 1:
                        username += " + others"
                        
                    reposter_label = ctk.CTkLabel(
                        self.repost_container,
                        text=username,
                        font=ctk.CTkFont(family="Helvetica", size=10),
                        text_color=COLORS["success"],
                        fg_color=COLORS["bg_dark"],
                        corner_radius=6,
                        width=100,
                        height=20
                    )
                    reposter_label.pack(side="right", padx=5, pady=2)
                
        except Exception as e:
            self.log_to_terminal(f"Error updating repost status: {str(e)}")
            
    def _create_tooltip(self, widget, text):
        """Create a tooltip for a widget."""
        def enter(event):
            x = widget.winfo_rootx() + widget.winfo_width() + 5
            y = widget.winfo_rooty() + 5
            
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