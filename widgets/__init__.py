"""Widgets package for the application"""

from widgets.animated_components import GlassCard, AnimatedIcon, GradientProgressBar, LogoAnimatedIcon
from widgets.download_card import ModernDownloadCard
from widgets.format_panel import ModernFormatPanel
from widgets.stats_bar import ModernStatsBar
from widgets.settings_dialog import SettingsDialog
from widgets.scraper_panel import ScraperPanel
from widgets.scraper_window import ScraperWindow
from widgets.failed_downloads_dialog import FailedDownloadsDialog

__all__ = [
    'GlassCard', 'AnimatedIcon', 'GradientProgressBar', 'LogoAnimatedIcon',
    'ModernDownloadCard', 'ModernFormatPanel', 'ModernStatsBar',
    'SettingsDialog', 'ScraperPanel', 'ScraperWindow', 'FailedDownloadsDialog',
]