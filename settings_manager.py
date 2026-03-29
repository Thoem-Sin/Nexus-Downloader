"""Settings manager for persistent configuration"""

from PySide6.QtCore import QSettings
from pathlib import Path
from themes import DARK_THEME


class SettingsManager:
    def __init__(self):
        self.settings = QSettings("NexusLabs", "NexusDownloader")
        self.default_settings = {
            "concurrent_downloads": 3,
            "custom_accent_color": "#8B5CF6",
            "custom_accent_secondary": "#EC489A",
            "custom_bg_primary": "#0A0A0F",
            "custom_bg_secondary": "#111118",
            "custom_bg_card": "#1C1C27",
            "use_custom_theme": False,
            "output_dir": str(Path.home() / "Downloads"),
            "auto_create_subfolders": True
        }
        
    def get(self, key, default=None):
        value = self.settings.value(key, self.default_settings.get(key, default))
        # Convert boolean strings to actual booleans
        if isinstance(value, str) and value.lower() in ["true", "false"]:
            return value.lower() == "true"
        return value
    
    def set(self, key, value):
        # Convert boolean to string for storage
        if isinstance(value, bool):
            value = str(value)
        self.settings.setValue(key, value)
        
    def get_custom_theme(self):
        if self.get("use_custom_theme", False):
            return {
                "bg_primary": self.get("custom_bg_primary", DARK_THEME["bg_primary"]),
                "bg_secondary": self.get("custom_bg_secondary", DARK_THEME["bg_secondary"]),
                "bg_tertiary": self.get("custom_bg_secondary", DARK_THEME["bg_secondary"]),
                "bg_card": self.get("custom_bg_card", DARK_THEME["bg_card"]),
                "bg_hover": self.get("custom_bg_secondary", DARK_THEME["bg_secondary"]),
                "bg_input": self.get("custom_bg_primary", DARK_THEME["bg_primary"]),
                "border": "#2A2A38",
                "border_focus": self.get("custom_accent_color", DARK_THEME["accent"]),
                "accent": self.get("custom_accent_color", DARK_THEME["accent"]),
                "accent_hover": self.get("custom_accent_color", DARK_THEME["accent"]),
                "accent_secondary": self.get("custom_accent_secondary", DARK_THEME["accent_secondary"]),
                "accent_green": "#10B981",
                "accent_yellow": "#F59E0B",
                "accent_red": "#EF4444",
                "accent_blue": "#3B82F6",
                "text_primary": "#F9FAFB",
                "text_secondary": "#9CA3AF",
                "text_muted": "#6B7280",
                "text_accent": self.get("custom_accent_color", DARK_THEME["accent"]),
                "shadow": "rgba(0,0,0,0.5)",
                "scrollbar": "#2A2A38",
                "scrollbar_hover": "#3A3A50",
                "progress_bg": "#27272A",
                "tag_bg": "#252535",
                "gradient_start": self.get("custom_accent_color", DARK_THEME["accent"]),
                "gradient_end": self.get("custom_accent_secondary", DARK_THEME["accent_secondary"]),
                "glass": "rgba(28,28,39,0.85)",
                "blur": "rgba(28,28,39,0.7)",
            }
        return None
