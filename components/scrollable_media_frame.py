"""
MediaGridFrame component for displaying a grid of media cards in the Instagram Repost tool.
This implementation uses pagination instead of scrolling.
"""
import customtkinter as ctk
import logging
import math
from utils.constants import COLORS
from components.media_card import MediaCard

class ScrollableMediaFrame(ctk.CTkFrame):
    """
    A custom frame that displays media items in a paginated grid.
    
    This implementation completely abandons scrolling in favor of pagination
    with next/previous buttons and page indicators.
    """
    
    def __init__(self, parent, reposter, **kwargs):
        """Initialize the MediaGridFrame with pagination support."""
        # Extract scrollbar-specific options from kwargs but we won't use them
        kwargs.pop("scrollbar_button_color", None)
        kwargs.pop("scrollbar_button_hover_color", None)
        kwargs.pop("scrollbar_fg_color", None)
        corner_radius = kwargs.pop("corner_radius", 10)
        
        # Initialize the main frame with the remaining kwargs
        super().__init__(parent, **kwargs)
        
        # Store references
        self.parent = parent
        self.reposter = reposter
        
        # Media storage
        self.media_cards = []
        self.filtered_cards = []
        self.selected_cards = []  # Track multiple selected cards
        self.visible_cards = []  # Currently visible cards (for current page)
        
        # Define standard card dimensions - SMALLER SIZES
        self.CARD_WIDTH = 160     # Reduced from 200
        self.CARD_HEIGHT = 240    # Reduced from 300
        self.CARD_SPACING = 8     # Reduced from 10
        
        # Pagination settings
        self.current_page = 0
        self.items_per_page = 9  # Increased from 6 since cards are smaller
        self.total_pages = 0
        
        # Configure the main frame
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)  # Row 0 for pagination controls, row 1 for content
        
        # Create the content frame
        self.content_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.content_frame.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
        
        # Create pagination controls frame
        self.controls_frame = ctk.CTkFrame(self, fg_color="transparent", height=30)
        self.controls_frame.grid(row=2, column=0, sticky="ew", padx=5, pady=5)
        
        # Configure pagination controls
        self.controls_frame.grid_columnconfigure(0, weight=1)
        self.controls_frame.grid_columnconfigure(1, weight=0)
        self.controls_frame.grid_columnconfigure(2, weight=0)
        self.controls_frame.grid_columnconfigure(3, weight=0)
        self.controls_frame.grid_columnconfigure(4, weight=1)
        
        # Previous button
        self.prev_button = ctk.CTkButton(
            self.controls_frame, 
            text="◀ Prev", 
            command=self._go_to_prev_page,
            fg_color=COLORS.get("accent", "#1f538d"),
            hover_color=COLORS.get("accent_dark", "#0d2e4d"),
            width=80,         # Reduced from 100
            height=24         # Reduced from default
        )
        self.prev_button.grid(row=0, column=1, padx=(5, 2), pady=5)
        
        # Page indicator
        self.page_indicator = ctk.CTkLabel(
            self.controls_frame, 
            text="Page 0 of 0",
            fg_color=COLORS.get("bg_medium", "#3e4042"),
            corner_radius=5,
            width=80,         # Reduced from 100
            height=24         # Reduced from 30
        )
        self.page_indicator.grid(row=0, column=2, padx=2, pady=5)
        
        # Next button
        self.next_button = ctk.CTkButton(
            self.controls_frame, 
            text="Next ▶", 
            command=self._go_to_next_page,
            fg_color=COLORS.get("accent", "#1f538d"),
            hover_color=COLORS.get("accent_dark", "#0d2e4d"),
            width=80,         # Reduced from 100
            height=24         # Reduced from default
        )
        self.next_button.grid(row=0, column=3, padx=(2, 5), pady=5)
        
        # Configure content grid
        # Set up a 3x3 grid by default (9 items per page)
        self.current_columns = 3
        self.current_rows = 3
        
        for i in range(self.current_columns):
            self.content_frame.grid_columnconfigure(i, weight=1)
            
        for i in range(self.current_rows):
            self.content_frame.grid_rowconfigure(i, weight=1)
        
        # Initial layout update on window resize
        self.bind("<Configure>", self._handle_resize)
        
        # Schedule initial layout update
        self.after(100, self._update_layout)
        
    def _handle_resize(self, event=None):
        """Handle resize events by updating the layout."""
        # Ignore small frames
        if self.winfo_width() < 100 or self.winfo_height() < 100:
            return
            
        # Schedule a layout update
        self.after(100, self._update_layout)
        
    def _update_layout(self):
        """Update the layout of media cards based on available width."""
        # Calculate how many columns fit based on available width
        available_width = self.winfo_width() - 20
        card_width_with_spacing = self.CARD_WIDTH + (2 * self.CARD_SPACING)
        
        columns = max(1, min(5, available_width // card_width_with_spacing))  # Allow up to 5 columns (increased from 4)
        
        # Calculate how many rows fit based on available height
        available_height = self.winfo_height() - 80  # Account for pagination controls
        card_height_with_spacing = self.CARD_HEIGHT + (2 * self.CARD_SPACING)
        
        rows = max(1, min(4, available_height // card_height_with_spacing))  # Allow up to 4 rows (increased from 3)
        
        # Only update if layout changed
        if columns != self.current_columns or rows != self.current_rows:
            self.current_columns = columns
            self.current_rows = rows
            self.items_per_page = columns * rows
            
            # Configure content grid
            for i in range(columns):
                self.content_frame.grid_columnconfigure(i, weight=1)
                
            for i in range(rows):
                self.content_frame.grid_rowconfigure(i, weight=1)
                
            logging.debug(f"Layout updated: {columns}x{rows} grid with {self.items_per_page} items per page")
            
            # Re-paginate with new page size
            self._update_pagination()
    
    def _update_pagination(self):
        """Update pagination based on current items and page size."""
        cards = self.filtered_cards if self.filtered_cards else self.media_cards
        
        # Calculate total pages
        if self.items_per_page > 0:
            self.total_pages = math.ceil(len(cards) / self.items_per_page)
        else:
            self.total_pages = 0
            
        # Ensure current page is valid
        if self.current_page >= self.total_pages:
            self.current_page = max(0, self.total_pages - 1)
        
        # Update page indicator
        self.page_indicator.configure(text=f"Page {self.current_page + 1} of {self.total_pages}")
        
        # Enable/disable pagination buttons
        self.prev_button.configure(state="normal" if self.current_page > 0 else "disabled")
        self.next_button.configure(state="normal" if self.current_page < self.total_pages - 1 else "disabled")
        
        # Show current page
        self._show_current_page()
    
    def _show_current_page(self):
        """Display the current page of media cards."""
        cards = self.filtered_cards if self.filtered_cards else self.media_cards
        
        # Hide all cards first
        for card in self.visible_cards:
            card.grid_forget()
        
        self.visible_cards = []
        
        # If no cards or invalid page, just return
        if not cards or self.current_page < 0 or self.total_pages == 0:
            return
        
        # Calculate start and end indices for current page
        start_idx = self.current_page * self.items_per_page
        end_idx = min(start_idx + self.items_per_page, len(cards))
        
        # Show cards for current page
        for i, idx in enumerate(range(start_idx, end_idx)):
            if idx >= len(cards):
                break
                
            card = cards[idx]
            
            # Calculate grid position
            row = i // self.current_columns
            col = i % self.current_columns
            
            # Standard card size
            try:
                card.configure(width=self.CARD_WIDTH, height=self.CARD_HEIGHT)
            except Exception:
                pass
                
            # Place card in grid
            card.grid(
                in_=self.content_frame,
                row=row,
                column=col,
                sticky="nsew",
                padx=self.CARD_SPACING,
                pady=self.CARD_SPACING
            )
            
            # Add to visible cards
            self.visible_cards.append(card)
    
    def _go_to_next_page(self):
        """Go to the next page."""
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            self._update_pagination()
    
    def _go_to_prev_page(self):
        """Go to the previous page."""
        if self.current_page > 0:
            self.current_page -= 1
            self._update_pagination()
            
    # Implement scroll methods that just call pagination methods
    # This allows compatibility with existing code that expects these methods
    def scroll_up(self, event=None):
        """Compatibility method - go to previous page."""
        self._go_to_prev_page()
        return "break"
        
    def scroll_down(self, event=None):
        """Compatibility method - go to next page."""
        self._go_to_next_page()
        return "break"
            
    def add_media(self, media):
        """Add a new media item to the grid."""
        # Create media card with selection callback
        card = MediaCard(
            self.content_frame,
            media,
            self.reposter,
            on_select=self.handle_selection,
            width=self.CARD_WIDTH,
            height=self.CARD_HEIGHT,
            fg_color=COLORS.get("bg_light", "#333333"),
            corner_radius=8
        )
        
        # Add to list of all cards
        self.media_cards.append(card)
        
        # Update pagination for the new card
        self._update_pagination()
        
        return card
        
    def handle_selection(self, selected_card):
        """Handle selection of a media card."""
        # Support multi-selection
        if selected_card.selected:
            # Card was selected, add to selection list
            self.selected_cards.append(selected_card)
            # Update the selection badge with the selection number
            selected_card.selection_badge.configure(text=str(len(self.selected_cards)))
        else:
            # Card was deselected, remove from selection list
            if selected_card in self.selected_cards:
                self.selected_cards.remove(selected_card)
                
            # Update remaining selection badges with new numbers
            for i, card in enumerate(self.selected_cards):
                card.selection_badge.configure(text=str(i+1))
                
        # Update UI elements based on selection state
        self.parent.update_selection_count(len(self.selected_cards))
                
    def clear(self):
        """Clear all media cards."""
        for card in self.media_cards:
            card.destroy()
            
        self.media_cards = []
        self.filtered_cards = []
        self.visible_cards = []
        self.selected_cards = []
        
        # Reset pagination
        self.current_page = 0
        self._update_pagination()
    
    def clear_selection(self):
        """Clear the current selection."""
        # Deselect all cards
        for card in self.selected_cards[:]:
            card.toggle_select(False)
        
        # Clear the selection list
        self.selected_cards = []
        
        # Update UI elements
        self.parent.update_selection_count(0)
    
    def select_all_videos(self):
        """Select all video items."""
        self.clear_selection()
        
        for card in self.filtered_cards or self.media_cards:
            if hasattr(card.media, 'media_type') and card.media.media_type == 2:  # Videos
                card.toggle_select(True)
        
    def select_all_photos(self):
        """Select all photo items."""
        self.clear_selection()
        
        for card in self.filtered_cards or self.media_cards:
            if hasattr(card.media, 'media_type') and card.media.media_type == 1:  # Photos
                card.toggle_select(True)
                
    def select_all(self):
        """Select all items."""
        self.clear_selection()
        
        for card in self.filtered_cards or self.media_cards:
            card.toggle_select(True)
            
    def get_selected_media(self):
        """Get all currently selected media."""
        return [card for card in self.media_cards if hasattr(card, "selected") and card.selected]
    
    def filter_and_sort_media(self, search_text, media_type=None, sort_by=None, sort_order="desc"):
        """Filter and sort media based on criteria."""
        # Reset filtered cards
        self.filtered_cards = []
        
        # Apply filters
        for card in self.media_cards:
            # Text search
            text_match = True
            if search_text:
                search_lower = search_text.lower()
                card_text = getattr(card.media, "caption_text", "") or ""
                card_text = card_text.lower()
                text_match = search_lower in card_text
            
            # Media type filter
            type_match = True
            if media_type == "video":
                type_match = getattr(card.media, "media_type", 0) == 2
            elif media_type == "photo":
                type_match = getattr(card.media, "media_type", 0) == 1
            
            # If all filters match, include card
            if text_match and type_match:
                self.filtered_cards.append(card)
        
        # Apply sorting
        if sort_by:
            reverse = sort_order.lower() == "desc"
            
            if sort_by == "date":
                self.filtered_cards.sort(key=lambda c: getattr(c.media, "taken_at", 0) or 0, reverse=reverse)
            elif sort_by == "likes":
                self.filtered_cards.sort(key=lambda c: getattr(c.media, "like_count", 0) or 0, reverse=reverse)
            elif sort_by == "comments":
                self.filtered_cards.sort(key=lambda c: getattr(c.media, "comment_count", 0) or 0, reverse=reverse)
        
        # Reset to first page and update pagination
        self.current_page = 0
        self._update_pagination()
        
        return len(self.filtered_cards) 