# platform/mac：无边框透明 NSWindow + PetView 自绘（气泡/立绘/拖拽）与立绘加载、窗口几何、自截图。
from __future__ import annotations

import math
import os
import time

from AppKit import (NSBezierPath, NSColor, NSCompositingOperationSourceOver, NSFont,
                    NSFontAttributeName, NSForegroundColorAttributeName, NSGraphicsContext,
                    NSImage, NSImageInterpolationHigh, NSPNGFileType, NSScreen, NSView, NSWindow,
                    NSWindowCollectionBehaviorCanJoinAllSpaces,
                    NSWindowCollectionBehaviorFullScreenAuxiliary)
from Foundation import NSAttributedString, NSMakePoint, NSMakeRect

from core import errors as core_errors
from core.models import SIZES, SPRITES
from core.state_reader import number as _number

TEXT = NSColor.colorWithCalibratedRed_green_blue_alpha_(0x3a / 255, 0x2a / 255, 0x1a / 255, 1)
CREAM = NSColor.colorWithCalibratedRed_green_blue_alpha_(0xff / 255, 0xfa / 255, 0xf3 / 255, 1)
ORANGE = NSColor.colorWithCalibratedRed_green_blue_alpha_(0xe8 / 255, 0x74 / 255, 0x3b / 255, 1)


class PetView(NSView):
    """自绘内容：上方气泡，下方立绘。没画到的地方就是透明的。"""

    pet = None  # 应用控制器（Pet）：状态、文案、菜单动作等用例
    ctl = None  # PetWindow：尺寸、立绘、字体等绘制上下文
    drag0 = None

    def drawRect_(self, rect):
        try:
            self.draw_content(rect)
        except Exception:
            # AppKit 会对 drawRect 里抛出的异常直接杀进程，先记下来。
            # 记日志本身也不能抛：运行目录不可写时会把整个进程带走。
            core_errors.log_exception(self.ctl.run_dir)

    def draw_content(self, rect):
        pet, ctl = self.pet, self.ctl
        if os.environ.get('PET_DRAW_DEBUG'):
            with open('/tmp/pet-draw.log', 'a') as f:
                f.write(f'draw {pet.state} {ctl.W}x{ctl.H}\n')
        if pet is None:
            return
        ctx = NSGraphicsContext.currentContext()
        ctx.setImageInterpolation_(NSImageInterpolationHigh)
        W, H = ctl.W, ctl.H
        s = ctl.scale

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
        img = ctl.images.get(st) or ctl.fallback_image
        if img is not None:
            iw = ctl.char_h * ctl.aspects.get(st, 0.73)
            rect = NSMakeRect((W - iw) / 2, 4 - (bob + hop) * s, iw, ctl.char_h)
            img.drawInRect_fromRect_operation_fraction_(rect, NSMakeRect(0, 0, 0, 0),
                                                        NSCompositingOperationSourceOver, 1.0)

        # 气泡：圆角矩形 + 下面的尾巴
        text = pet.display_text()
        pad = round(10 * s)
        attrs = {NSFontAttributeName: ctl.font, NSForegroundColorAttributeName: TEXT}

        def measure(t):
            return NSAttributedString.alloc().initWithString_attributes_(t, attrs).size()

        # 气泡宽度被窗口卡死（最多 W-4），文字太长会溢出气泡，
        # 逐字截到放得下为止。
        limit = W - 4 - 2 * pad
        tsz = measure(text)
        if tsz.width > limit:
            trimmed = text
            while trimmed:
                trimmed = trimmed[:-1]
                tsz = measure(trimmed + '…')
                if tsz.width <= limit:
                    break
            text = trimmed + '…'
            tsz = measure(text)
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
            self.pet.save_position(f.origin.x, f.origin.y)
        self.drag0 = None

    def rightMouseDown_(self, e):
        self.pet.show_menu(e.locationInWindow())

    # 菜单 target 是 view，这里转发给 Pet（漏转发的动作 AppKit 会把菜单项禁用）
    def setSize_(self, sender):
        self.pet.setSize_(sender)

    def toggleHide_(self, sender):
        self.pet.toggleHide_(sender)

    def toggleSound_(self, sender):
        self.pet.toggleSound_(sender)

    def togglePrivacy_(self, sender):
        self.pet.togglePrivacy_(sender)

    def toggleNotify_(self, sender):
        self.pet.toggleNotify_(sender)

    def toggleDnd_(self, sender):
        self.pet.toggleDnd_(sender)

    def goHandle_(self, sender):
        self.pet.goHandle_(sender)

    def quit_(self, sender):
        self.pet.quit_(sender)


class PetWindow:
    """无边框透明悬浮窗；立绘加载、气泡绘制尺寸、位置与截图都在此。"""

    def __init__(self, pet, sprites_dir: str, run_dir: str) -> None:
        self.pet = pet
        self.sprites_dir = sprites_dir
        self.run_dir = run_dir
        self.scale = 1.0  # mac 上尺寸直接用屏幕点数，不再按 96dpi 折算
        self.font = NSFont.fontWithName_size_('PingFangSC-Regular', 10) \
            or NSFont.systemFontSize_()
        self.small = NSFont.fontWithName_size_('PingFangSC-Regular', 8) \
            or NSFont.smallSystemFontSize()
        self.load_sprites()
        self.make_window()

    # ---------- 立绘与窗口 ----------
    def load_sprites(self):
        from PIL import Image
        h = SIZES.get(self.pet.settings.get('size', '中'), 190)
        self.char_h = h
        self.images, self.aspects = {}, {}
        for state, name in SPRITES.items():
            path = os.path.join(self.sprites_dir, name + '.png')
            img = NSImage.alloc().initWithContentsOfFile_(path)
            if img is None:
                continue
            try:
                with Image.open(path) as im:
                    aspect = im.width / im.height  # 每张保持自己的宽高比
            except Exception:
                aspect = 0.73  # PNG 坏了也要能画出来
            self.images[state] = img
            self.aspects[state] = aspect
        # 某张立绘缺失/损坏时用它替身；全都没有就只是不画立绘，别让桌宠起不来
        self.fallback_image = next(iter(self.images.values()), None)

    def make_window(self):
        self.W = max(round(self.char_h * max(self.aspects.values(), default=0.73)), round(190))
        self.bubble_h = round(52)
        self.H = self.bubble_h + round(8) + self.char_h + round(6)
        self.view = PetView.alloc().initWithFrame_(NSMakeRect(0, 0, self.W, self.H))
        self.view.pet = self.pet
        self.view.ctl = self
        self.win = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, self.W, self.H), 0, 2, False)  # 0=无边框 2=缓冲
        self.win.setContentView_(self.view)
        self.win.setOpaque_(False)
        self.win.setBackgroundColor_(NSColor.clearColor())
        self.win.setLevel_(25)  # NSStatusWindowLevel：悬浮在普通窗口上
        self.win.setHasShadow_(False)
        self.win.setCollectionBehavior_(NSWindowCollectionBehaviorCanJoinAllSpaces
                                        | NSWindowCollectionBehaviorFullScreenAuxiliary)
        self.place()
        self.win.orderFrontRegardless()
        self.refresh()

    def place(self):
        f = NSScreen.mainScreen().frame()
        x = _number(self.pet.settings.get('x'), f.origin.x + f.size.width - self.W - 40)
        y = _number(self.pet.settings.get('y'), f.origin.y + 70)
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

    def hide(self):
        self.win.orderOut_(None)

    def show(self):
        self.win.orderFrontRegardless()

    def capture(self, path: str) -> None:
        """自测用：把桌宠画成 PNG（抓自己不用屏幕录制权限）。

        早先用 CGWindowListCreateImage 抓窗口号：透明窗口没有自己的后备存储，
        抓回来的是桌宠背后屏幕的内容（实测抓到终端），截图等于没用。
        改成把 view 用 cacheDisplay 渲染进 bitmapImageRep——画的是桌宠自己。
        """
        view = self.view
        bounds = view.bounds()
        rep = view.bitmapImageRepForCachingDisplayInRect_(bounds)
        view.cacheDisplayInRect_toBitmapImageRep_(bounds, rep)
        data = rep.representationUsingType_properties_(NSPNGFileType, {})
        if data is not None:
            data.writeToFile_atomically_(path, True)
        self.capture_screen(path)

    def capture_screen(self, path: str) -> None:
        """顺带存一张整屏的（需要屏幕录制权限，没有就跳过）。"""
        try:
            from Quartz import (CGWindowListCreateImage, CGImageDestinationCreateWithURL,
                                CGImageDestinationAddImage, CGImageDestinationFinalize)
            from CoreFoundation import CFURLCreateWithFileSystemPath, kCFURLPOSIXPathStyle

            f = self.win.frame()
            # AppKit 用左下角原点，CG 截图用左上角原点，换算一下
            primary = NSScreen.screens()[0].frame()
            cg_y = primary.size.height - f.origin.y - f.size.height
            rect = ((f.origin.x, cg_y), (f.size.width, f.size.height))
            img = CGWindowListCreateImage(rect, 0, 0, 0)
            if img is None:
                return
            stem = os.path.splitext(path)[0]
            out = f'{stem}-screen.png'
            url = CFURLCreateWithFileSystemPath(None, out, kCFURLPOSIXPathStyle, False)
            dest = CGImageDestinationCreateWithURL(url, 'public.png', 1, None)
            if dest is None:
                return
            CGImageDestinationAddImage(dest, img, None)
            CGImageDestinationFinalize(dest)
        except Exception:
            pass
