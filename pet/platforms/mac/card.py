# platform/mac：权限审批卡片（#15，specs/permission.md §5.5）。只收 PermissionRequestViewModel，
# 决策经 pet 控制器转 bridge（renderer 不 import bridge）。detail 只存在本窗口内存，不落盘。
from __future__ import annotations

from AppKit import (NSButton, NSColor, NSFont, NSMakeRect, NSTextField,
                    NSTitledWindowMask, NSWindow, NSWindowCollectionBehaviorCanJoinAllSpaces,
                    NSWindowCollectionBehaviorFullScreenAuxiliary)
from Foundation import NSObject

from core import view_model as core_view_model
from core.models import PermissionRequestViewModel

BADGE = {
    'high': ('高危 · 破坏性操作', (0.85, 0.20, 0.15)),
    'medium': ('中风险', (0.90, 0.60, 0.10)),
}
W, H = 360, 300  # 定高：详情区常驻占位，展开只切 hidden（改高度会挪坏底锚定的子视图）


class CardActions(NSObject):
    """NSButton target/delegate 转发（AppKit 需要真 NSObject 才认 selector）。"""
    card = None

    def allowAction_(self, sender):
        self.card.on_allow()

    def denyAction_(self, sender):
        self.card.on_deny()

    def deferAction_(self, sender):
        self.card.on_defer()

    def toggleAction_(self, sender):
        self.card.toggle_detail()

    def windowWillClose_(self, note):
        self.card.on_close()


class PermissionCard:
    """单请求卡片：项目/工具/摘要/风险徽标/展开命令/三按钮/倒计时。"""

    def __init__(self, pet, vm: PermissionRequestViewModel, deadline: float) -> None:
        self.pet = pet
        self.vm = vm
        self.deadline = deadline
        self._settled = False
        self._armed = False        # 高风险 Allow 的二次确认
        self._detail_open = False
        self.actions = CardActions.alloc().init()
        self.actions.card = self

        self.win = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, W, H), NSTitledWindowMask, 2, False)
        self.win.setTitle_('Claude 需要你确认')
        self.win.setDelegate_(self.actions)
        self.win.setCollectionBehavior_(NSWindowCollectionBehaviorCanJoinAllSpaces
                                        | NSWindowCollectionBehaviorFullScreenAuxiliary)
        self._build()

    # ---------- 布局 ----------
    def _label(self, text, font, color, x, y, w, h, wrap=False):
        t = NSTextField.alloc().initWithFrame_(NSMakeRect(x, y, w, h))
        t.setEditable_(False)
        t.setSelectable_(True)
        t.setBordered_(False)
        t.setDrawsBackground_(False)
        t.setFont_(font)
        t.setTextColor_(color)
        t.setStringValue_(text)
        if wrap:
            t.setUsesSingleLineMode_(False)
            t.cell().setWraps_(True)
        return t

    def _build(self):
        title_font = NSFont.boldSystemFontOfSize_(14)
        body_font = NSFont.systemFontOfSize_(12)
        small_font = NSFont.systemFontOfSize_(10)
        gray = NSColor.disabledControlTextColor()
        dark = NSColor.controlTextColor()
        red = NSColor.systemRedColor()

        self.win.contentView().addSubview_(self._label(
            'Claude 需要你确认', title_font, dark, 12, H - 28, 210, 20))
        self.countdown = self._label('', small_font, gray, 240, H - 28, 108, 16)
        self.win.contentView().addSubview_(self.countdown)

        meta = f'{self.vm.tool} · {self.vm.project}' if self.vm.project else self.vm.tool
        self.win.contentView().addSubview_(self._label(meta, small_font, gray, 12, H - 50, 336, 14))

        self.win.contentView().addSubview_(self._label(
            self.vm.summary, body_font, dark, 12, H - 92, 336, 34, wrap=True))

        badge_text, rgb = BADGE.get(self.vm.risk, ('', (0, 0, 0)))
        if badge_text:
            badge = NSTextField.alloc().initWithFrame_(NSMakeRect(12, H - 112, 150, 18))
            badge.setEditable_(False)
            badge.setBordered_(False)
            badge.setDrawsBackground_(True)
            badge.setBackgroundColor_(NSColor.colorWithCalibratedRed_green_blue_alpha_(*rgb, 0.18))
            badge.setTextColor_(red if self.vm.risk == 'high' else NSColor.orangeColor())
            badge.setAlignment_(1)  # center
            badge.setStringValue_(badge_text)
            self.win.contentView().addSubview_(badge)

        # 展开命令：detail 只在这里（内存），关窗即丢；定高窗口，展开只切 hidden
        self.detail = NSTextField.alloc().initWithFrame_(NSMakeRect(12, 104, 336, 92))
        self.detail.setEditable_(False)
        self.detail.setSelectable_(True)  # 可复制，不可编辑
        self.detail.setBordered_(True)
        self.detail.setFont_(NSFont.monospacedSystemFontOfSize_weight_(11, 0.0))
        self.detail.setStringValue_(self.vm.detail or '（无详情）')
        self.detail.setHidden_(True)
        self.win.contentView().addSubview_(self.detail)

        self.toggle = self._button('展开命令 ▸', 'toggleAction:', 12, 72, 108, 24)
        default = core_view_model.card_default_focus(self.vm.risk)
        bw = 84
        self.btn_allow = self._button('允许', 'allowAction:', 12, 16, bw, 28, default == 'allow')
        self.btn_deny = self._button('拒绝', 'denyAction:', 12 + bw + 8, 16, bw, 28, False)
        self.btn_defer = self._button('回退终端', 'deferAction:', 12 + (bw + 8) * 2, 16, 100, 28,
                                      default == 'defer')
        self.btn_defer.setKeyEquivalent_('\x1b')  # Esc = 回退终端（高风险禁不了这个）
        self.win.setInitialFirstResponder_(
            self.btn_defer if default == 'defer' else self.btn_allow)

    def _button(self, title, action, x, y, w, h, is_default=False):
        b = NSButton.alloc().initWithFrame_(NSMakeRect(x, y, w, h))
        b.setTitle_(title)
        b.setTarget_(self.actions)
        b.setAction_(action)
        b.setBezelStyle_(1)  # rounded
        if is_default:
            b.setKeyEquivalent_('\r')
        self.win.contentView().addSubview_(b)
        return b

    # ---------- 行为 ----------
    def tick(self, now: float) -> None:
        self.countdown.setStringValue_(
            core_view_model.card_countdown_text(self.deadline - now))

    def show(self, origin=None):
        f = self.win.frame()
        x, y = origin if origin else (f.origin.x, f.origin.y)
        self.win.setFrame_display_(NSMakeRect(x, y, f.size.width, f.size.height), False)
        self.win.orderFrontRegardless()

    def toggle_detail(self):
        self._detail_open = not self._detail_open
        self.detail.setHidden_(not self._detail_open)
        self.toggle.setTitle_('收起命令 ▾' if self._detail_open else '展开命令 ▸')

    def on_allow(self):
        if self.vm.risk == 'high' and not self._armed:
            self._armed = True
            self.btn_allow.setTitle_('确认放行？再点一次')
            return
        self._settle('allow')

    def on_deny(self):
        self._settle('deny')

    def on_defer(self):
        self._settle('ask')

    def on_close(self):
        # 用户关卡片 = ask（不是 deny，spec §5.4）
        self._settle('ask')

    def settle_if_matching(self, rid: str) -> bool:
        """bridge 侧已结束（超时/退出）时由宠物调；匹配才关。"""
        if rid == self.vm.id and not self._settled:
            self._settled = True  # 只关窗，不再发决策（决策已在桥侧产生）
            self.close()
            return True
        return False

    def _settle(self, decision: str):
        if self._settled:
            return
        self._settled = True
        self.close()
        self.pet.permission_decide(self.vm.id, decision)

    def close(self):
        self.win.setDelegate_(None)
        self.win.orderOut_(None)
        self.win.close()
