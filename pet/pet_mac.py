# Claude 娘桌宠悬浮窗 · macOS 版
# Tk 的 canvas 在 macOS 上画不出透明背景，所以这里直接用 pyobjc 的原生 NSWindow：
# 无边框 + 透明底，气泡和立绘都画在一个自绘 NSView 上。
# 状态文件、设置文件和 Windows 版 pet.pyw 保持同一套约定。
# 用法：python pet_mac.py <运行目录>
import math
import os
import socket
import subprocess
import sys
import time

from AppKit import (NSApplication, NSApplicationActivationPolicyAccessory, NSBezierPath,
                    NSColor, NSCompositingOperationSourceOver, NSFont, NSFontAttributeName,
                    NSForegroundColorAttributeName, NSGraphicsContext, NSImage,
                    NSImageInterpolationHigh, NSMenu, NSMenuItem, NSScreen,
                    NSWindow, NSWindowCollectionBehaviorCanJoinAllSpaces,
                    NSWindowCollectionBehaviorFullScreenAuxiliary, NSView, NSWorkspace)
from Foundation import NSMakePoint, NSMakeRect, NSAttributedString, NSTimer

from core import sessions as core_sessions
from core import state_reader as core_state_reader
from core import view_model as core_view_model
from core.models import IDLE_AFTER, SIZES, SPRITES  # noqa: F401  (本文件的渲染代码与测试直接用)

HERE = os.path.dirname(os.path.abspath(__file__))
SOUNDS = os.path.join(os.path.dirname(HERE), 'sounds')
_args = [a for a in sys.argv[1:] if not a.startswith('-')]  # 兼容 --shot 这类开关
RUN_DIR = _args[0] if _args else os.path.join(os.path.expanduser('~'), '.claude', 'desk-pet')
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

TEXT = NSColor.colorWithCalibratedRed_green_blue_alpha_(0x3a / 255, 0x2a / 255, 0x1a / 255, 1)
CREAM = NSColor.colorWithCalibratedRed_green_blue_alpha_(0xff / 255, 0xfa / 255, 0xf3 / 255, 1)
ORANGE = NSColor.colorWithCalibratedRed_green_blue_alpha_(0xe8 / 255, 0x74 / 255, 0x3b / 255, 1)


def play_sound(path):
    try:
        subprocess.Popen(['afplay', path], stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def claude_pids():
    """正在跑的 claude 进程 pid 列表；查不到就当作还在跑。"""
    try:
        out = subprocess.run(['pgrep', '-f', r'(^|/)claude( |$)|node.*claude'],
                             capture_output=True, text=True, timeout=10).stdout
        mine = {os.getpid(), os.getppid()}
        return {int(p) for p in out.split() if p.isdigit() and int(p) not in mine}
    except Exception:
        return {0}


def ppid(pid):
    try:
        out = subprocess.run(['ps', '-o', 'ppid=', '-p', str(pid)],
                             capture_output=True, text=True, timeout=5).stdout.strip()
        return int(out) if out.isdigit() else None
    except Exception:
        return None


def claude_app_pids():
    """包着 claude 进程的 App（终端/iTerm/编辑器）的 pid 集合。"""
    ws = NSWorkspace.sharedWorkspace()
    app_pids = {a.processIdentifier() for a in ws.runningApplications() if a.processIdentifier() > 0}
    result = set()
    for pid in claude_pids():
        seen = set()
        while pid > 1 and pid not in seen:
            seen.add(pid)
            if pid in app_pids:
                result.add(pid)
                break
            pid = ppid(pid) or 0
    return result


def load_settings():
    return core_state_reader.load_settings(SETTINGS)


def save_settings(s):
    core_state_reader.save_settings(SETTINGS, s)


def read_latest():
    """读所有会话里最新的状态；顺手清掉过期文件。"""
    return core_sessions.read_latest(SESSIONS)


class PetView(NSView):
    """自绘内容：上方气泡，下方立绘。没画到的地方就是透明的。"""

    pet = None
    drag0 = None

    def drawRect_(self, rect):
        try:
            self.draw_content(rect)
        except Exception:
            # AppKit 会对 drawRect 里抛出的异常直接杀进程，先记下来
            import traceback
            with open(os.path.join(RUN_DIR, 'pet-error.log'), 'a', encoding='utf-8') as f:
                traceback.print_exc(file=f)

    def draw_content(self, rect):
        pet = self.pet
        if os.environ.get('PET_DRAW_DEBUG'):
            with open('/tmp/pet-draw.log', 'a') as f:
                f.write(f'draw {pet.state} {pet.W}x{pet.H}\n')
        if pet is None:
            return
        ctx = NSGraphicsContext.currentContext()
        ctx.setImageInterpolation_(NSImageInterpolationHigh)
        W, H = pet.W, pet.H
        s = pet.scale

        # 立绘：底边中央，带呼吸/发抖/小跳的纵向偏移（原版的 animate 逻辑）
        st = pet.effective_state()
        t = time.time()
        if st == 'stone':
            bob = 0
        elif st == 'tool':
            bob = 2.5 * math.sin(t * 9)
        elif st == 'error':
            bob = 2 * math.sin(t * 25)
        else:
            bob = 3 * math.sin(t * 2.2)
        since = t - pet.hop_at
        hop = -14 * math.sin(since / 0.28 * math.pi) if since < 0.28 else 0
        img = pet.images[st]
        iw = pet.char_h * pet.aspects.get(st, 0.73)
        rect = NSMakeRect((W - iw) / 2, 4 - (bob + hop) * s, iw, pet.char_h)
        img.drawInRect_fromRect_operation_fraction_(rect, NSMakeRect(0, 0, 0, 0),
                                                    NSCompositingOperationSourceOver, 1.0)

        # 气泡：圆角矩形 + 下面的尾巴
        text = pet.display_text()
        pad = round(10 * s)
        attrs = {NSFontAttributeName: pet.font, NSForegroundColorAttributeName: TEXT}
        tsz = NSAttributedString.alloc().initWithString_attributes_(text, attrs).size()
        bw = min(max(tsz.width + 2 * pad, 80 * s), W - 4)
        x0 = (W - bw) / 2
        y_top, y_bot = H - 2 * s, H - 38 * s           # 气泡身体（视图坐标系，原点在左下）
        tail_bot = y_bot - 10 * s
        body = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
            NSMakeRect(x0, y_bot, bw, y_top - y_bot), 12 * s, 12 * s)
        tail = NSBezierPath.bezierPath()
        tail.moveToPoint_(NSMakePoint(W / 2 + 8 * s, y_bot + 1))
        tail.lineToPoint_(NSMakePoint(W / 2, tail_bot))
        tail.lineToPoint_(NSMakePoint(W / 2 - 4 * s, y_bot + 1))
        tail.closePath()
        body.appendBezierPath_(tail)
        CREAM.setFill()
        ORANGE.setStroke()
        body.fill()
        body.setLineWidth_(max(2, round(2 * s)))
        body.stroke()

        # 文字：气泡里水平居中（“思考中”的点点点在 tick 里自己变）
        tp = NSMakePoint((W - tsz.width) / 2, y_bot + (y_top - y_bot - tsz.height) / 2)
        NSAttributedString.alloc().initWithString_attributes_(text, attrs).drawAtPoint_(tp)

    def mouseDown_(self, e):
        pet = self.pet
        if e.clickCount() == 2:
            pet.bring_claude_front()
            return
        self.drag0 = (e.locationInWindow(), self.window().frame().origin)

    def mouseDragged_(self, e):
        if self.drag0 is None:
            return
        loc, origin = self.drag0
        now = e.locationInWindow()
        self.window().setFrameOrigin_(NSMakePoint(origin.x + now.x - loc.x, origin.y + now.y - loc.y))

    def mouseUp_(self, e):
        if self.drag0 is not None:
            f = self.window().frame()
            self.pet.settings['x'], self.pet.settings['y'] = f.origin.x, f.origin.y
            save_settings(self.pet.settings)
        self.drag0 = None

    def rightMouseDown_(self, e):
        self.pet.show_menu(e.locationInWindow())

    # 菜单 target 是 view，这里转发给 Pet
    def setSize_(self, sender):
        self.pet.setSize_(sender)

    def toggleHide_(self, sender):
        self.pet.toggleHide_(sender)

    def toggleSound_(self, sender):
        self.pet.toggleSound_(sender)

    def quit_(self, sender):
        self.pet.quit_(sender)


class Pet:
    def __init__(self):
        self.settings = load_settings()
        self.scale = 1.0  # mac 上尺寸直接用屏幕点数，不再按 96dpi 折算
        self.font = NSFont.fontWithName_size_('PingFangSC-Regular', 10) \
            or NSFont.systemFontSize_()
        self.small = NSFont.fontWithName_size_('PingFangSC-Regular', 8) \
            or NSFont.smallSystemFontSize()
        self.state, self.text, self.project = 'waiting', '我来啦～', ''
        self.state_since = time.time()
        self.last_mtime = 0
        self.last_mtime_seen = 0
        self.hop_at = time.time()
        self.hidden = False
        self.last_alive = time.time()
        self.app_pids = set()
        self.app_pids_at = 0

        self.load_sprites()
        self.make_window()
        self.make_menu()

    # ---------- 窗口 ----------
    def load_sprites(self):
        from PIL import Image
        h = SIZES.get(self.settings.get('size', '中'), 190)
        self.char_h = h
        self.images, self.aspects = {}, {}
        for state, name in SPRITES.items():
            path = os.path.join(HERE, 'sprites', name + '.png')
            img = NSImage.alloc().initWithContentsOfFile_(path)
            if img is None:
                continue
            self.images[state] = img
            with Image.open(path) as im:
                self.aspects[state] = im.width / im.height  # 每张保持自己的宽高比

    def make_window(self):
        self.W = max(round(self.char_h * max(self.aspects.values(), default=0.73)), round(190))
        self.bubble_h = round(52)
        self.H = self.bubble_h + round(8) + self.char_h + round(6)
        self.view = PetView.alloc().initWithFrame_(NSMakeRect(0, 0, self.W, self.H))
        self.view.pet = self
        self.win = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, self.W, self.H), 0, 2, False)  # 0=无边框 2=缓冲
        self.win.setContentView_(self.view)
        self.win.setOpaque_(False)
        self.win.setBackgroundColor_(NSColor.clearColor())
        self.win.setLevel_(25)  # NSStatusWindowLevel：悬浮在普通窗口上
        self.win.setHasShadow_(False)
        self.win.setCollectionBehavior_(NSWindowCollectionBehaviorCanJoinAllSpaces
                                        | NSWindowCollectionBehaviorFullScreenAuxiliary)
        self.place_window()
        self.win.orderFrontRegardless()
        self.refresh()

    def place_window(self):
        f = NSScreen.mainScreen().frame()
        x = self.settings.get('x', f.origin.x + f.size.width - self.W - 40)
        y = self.settings.get('y', f.origin.y + 70)
        x = min(max(f.origin.x, x), f.origin.x + f.size.width - 40)
        y = min(max(f.origin.y, y), f.origin.y + f.size.height - 40)
        self.win.setFrameOrigin_(NSMakePoint(x, y))

    def resize(self):
        # 保持底边中点不动地换大小
        f = self.win.frame()
        cx, cy = f.origin.x + f.size.width / 2, f.origin.y
        self.load_sprites()
        self.W = max(round(self.char_h * max(self.aspects.values(), default=0.73)), round(190))
        self.H = self.bubble_h + round(8) + self.char_h + round(6)
        self.view.setFrameSize_((self.W, self.H))
        self.win.setFrame_(NSMakeRect(cx - self.W / 2, cy, self.W, self.H))
        self.refresh()

    def refresh(self):
        self.view.setNeedsDisplay_(True)

    # ---------- 菜单 ----------
    def show_menu(self, point):
        p = self.view.convertPoint_fromView_(point, None)
        self.menu.popUpMenu_positionItem_atPoint_inView_(self.menu, None, p, self.view)

    def make_menu(self):
        self.menu = NSMenu.alloc().init()
        self.size_items = {}
        for name in SIZES:
            it = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(name, 'setSize:', '')
            it.setTarget_(self.view)
            it.setState_(1 if name == self.settings.get('size', '中') else 0)
            self.menu.addItem_(it)
            self.size_items[name] = it
        self.hide_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            '切到 Claude 时自动隐藏', 'toggleHide:', '')
        self.hide_item.setTarget_(self.view)
        self.hide_item.setState_(1 if self.settings.get('hideOnFocus') else 0)
        self.menu.addItem_(self.hide_item)
        self.sound_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            '提示音', 'toggleSound:', '')
        self.sound_item.setTarget_(self.view)
        self.sound_item.setState_(1 if self.settings.get('sound', True) else 0)
        self.menu.addItem_(self.sound_item)
        self.menu.addItem_(NSMenuItem.separatorItem())
        quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_('退出桌宠', 'quit:', '')
        quit_item.setTarget_(self.view)
        self.menu.addItem_(quit_item)

    # 菜单动作（target 是 view，转发回来）
    def setSize_(self, sender):
        name = sender.title()
        self.settings['size'] = name
        save_settings(self.settings)
        for n, it in self.size_items.items():
            it.setState_(1 if n == name else 0)
        self.resize()

    def toggleHide_(self, sender):
        sender.setState_(0 if sender.state() else 1)
        self.settings['hideOnFocus'] = bool(sender.state())
        save_settings(self.settings)

    def toggleSound_(self, sender):
        sender.setState_(0 if sender.state() else 1)
        self.settings['sound'] = bool(sender.state())
        save_settings(self.settings)

    def quit_(self, sender):
        NSApplication.sharedApplication().terminate_(None)

    # ---------- 状态 ----------
    def display_text(self):
        return core_view_model.display_text_with_dots(
            self.state, self.text, time.time(), self.state_since)

    def effective_state(self):
        return core_view_model.effective_state(self.state, self.state_since, time.time())

    def poll(self):
        latest = read_latest()
        if latest and latest[0] != self.last_mtime:
            self.last_mtime_seen, self.last_mtime = self.last_mtime, latest[0]
            mapped = core_view_model.normalize(latest[1])
            changed = mapped.state != self.state
            self.state, self.text = mapped.state, mapped.text
            self.project = mapped.project
            self.state_since = time.time()
            if mapped.sound and self.settings.get('sound', True) and self.last_mtime_seen:
                play_sound(os.path.join(SOUNDS, mapped.sound + '.wav'))
            if changed:
                self.hop_at = time.time()
        self.refresh()

    def tick(self):
        # 33ms 动画帧 + “思考中”点点点
        self.refresh()

    def watch_focus(self):
        should_hide = (self.settings.get('hideOnFocus')
                       and self.claude_is_foreground()
                       and self.view.drag0 is None)
        if should_hide and not self.hidden:
            self.win.orderOut_(None)
            self.hidden = True
        elif not should_hide and self.hidden:
            self.win.orderFrontRegardless()
            self.hidden = False

    def claude_is_foreground(self):
        now = time.time()
        if now - self.app_pids_at > 30:
            self.app_pids, self.app_pids_at = claude_app_pids(), now
        front = NSWorkspace.sharedWorkspace().frontmostApplication()
        return bool(front) and front.processIdentifier() in self.app_pids

    def bring_claude_front(self):
        # 双击：把跑着 claude 的那个 App 叫到前台
        ws = NSWorkspace.sharedWorkspace()
        for a in ws.runningApplications():
            if a.processIdentifier() in claude_app_pids():
                a.activateWithOptions_(1 << 1)  # ignoreOtherApps
                return

    def watch_claude(self):
        # Claude 关掉两分钟后，桌宠也自己退出
        if claude_pids():
            self.last_alive = time.time()
        elif time.time() - self.last_alive > 120:
            NSApplication.sharedApplication().terminate_(None)
            return


def shoot(pet, path):
    """自测用：把桌宠窗口自己存成 PNG（抓自己不用屏幕录制权限）。"""
    from Quartz import CGWindowListCreateImage, CGImageDestinationCreateWithURL, \
        CGImageDestinationAddImage, CGImageDestinationFinalize
    from CoreFoundation import CFURLCreateWithFileSystemPath, kCFURLPOSIXPathStyle

    def save(img, p):
        url = CFURLCreateWithFileSystemPath(None, p, kCFURLPOSIXPathStyle, False)
        dest = CGImageDestinationCreateWithURL(url, 'public.png', 1, None)
        CGImageDestinationAddImage(dest, img, None)
        CGImageDestinationFinalize(dest)

    f = pet.win.frame()
    # AppKit 用左下角原点，CG 截图用左上角原点，换算一下
    primary = NSScreen.screens()[0].frame()
    cg_y = primary.size.height - f.origin.y - f.size.height
    rect = ((f.origin.x, cg_y), (f.size.width, f.size.height))
    save(CGWindowListCreateImage(rect, 1, pet.win.windowNumber(), 0), path)
    save(CGWindowListCreateImage(rect, 0, 0, 0), path.replace('.png', '-screen.png'))
    NSApplication.sharedApplication().terminate_(None)


def main():
    acquire_lock()
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)  # 不占 Dock
    pet = Pet()
    if '--shot' in sys.argv:  # --shot <路径>：画几帧后截图退出
        path = sys.argv[sys.argv.index('--shot') + 1]
        NSTimer.scheduledTimerWithTimeInterval_repeats_block_(1.5, False,
                                                              lambda t: shoot(pet, path))
    NSTimer.scheduledTimerWithTimeInterval_repeats_block_(0.25, True, lambda t: pet.poll())
    NSTimer.scheduledTimerWithTimeInterval_repeats_block_(0.033, True, lambda t: pet.tick())
    NSTimer.scheduledTimerWithTimeInterval_repeats_block_(0.3, True, lambda t: pet.watch_focus())
    NSTimer.scheduledTimerWithTimeInterval_repeats_block_(30, True, lambda t: pet.watch_claude())
    app.run()


if __name__ == '__main__':
    try:
        main()
    except Exception:
        import traceback
        with open(os.path.join(RUN_DIR, 'pet-error.log'), 'w', encoding='utf-8') as f:
            traceback.print_exc(file=f)
