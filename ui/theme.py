"""
Global dark/light theme manager.

Usage:
    import ui.theme as theme

    theme.apply(dark)     # set theme (call once after Tk root created to initialise)
    theme.toggle()        # flip dark ↔ light
    theme.is_dark()       # current state
    theme.register(cb)    # callback(dark: bool) called on every change
    theme.unregister(cb)  # remove callback
"""

_dark: bool = False
_listeners: list = []
_native_body_size: int = -12   # TkDefaultFont pixel size captured before sv_ttk loads


def _capture_native_size():
    """Snapshot TkDefaultFont size before sv_ttk changes it."""
    global _native_body_size
    try:
        import tkinter.font as tkfont
        _native_body_size = tkfont.nametofont('TkDefaultFont').actual()['size']
    except Exception:
        pass


def _restore_sv_font_sizes():
    """Bring sv_ttk's named fonts back down to the native body size."""
    try:
        import tkinter.font as tkfont
        size = _native_body_size
        # Body font used by almost all widgets
        tkfont.nametofont('SunValleyBodyFont').configure(size=size)
        # Caption font used by LabelFrame labels and Treeview headings
        tkfont.nametofont('SunValleyCaptionFont').configure(size=size)
        # Also restore standard Tk named fonts in case sv_ttk touched them
        for name in ('TkDefaultFont', 'TkTextFont', 'TkFixedFont',
                     'TkMenuFont', 'TkHeadingFont', 'TkSmallCaptionFont'):
            try:
                tkfont.nametofont(name).configure(size=size)
            except Exception:
                pass
    except Exception:
        pass  # SunValley fonts don't exist until sv_ttk first loads — safe to ignore


def is_dark() -> bool:
    return _dark


def toggle() -> None:
    apply(not _dark)


def apply(dark: bool) -> None:
    global _dark
    _dark = dark
    _capture_native_size()
    try:
        import sv_ttk
        sv_ttk.set_theme('dark' if dark else 'light')
        _restore_sv_font_sizes()
    except Exception:
        pass  # sv_ttk not installed; canvas theme still switches
    for cb in list(_listeners):
        try:
            cb(dark)
        except Exception:
            pass


def register(cb) -> None:
    if cb not in _listeners:
        _listeners.append(cb)


def unregister(cb) -> None:
    try:
        _listeners.remove(cb)
    except ValueError:
        pass
