"""
Text handling components for logging and terminal output.
"""
import logging
import tkinter as tk

class TextRedirector:
    def __init__(self, text_widget):
        self.text_widget = text_widget
        self.buffer = ""
        
    def write(self, string):
        self.buffer += string
        self.text_widget.after(0, self.update_text_widget)
        
    def update_text_widget(self):
        self.text_widget.configure(state="normal")
        self.text_widget.insert("end", self.buffer)
        self.text_widget.see("end")
        self.text_widget.configure(state="disabled")
        self.buffer = ""
        
    def flush(self):
        pass

# Custom logging handler that redirects to a text widget
class TextWidgetHandler(logging.Handler):
    def __init__(self, text_widget):
        logging.Handler.__init__(self)
        self.text_widget = text_widget
        
    def emit(self, record):
        msg = self.format(record)
        self.text_widget.after(0, self.update_text_widget, msg + "\n", record.levelno)
        
    def update_text_widget(self, msg, level):
        self.text_widget.configure(state="normal")
        
        # Choose tag based on log level
        tag = "info"
        if level >= logging.ERROR:
            tag = "error"
        elif level >= logging.WARNING:
            tag = "warning"
            
        # Insert the text with the appropriate tag
        self.text_widget.insert("end", msg, tag)
        self.text_widget.see("end")
        self.text_widget.configure(state="disabled") 