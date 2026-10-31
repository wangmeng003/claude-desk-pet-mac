# Claude 娘桌宠悬浮窗
# mod 把每个会话的状态写进 <运行目录>/sessions/<会话id>.json，这里读最新的那个来换表情和气泡。
# 用法：pythonw pet.pyw <运行目录>
import atexit
import ctypes
import ctypes.wintypes as wt
import math
import os
import queue
import subprocess
import sys
import time
import tkinter as tk
from tkinter import messagebox
import winsound

from PIL import Image, ImageTk

from core import cli_args
from core import errors as core_errors
from core import lock
from core import sessions as core_sessions
from core import state_reader as core_state_reader
from core import view_model as core_view_model
from core.models import IDLE_AFTER, SIZES, SPRITES  # noqa: F401  (build/菜单与测试直接用)

HERE = os.path.dirname(os.path.abspath(__file__))
SOUNDS = os.path.join(os.path.dirname(HERE), 'sounds')
RUN_DIR, _SHOT_PATH = cli_args.parse_args(sys.argv[1:], cli_args.default_run_dir())
SESSIONS = os.path.join(RUN_DIR, 'sessions')
SETTINGS = os.path.join(RUN_DIR, 'settings.json')
QUIET = '--quiet' in sys.argv[1:]  # 被 hooks 自动拉起：单实例冲突只写日志，不弹对话框

# 只允许开一个桌宠：占住一个本地端口，占不到说明已经有一个在跑
# （在 acquire_lock() 里做，保持 import 本模块无副作用，测试才能导入）
_lock = None


def report_and_exit(msg, code, quiet):
    """单实例冲突的明确提示（#5）：写 pet-error.log；手动启动再弹对话框。"""
    try:
        with open(os.path.join(RUN_DIR, 'pet-error.log'), 'a', encoding='utf-8') as f:
            f.write(f'{time.strftime("%Y-%m-%d %H:%M:%S")} 单实例锁：{msg}\n')
    except OSError:
        pass
    if not quiet:
        root = tk.Tk()
        root.withdraw()
        messagebox.showinfo('Claude 桌宠', msg)
        root.destroy()
    sys.exit(code)


def acquire_lock(quiet):
    global _lock
    kind, info = lock.acquire(RUN_DIR, lock.port_from_env())
    if kind == 'acquired':
        _lock = info  # 一直持有：GC/关闭都会放开端口，第二只桌宠就能进来
        atexit.register(lock.remove_lock, lock.lock_path(RUN_DIR))
    elif kind == 'another-pet':
        report_and_exit(f'已经有一只桌宠在跑啦（PID {info["pid"]}），就不再开第二只。', 0, quiet)
    else:
        report_and_exit(
            f'端口 {info["port"]} 被其他程序占用，桌宠起不来。'
            f'设置环境变量 PET_PORT 换一个端口（例如 47400）再启动。', 1, quiet)

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


def _ps_quote(text):
    """PowerShell 单引号字符串字面量：单引号翻倍转义（项目目录名可能带 '）。"""
    return text.replace("'", "''")


def toast(title, body):
    """原生 Toast 通知（#6）：PowerShell 借 WinRT 模板发一条，AUMID 挂 PowerShell。
    点按拿不到回调（点按聚焦做不到），正文自带「双击桌宠回到终端」。失败静默。"""
    ps = (
        "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications,"
        " ContentType = WindowsRuntime] | Out-Null;"
        "$t = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent("
        "[Windows.UI.Notifications.ToastTemplateType]::ToastText02);"
        "$x = $t.GetElementsByTagName('text');"
        f"$x.Item(0).AppendChild($t.CreateTextNode('{_ps_quote(title)}')) | Out-Null;"
        f"$x.Item(1).AppendChild($t.CreateTextNode('{_ps_quote(body)}')) | Out-Null;"
        "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("
        "'{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\\WindowsPowerShell\\v1.0\\powershell.exe')"
        ".Show([Windows.UI.Notifications.ToastNotification]::new($t))"
    )
    try:
        subprocess.Popen(
            ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', ps],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def flash_claude():
    """闪 Claude 窗口任务栏按钮（#6）：Toast 之外再给一个视觉提示。"""
    hwnd = find_claude_window()
    if not hwnd:
        return

    class FLASHWINFO(ctypes.Structure):
        _fields_ = [('cbSize', wt.UINT), ('hwnd', wt.HWND), ('dwFlags', wt.DWORD),
                    ('uCount', wt.UINT), ('dwTimeout', wt.DWORD)]
    FLASHW_ALL = 3
    info = FLASHWINFO(ctypes.sizeof(FLASHWINFO), hwnd, FLASHW_ALL, 3, 0)
    try:
        user32.FlashWindowEx(ctypes.byref(info))
    except Exception:
        pass


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


class PermissionCard:
    """权限审批卡片（#15，specs §5.5）：Toplevel + 三按钮 + 倒计时。detail 只在内存。"""

    BADGE = {'high': ('高危 · 破坏性操作', '#d93025', '#ffe8e6'),
             'medium': ('中风险', '#b06000', '#fff3d6')}

    def __init__(self, pet, vm, deadline):
        self.pet, self.vm, self.deadline = pet, vm, deadline
        self._settled = False
        self._armed = False  # 高风险 Allow 二次确认
        top = self.top = tk.Toplevel(pet.root)
        top.title('Claude 需要你确认')
        top.attributes('-topmost', True)
        top.resizable(False, False)
        top.protocol('WM_DELETE_WINDOW', self.on_close)

        head = tk.Frame(top, padx=14, pady=10)
        head.pack(fill='x')
        tk.Label(head, text='Claude 需要你确认', font=('Microsoft YaHei UI', 12, 'bold')
                 ).pack(side='left')
        self.time_label = tk.Label(head, text='', fg='#888')
        self.time_label.pack(side='right')

        meta = f'{vm.tool} · {vm.project}' if vm.project else vm.tool
        tk.Label(top, text=meta, fg='#888', padx=14, anchor='w').pack(fill='x')
        tk.Label(top, text=vm.summary, font=('Microsoft YaHei UI', 10),
                 wraplength=320, justify='left', padx=14, anchor='w').pack(fill='x')
        badge = self.BADGE.get(vm.risk)
        if badge:
            tk.Label(top, text=badge[0], fg=badge[1], bg=badge[2], padx=6).pack(anchor='w', padx=14)

        self.toggle_btn = tk.Button(top, text='展开命令 ▸', relief='flat', command=self.toggle_detail)
        self.toggle_btn.pack(anchor='w', padx=14)
        self.detail = tk.Text(top, height=5, width=44, font=('Consolas', 9), state='disabled')
        self.detail.insert('1.0', vm.detail or '（无详情）')
        self.detail.configure(state='disabled')  # 只读可复制

        row = tk.Frame(top, pady=10)
        row.pack()
        self.btn_allow = tk.Button(row, text='允许', width=10, command=self.on_allow)
        self.btn_deny = tk.Button(row, text='拒绝', width=10, command=self.on_deny)
        self.btn_defer = tk.Button(row, text='回退终端', width=12, command=self.on_defer)
        self.btn_allow.pack(side='left', padx=4)
        self.btn_deny.pack(side='left', padx=4)
        self.btn_defer.pack(side='left', padx=4)

        default = core_view_model.card_default_focus(vm.risk)
        default_btn = self.btn_defer if default == 'defer' else self.btn_allow
        default_btn.focus_set()
        top.bind('<Return>', lambda e: default_btn.invoke())
        top.bind('<Escape>', lambda e: self.btn_defer.invoke())
        self.detail_open = False
        self.tick()

    def tick(self):
        self.time_label.config(
            text=core_view_model.card_countdown_text(self.deadline - time.time()))
        if not self._settled:
            self.top.after(500, self.tick)

    def toggle_detail(self):
        self.detail_open = not self.detail_open
        if self.detail_open:
            self.detail.pack(anchor='w', padx=14, before=self.toggle_btn.master)
            # 展开区塞在 toggle 与按钮行之间：直接 pack 到 top 尾部也行，先按简单来
            self.toggle_btn.config(text='收起命令 ▾')
        else:
            self.detail.pack_forget()
            self.toggle_btn.config(text='展开命令 ▸')

    def on_allow(self):
        if self.vm.risk == 'high' and not self._armed:
            self._armed = True
            self.btn_allow.config(text='确认放行？再点一次')
            return
        self._settle('allow')

    def on_deny(self):
        self._settle('deny')

    def on_defer(self):
        self._settle('ask')

    def on_close(self):
        # 用户关卡片 = ask（不是 deny，spec §5.4）
        self._settle('ask')

    def settle_if_matching(self, rid):
        """桥侧已结束（超时/退出）时由宠物调；匹配才关。"""
        if rid == self.vm.id and not self._settled:
            self._settled = True
            self._close()
            return True
        return False

    def _settle(self, decision):
        if self._settled:
            return
        self._settled = True
        self._close()
        self.pet.permission_decide(self.vm.id, decision)

    def _close(self):
        try:
            self.top.destroy()
        except Exception:
            pass


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
        self.error_streak = 0  # 连续 error 计数（石化彩蛋）
        self.drag = None
        self.last_alive = time.time()
        self.notify_gate = core_view_model.NotifyGate()
        self.bubble_text = None
        self.bridge = None  # __main__ 起 mainloop 前 attach_bridge（#15）
        self.card_events = queue.SimpleQueue()  # HTTP 线程 → 主线程（只传事件）
        self.card = None

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
        self.watch_lifecycle()

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
        self.privacy_var = tk.BooleanVar(value=self.settings.get('privacy', False))
        self.menu.add_checkbutton(label='隐私模式（不写项目/文件名）', variable=self.privacy_var,
                                  command=self.toggle_privacy)
        self.notify_var = tk.BooleanVar(value=self.settings.get('notify', True))
        self.menu.add_checkbutton(label='原生通知', variable=self.notify_var,
                                  command=self.toggle_notify)
        self.dnd_var = tk.BooleanVar(value=self.settings.get('dnd', False))
        self.menu.add_checkbutton(label='勿扰模式（不弹横幅不响铃）', variable=self.dnd_var,
                                  command=self.toggle_dnd)
        self.menu.add_command(label='去处理（切到终端）', command=self.go_handle)
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

    def toggle_privacy(self):
        # 隐私模式（#8）：状态文件不写项目名/文件名；hooks 一分钟内重读到开关
        self.settings['privacy'] = self.privacy_var.get()
        save_settings(self.settings)

    def toggle_notify(self):
        # 原生通知开关（#6）：celebrate/error/attention 三类状态弹 Toast + 闪任务栏
        self.settings['notify'] = self.notify_var.get()
        save_settings(self.settings)

    def toggle_dnd(self):
        # 勿扰模式（#11）：不弹横幅不响铃，气泡/表情照常
        self.settings['dnd'] = self.dnd_var.get()
        save_settings(self.settings)

    def go_handle(self):
        # 菜单「去处理」（#11）：聚焦终端；找不到窗口时气泡给出项目路径
        if not self.focus_claude():
            self.text = (f'没找到终端窗口，项目在 {self.project}'
                         if self.project else '没找到终端窗口')
            self.state_since = time.time()
            self.draw_bubble()

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

    def focus_claude(self):
        """把 Claude 窗口叫到前台；返回是否找到（失败时调用方气泡给项目路径，#11）。"""
        hwnd = find_claude_window()
        if hwnd:
            if user32.IsIconic(hwnd):
                user32.ShowWindow(hwnd, 9)  # SW_RESTORE
            user32.SetForegroundWindow(hwnd)
            return True
        return False

    def on_double(self, e):
        # 双击：把 Claude 窗口叫到前台
        self.focus_claude()

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
            self.drain_card_events()
            self.schedule(250, self.poll)

    # ---------- 权限审批卡片（#15）----------
    def attach_bridge(self, server) -> None:
        self.bridge = server

    def permission_incoming(self, vm) -> None:
        """bridge on_request（HTTP 线程）：只入队，UI 只在主线程碰。"""
        self.card_events.put(('request', vm))

    def permission_settled(self, rid, decision, reason) -> None:
        """bridge on_settled（HTTP 线程）：桥侧已结束（超时/退出），关匹配卡片。"""
        self.card_events.put(('settled', rid))

    def drain_card_events(self) -> None:
        if self.bridge is None:
            return
        while True:
            try:
                kind, payload = self.card_events.get_nowait()
            except queue.Empty:
                return
            if kind == 'request':
                if self.card is None:  # 忙时 bridge 已 409，到不了这；防御只弹一张
                    self.card = PermissionCard(self, payload,
                                               time.time() + core_view_model.CARD_TIMEOUT)
            elif self.card is not None and self.card.settle_if_matching(payload):
                self.card = None

    def permission_decide(self, rid, decision, reason='user') -> None:
        """卡片按钮/关窗 → 桥的决策；卡片自己已关。"""
        self.card = None
        if self.bridge is not None:
            self.bridge.decide(rid, decision, reason)

    def poll_once(self):
        latest = read_latest()
        if latest and latest[0] != self.last_mtime:
            self.last_mtime_seen, self.last_mtime = self.last_mtime, latest[0]
            mapped = core_view_model.normalize(latest[1])
            changed = mapped.state != self.state
            self.state, self.text = mapped.state, mapped.text
            self.project = mapped.project
            self.state_since = time.time()
            # 石化彩蛋（协议 §3）：连续 3 次 error 由渲染层自己触发
            if mapped.state == 'error':
                self.error_streak += 1
                if self.error_streak >= 3:
                    self.state, self.text = 'stone', '石化了…'
            else:
                self.error_streak = 0
            if (mapped.sound and self.sound_var.get() and not self.settings.get('dnd')
                    and self.last_mtime_seen):  # 刚启动时不重播旧提示音
                try:
                    winsound.PlaySound(os.path.join(SOUNDS, mapped.sound + '.wav'),
                                       winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
                except Exception:
                    pass
            # 原生通知（#6/#11）：长任务完成/出错/需要你看，状态切换时 Toast + 闪任务栏；
            # 勿扰不弹不响（Toast 自带默认铃声）、同一件事 2 秒内只弹一次
            if self.notify_gate.allow(mapped.state, mapped.text, mapped.session,
                                      changed, self.settings, time.time()):
                toast('Claude 桌宠',
                      core_view_model.notify_body(mapped.text, mapped.project,
                                                  bool(self.settings.get('privacy'))))
                flash_claude()
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

    def watch_lifecycle(self):
        # 没有活跃会话（ts+TTL 判定，#4）超过两分钟，桌宠自己退出。
        # 不再靠 tasklist 找 claude.exe：终端里的 Claude 进程名对不上会误退。
        if core_sessions.has_live_session(SESSIONS):
            self.last_alive = time.time()
        elif time.time() - self.last_alive > 120:
            self.root.destroy()
            return
        self.schedule(30000, self.watch_lifecycle)


if __name__ == '__main__':
    if _SHOT_PATH is None:  # --shot 是诊断/测试路径，不参与抢锁
        acquire_lock(QUIET)
    server = None
    try:
        pet = Pet()
        if _SHOT_PATH is None:  # 审批桥随真桌宠起停（#13/#15）
            from bridge.server import BridgeServer
            server = BridgeServer(RUN_DIR, on_request=pet.permission_incoming,
                                  on_settled=pet.permission_settled)
            server.start()
            pet.attach_bridge(server)
        pet.root.mainloop()
    except Exception:
        import traceback
        with open(os.path.join(RUN_DIR, 'pet-error.log'), 'w', encoding='utf-8') as f:
            traceback.print_exc(file=f)
    finally:
        if server is not None:
            server.stop()  # pending 全转 ask + 删 bridge.json
