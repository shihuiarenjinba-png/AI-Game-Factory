"""Native Windows accessibility bridge for Signal Sprint.

Standard Win32 BUTTON and STATIC child HWNDs supply UIA ControlType,
Name, InvokePattern, keyboard focus, and status text. Tk remains the game
state/event loop. No package identity or game logic is modified.
"""
import ctypes
from ctypes import wintypes

WS_CHILD = 0x40000000
WS_VISIBLE = 0x10000000
WS_TABSTOP = 0x00010000
BS_PUSHBUTTON = 0
SS_LEFT = 0
WM_COMMAND = 0x0111
GWLP_WNDPROC = -4
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010


class NativeUIABridge:
    def __init__(self, root, status_widget, tk_buttons):
        self.root = root
        self.status_widget = status_widget
        self.tk_buttons = tk_buttons
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.parent = root.winfo_id()
        self.controls = []
        self.status_hwnd = None
        self.callbacks = ()
        self.pending = None
        self._closed = False

        ptr = ctypes.c_void_p
        self.user32.CreateWindowExW.argtypes = [
            wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR,
            wintypes.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            ctypes.c_int, ptr, ptr, ptr, ptr]
        self.user32.CreateWindowExW.restype = ptr
        self.user32.SetWindowTextW.argtypes = [ptr, wintypes.LPCWSTR]
        self.user32.SetWindowTextW.restype = wintypes.BOOL
        self.user32.SetWindowPos.argtypes = [
            ptr, ptr, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            ctypes.c_int, wintypes.UINT]
        self.user32.SetWindowPos.restype = wintypes.BOOL
        self.user32.CallWindowProcW.argtypes = [
            ptr, ptr, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        self.user32.CallWindowProcW.restype = wintypes.LPARAM
        self.user32.SetWindowLongPtrW.argtypes = [ptr, ctypes.c_int, ptr]
        self.user32.SetWindowLongPtrW.restype = ptr
        callback_type = ctypes.WINFUNCTYPE(
            wintypes.LPARAM, ptr, wintypes.UINT,
            wintypes.WPARAM, wintypes.LPARAM)

        def window_proc(hwnd, msg, wparam, lparam):
            if msg == WM_COMMAND:
                control_id = int(wparam) & 0xFFFF
                notification = (int(wparam) >> 16) & 0xFFFF
                index = control_id - 4100
                if notification == 0 and 0 <= index < len(self.callbacks):
                    # Dispatch back to Tk's event loop rather than re-entering
                    # game rendering from inside a Win32 message callback.
                    self.root.after(0, self.callbacks[index])
                    return 0
            return self.user32.CallWindowProcW(
                self._original_proc, hwnd, msg, wparam, lparam)

        self._window_proc = callback_type(window_proc)
        self._original_proc = self.user32.SetWindowLongPtrW(
            self.parent, GWLP_WNDPROC,
            ctypes.cast(self._window_proc, ptr))
        if not self._original_proc:
            raise OSError("Cannot install native UIA command dispatcher")

    def install(self, callbacks):
        self.callbacks = tuple(callbacks)
        for index in range(5):
            hwnd = self.user32.CreateWindowExW(
                0, "BUTTON", "", WS_CHILD | WS_VISIBLE |
                WS_TABSTOP | BS_PUSHBUTTON,
                0, 0, 1, 1, self.parent,
                ctypes.c_void_p(4100 + index), None, None)
            if not hwnd:
                raise OSError("Cannot create native UIA button")
            self.controls.append(hwnd)
        self.status_hwnd = self.user32.CreateWindowExW(
            0, "STATIC", "", WS_CHILD | WS_VISIBLE | SS_LEFT,
            0, 0, 1, 1, self.parent,
            ctypes.c_void_p(4200), None, None)
        if not self.status_hwnd:
            raise OSError("Cannot create native UIA status text")
        self.root.bind("<Configure>", self._on_configure, add="+")
        self.root.after_idle(self._layout)

    def refresh(self, names, status):
        self.pending = (tuple(names), status)
        if self.controls:
            self.root.after_idle(self._layout)

    def _on_configure(self, event):
        if event.widget is self.root and self.controls:
            self.root.after_idle(self._layout)

    def _place(self, hwnd, widget):
        if not widget.winfo_ismapped():
            return
        x = widget.winfo_rootx() - self.root.winfo_rootx()
        y = widget.winfo_rooty() - self.root.winfo_rooty()
        width = max(1, widget.winfo_width())
        height = max(1, widget.winfo_height())
        if not self.user32.SetWindowPos(
                hwnd, None, x, y, width, height,
                SWP_NOZORDER | SWP_NOACTIVATE):
            raise OSError("Cannot position native UIA control")

    def _layout(self):
        if self._closed or not self.controls or self.pending is None:
            return
        names, status = self.pending
        for hwnd, widget, name in zip(
                self.controls, self.tk_buttons, names):
            self.user32.SetWindowTextW(hwnd, name)
            self._place(hwnd, widget)
        self.user32.SetWindowTextW(self.status_hwnd, status)
        self._place(self.status_hwnd, self.status_widget)
