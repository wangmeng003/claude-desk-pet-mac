# Claude 娘桌宠悬浮窗
# mod 把每个会话的状态写进 <运行目录>/sessions/<会话id>.json，这里读最新的那个来换表情和气泡。
# 用法：pythonw pet.pyw <运行目录>
import ctypes
import ctypes.wintypes as wt
import math
import os
import socket
import subprocess
import sys
import time
import tkinter as tk
import winsound

from PIL import Image, ImageTk

from core import cli_args
from core import errors as core_errors
from core import sessions as core_sessions
from core import state_reader as core_state_reader
from core import view_model as core_view_model
from core.models import IDLE_AFTER, SIZES, SPRITES  # noqa: F401  (build/菜单与测试直接用)

HERE = os.path.dirname(os.path.abspath(__file__))
SOUNDS = os.path.join(os.path.dirname(HERE), 'sounds')
RUN_DIR, _SHOT_PATH = cli_args.parse_args(sys.argv[1:], cli_args.default_run_dir())
SESSIONS = os.path.join(RUN_DIR, 'sessions')
SETTINGS = os.path.join(RUN_DIR, 'settings.json')

# 只允许开一个桌宠：占住一个本地端口，占不到说明已经有一个在跑
# （在 acquire_lock() 里做，保持 import 本模块无副作用，测试才能导入）
_lock = None


def acquire_lock():
    global _lock
    try:
        _lock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        _lock.bind(('127.0.0.1', 47321))
    except OSError:
        sys.exit(0)

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass

# 状态 → 立绘在 core.models 里（与 macOS 版共用）。
KEY = '#ff00fe'       # 透明色：画布上这个颜色的像素会被挖空
EDGE = (58, 36, 26)   # 半透明边缘和这个深棕色混合，避免边缘发出洋红色的毛边
ORANGE = '#e8743b'

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32


def process_name(pid):
    h = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return ''
    try:
        buf = ctypes.create_unicode_buffer(520)
        size = wt.DWORD(520)
        if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return os.path.basename(buf.value).lower()
        return ''
    finally:
        kernel32.CloseHandle(h)


def window_pid(hwnd):
    pid = wt.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def claude_is_foreground():
    hwnd = user32.GetForegroundWindow()
    return bool(hwnd) and process_name(window_pid(hwnd)) == 'claude.exe'


def find_claude_window():
    found = []
    PROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)

    def cb(hwnd, _):
        if user32.IsWindowVisible(hwnd) and user32.GetWindowTextLengthW(hwnd) > 0 \
                and process_name(window_pid(hwnd)) == 'claude.exe':
            found.append(hwnd)
            return False
        return True

    user32.EnumWindows(PROC(cb), 0)
    return found[0] if found else None


def claude_running():
    try:
        out = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq claude.exe', '/NH'], capture_output=True,
                             text=True, timeout=10, creationflags=0x08000000).stdout
        return 'claude.exe' in out.lower()
    except Exception:
        return True


def load_settings():
    return core_state_reader.load_settings(SETTINGS)


def save_settings(s):
    core_state_reader.save_settings(SETTINGS, s)


def read_latest():
    """读所有会话里最新的状态；顺手清掉过期文件。"""
    return core_sessions.read_latest(SESSIONS)


def prepare(path, height):
    """缩放立绘并把透明部分处理成透明色。"""
    im = Image.open(path).convert('RGBA')
    w = round(im.width * height / im.height)
    im = im.resize((w, height), Image.LANCZOS)
    bg = Image.new('RGBA', im.size, EDGE + (255,))
    solid = Image.alpha_composite(bg, im)
    key = Image.new('RGBA', im.size, KEY)
    mask = im.getchannel('A').point(lambda a: 255 if a >= 110 else 0)
    key.paste(solid, (0, 0), mask)
    return key.convert('RGB')


class Pet:
    def __init__(self):
        self.settings = load_settings()
        self.root = tk.Tk()
        self.root.title('Claude 桌宠')
        self.root.overrideredirect(True)
        self.root.attributes('-topmost', True)
        self.root.attributes('-transparentcolor', KEY)
        self.root.configure(bg=KEY)
        self.scale = self.root.winfo_fpixels('1i') / 96

        self.canvas = tk.Canvas(self.root, bg=KEY, highlightthickness=0, bd=0)
        self.canvas.pack()
        self.font = ('Microsoft YaHei UI', 10)
        self.small = ('Microsoft YaHei UI', 8)

        self.state, self.text, self.project = 'waiting', '我来啦～', ''
        self.state_since = time.time()
        self.last_mtime = 0
        self.last_mtime_seen = 0
        self.hop_at = time.time()
        self.hidden = False
        self.drag = None
        self.last_alive = time.time()
        self.bubble_text = None

        self.build()
        self.place_window()
        self.make_menu()

        self.canvas.bind('<ButtonPress-1>', self.on_press)
        self.canvas.bind('<B1-Motion>', self.on_drag)
        self.canvas.bind('<ButtonRelease-1>', self.on_release)
        self.canvas.bind('<Double-Button-1>', self.on_double)
        self.canvas.bind('<Button-3>', lambda e: self.menu.tk_popup(e.x_root, e.y_root))

        self.poll()
        self.animate()
        self.watch_focus()
        self.watch_claude()

    # ---------- 布局 ----------
    def build(self):
        h = round(SIZES.get(self.settings.get('size', '中'), 190) * self.scale)
        self.images = {}
        for state, name in SPRITES.items():
            try:
                self.images[state] = ImageTk.PhotoImage(
                    prepare(os.path.join(HERE, 'sprites', name + '.png'), h))
            except Exception:
                continue  # 立绘缺失/损坏：跳过这一张，别让整个桌宠起不来
        self.fallback_image = next(iter(self.images.values()), None)
        self.char_h = h
        self.char_w = max((img.width() for img in self.images.values()),
                           default=round(190 * self.scale))
        self.bubble_h = round(52 * self.scale)
        self.W = max(self.char_w, round(190 * self.scale))
        self.H = self.bubble_h + round(8 * self.scale) + h + round(6 * self.scale)
        self.canvas.config(width=self.W, height=self.H)
        self.canvas.delete('all')
        image = self.images.get(self.state) or self.fallback_image
        self.sprite = None
        if image is not None:
            self.sprite = self.canvas.create_image(self.W // 2, self.H, anchor='s', image=image)
        self.draw_bubble()

    def measure(self, text):
        """用 Tk 的字体度量量文字宽度。"""
        try:
            return int(self.canvas.tk.call('font', 'measure', self.font, text))
        except Exception:
            return 0

    def draw_bubble(self):
        c, s = self.canvas, self.scale
        c.delete('bubble')
        self.bubble_text = None
        text = self.display_text()
        # 气泡宽度被窗口卡死，文字太长会溢出气泡，逐字截到放得下为止
        limit = self.W - 4
        if self.measure(text) > limit:
            trimmed = text
            while trimmed and self.measure(trimmed + '…') > limit:
                trimmed = trimmed[:-1]
            text = trimmed + '…'
        tid = c.create_text(self.W // 2, round(20 * s), text=text, font=self.font, fill='#3a2a1a', tags='bubble')
        box = c.bbox(tid)
        if not box:
            # 画布还没算出文字尺寸：这帧先不画气泡，下一帧补上
            c.delete(tid)
            return
        x0, y0, x1, y1 = box
        pad = round(10 * s)
        x0, x1 = max(1, x0 - pad), min(self.W - 2, x1 + pad)
        y0, y1 = 2, round(38 * s)
        r = round(12 * s)
        pts = [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1, x1 - r, y1,
               self.W // 2 + round(8 * s), y1, self.W // 2, y1 + round(10 * s), self.W // 2 - round(4 * s), y1,
               x0 + r, y1, x0, y1, x0, y1 - r, x0, y0 + r, x0, y0]
        c.create_polygon(pts, smooth=True, fill='#fffaf3', outline=ORANGE, width=max(2, round(2 * s)), tags='bubble')
        c.tag_raise(tid)
        self.bubble_text = tid

    def display_text(self):
        return core_view_model.display_text(
            self.state, self.text, time.time(), self.state_since)

    def effective_state(self):
        return core_view_model.effective_state(self.state, self.state_since, time.time())

    def place_window(self):
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        x = core_state_reader.number(self.settings.get('x'), sw - self.W - round(40 * self.scale))
        y = core_state_reader.number(self.settings.get('y'), sh - self.H - round(70 * self.scale))
        x, y = min(max(0, x), sw - 40), min(max(0, y), sh - 40)
        self.root.geometry(f'{self.W}x{self.H}+{x}+{y}')

    def make_menu(self):
        self.menu = tk.Menu(self.root, tearoff=0, font=self.font)
        size_menu = tk.Menu(self.menu, tearoff=0, font=self.font)
        self.size_var = tk.StringVar(value=self.settings.get('size', '中'))
        for name in SIZES:
            size_menu.add_radiobutton(label=name, variable=self.size_var, value=name, command=self.resize)
        self.menu.add_cascade(label='大小', menu=size_menu)
        self.hide_var = tk.BooleanVar(value=self.settings.get('hideOnFocus', False))
        self.menu.add_checkbutton(label='切到 Claude 时自动隐藏', variable=self.hide_var, command=self.toggle_hide)
        self.sound_var = tk.BooleanVar(value=self.settings.get('sound', True))
        self.menu.add_checkbutton(label='提示音', variable=self.sound_var, command=self.toggle_sound)
        self.menu.add_separator()
        self.menu.add_command(label='退出桌宠', command=self.root.destroy)

    def resize(self):
        self.settings['size'] = self.size_var.get()
        save_settings(self.settings)
        bottom_x = self.root.winfo_x() + self.W // 2
        bottom_y = self.root.winfo_y() + self.H
        self.build()
        self.root.geometry(f'{self.W}x{self.H}+{bottom_x - self.W // 2}+{bottom_y - self.H}')

    def toggle_hide(self):
        self.settings['hideOnFocus'] = self.hide_var.get()
        save_settings(self.settings)

    def toggle_sound(self):
        self.settings['sound'] = self.sound_var.get()
        save_settings(self.settings)

    # ---------- 鼠标 ----------
    def on_press(self, e):
        self.drag = (e.x_root - self.root.winfo_x(), e.y_root - self.root.winfo_y())

    def on_drag(self, e):
        if self.drag:
            self.root.geometry(f'+{e.x_root - self.drag[0]}+{e.y_root - self.drag[1]}')

    def on_release(self, e):
        self.drag = None
        self.settings['x'], self.settings['y'] = self.root.winfo_x(), self.root.winfo_y()
        save_settings(self.settings)

    def on_double(self, e):
        # 双击：把 Claude 窗口叫到前台
        hwnd = find_claude_window()
        if hwnd:
            if user32.IsIconic(hwnd):
                user32.ShowWindow(hwnd, 9)  # SW_RESTORE
            user32.SetForegroundWindow(hwnd)

    # ---------- 循环 ----------
    def schedule(self, delay, fn):
        """排下一次回调；root 已销毁时安静跳过。"""
        try:
            self.root.after(delay, fn)
        except Exception:
            pass

    def log_error(self):
        """记异常到运行目录；写不进去也不能影响主循环。"""
        core_errors.log_exception(RUN_DIR)

    def poll(self):
        # poll 里的异常绝不能停掉轮询：root.after 在最后，
        # 一旦抛错就再也不会调度，桌宠会永远停在旧表情。
        try:
            self.poll_once()
        except Exception:
            self.log_error()
        finally:
            self.schedule(250, self.poll)

    def poll_once(self):
        latest = read_latest()
        if latest and latest[0] != self.last_mtime:
            self.last_mtime_seen, self.last_mtime = self.last_mtime, latest[0]
            mapped = core_view_model.normalize(latest[1])
            changed = mapped.state != self.state
            self.state, self.text = mapped.state, mapped.text
            self.project = mapped.project
            self.state_since = time.time()
            if mapped.sound and self.sound_var.get() and self.last_mtime_seen:  # 刚启动时不重播旧提示音
                try:
                    winsound.PlaySound(os.path.join(SOUNDS, mapped.sound + '.wav'),
                                       winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
                except Exception:
                    pass
            if changed:
                self.hop_at = time.time()
            self.set_sprite(self.effective_state())
            self.draw_bubble()
        elif self.effective_state() == 'idle':
            idle = self.images.get('idle')
            if (idle is not None and self.sprite is not None
                    and self.canvas.itemcget(self.sprite, 'image') != str(idle)):
                self.canvas.itemconfig(self.sprite, image=idle)
                self.draw_bubble()

    def set_sprite(self, state):
        """换立绘；这张图缺失时退到任意一张。"""
        image = self.images.get(state) or self.fallback_image
        if image is None or self.sprite is None:
            return
        self.canvas.itemconfig(self.sprite, image=image)

    def animate(self):
        t = time.time()
        st = self.effective_state()
        s = self.scale
        if st == 'stone':
            bob = 0
        elif st == 'tool':
            bob = 2.5 * math.sin(t * 9)   # 敲键盘：快速小幅抖动
        elif st == 'error':
            bob = 2 * math.sin(t * 25)    # 慌张：发抖
        else:
            bob = 3 * math.sin(t * 2.2)   # 平时：慢慢呼吸
        since = t - self.hop_at
        hop = -14 * math.sin(since / 0.28 * math.pi) if since < 0.28 else 0  # 换状态时小跳一下
        if self.sprite is not None:
            self.canvas.coords(self.sprite, self.W // 2,
                               self.H + round((bob + hop) * s) - round(4 * s))
        if st == 'thinking' and self.text.endswith('中') and self.bubble_text:
            # “思考中” 后面的点点点一跳一跳
            self.canvas.itemconfig(self.bubble_text, text=core_view_model.thinking_dots(self.text, t))
        self.schedule(33, self.animate)

    def watch_focus(self):
        should_hide = self.hide_var.get() and claude_is_foreground() and self.drag is None
        if should_hide and not self.hidden:
            self.root.withdraw()
            self.hidden = True
        elif not should_hide and self.hidden:
            self.root.deiconify()
            self.root.attributes('-topmost', True)
            self.hidden = False
        self.schedule(300, self.watch_focus)

    def watch_claude(self):
        # Claude 关掉两分钟后，桌宠也自己退出
        if claude_running():
            self.last_alive = time.time()
        elif time.time() - self.last_alive > 120:
            self.root.destroy()
            return
        self.schedule(30000, self.watch_claude)


if __name__ == '__main__':
    acquire_lock()
    try:
        Pet().root.mainloop()
    except Exception:
        import traceback
        with open(os.path.join(RUN_DIR, 'pet-error.log'), 'w', encoding='utf-8') as f:
            traceback.print_exc(file=f)
