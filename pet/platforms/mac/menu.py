# platform/mac：右键菜单。只负责 NSMenu 构建与勾选状态；动作经 PetView 转发回 Pet（app 层用例）。
from __future__ import annotations

import time

from AppKit import NSMenu, NSMenuItem

from core import aggregate as core_aggregate
from core.models import SIZES


class PetMenu:
    def __init__(self, pet) -> None:
        self.pet = pet
        self.menu = NSMenu.alloc().init()
        self._session_items: list[NSMenuItem] = []  # 会话区（M3 #22），popup 前按最近一帧重建
        self._session_sep: NSMenuItem | None = None
        self.size_items = {}
        for name in SIZES:
            it = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(name, 'setSize:', '')
            it.setTarget_(pet.view)
            it.setState_(1 if name == pet.settings.get('size', '中') else 0)
            self.menu.addItem_(it)
            self.size_items[name] = it
        self.hide_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            '切到 Claude 时自动隐藏', 'toggleHide:', '')
        self.hide_item.setTarget_(pet.view)
        self.hide_item.setState_(1 if pet.settings.get('hideOnFocus') else 0)
        self.menu.addItem_(self.hide_item)
        self.sound_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            '提示音', 'toggleSound:', '')
        self.sound_item.setTarget_(pet.view)
        self.sound_item.setState_(1 if pet.settings.get('sound', True) else 0)
        self.menu.addItem_(self.sound_item)
        self.privacy_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            '隐私模式（不写项目/文件名）', 'togglePrivacy:', '')
        self.privacy_item.setTarget_(pet.view)
        self.privacy_item.setState_(1 if pet.settings.get('privacy') else 0)
        self.menu.addItem_(self.privacy_item)
        self.notify_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            '原生通知', 'toggleNotify:', '')
        self.notify_item.setTarget_(pet.view)
        self.notify_item.setState_(1 if pet.settings.get('notify', True) else 0)
        self.menu.addItem_(self.notify_item)
        self.dnd_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            '勿扰模式（不弹横幅不响铃）', 'toggleDnd:', '')
        self.dnd_item.setTarget_(pet.view)
        self.dnd_item.setState_(1 if pet.settings.get('dnd') else 0)
        self.menu.addItem_(self.dnd_item)
        go_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            '去处理（切到终端）', 'goHandle:', '')
        go_item.setTarget_(pet.view)
        self.menu.addItem_(go_item)
        self.menu.addItem_(NSMenuItem.separatorItem())
        quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_('退出桌宠', 'quit:', '')
        quit_item.setTarget_(pet.view)
        self.menu.addItem_(quit_item)

    def update_size_state(self, name: str) -> None:
        for n, it in self.size_items.items():
            it.setState_(1 if n == name else 0)

    def rebuild_sessions(self) -> None:
        """会话区（M3 #22）：清旧项，按最近一帧 poll 的状态重建，插在菜单最上面。

        单会话也显示（与气泡计数不同：菜单是「都有谁在跑」的入口）；
        没有活跃会话时整段不出现。
        """
        while self._session_items:
            self.menu.removeItem_(self._session_items.pop())
        if self._session_sep is not None:
            self.menu.removeItem_(self._session_sep)
            self._session_sep = None
        entries = core_aggregate.session_entries(
            getattr(self.pet, 'last_states', []),
            getattr(self.pet, 'main_session', ''), time.time())
        if not entries:
            return
        for i, (label, sid, is_main) in enumerate(entries):
            it = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(label, 'pickSession:', '')
            it.setTarget_(self.pet.view)
            it.setRepresentedObject_(sid)
            it.setState_(1 if is_main else 0)
            self.menu.insertItem_atIndex_(it, i)
            self._session_items.append(it)
        self._session_sep = NSMenuItem.separatorItem()
        self.menu.insertItem_atIndex_(self._session_sep, len(entries))

    def popup(self, view, point) -> None:
        self.rebuild_sessions()
        p = view.convertPoint_fromView_(point, None)
        self.menu.popUpMenu_positionItem_atPoint_inView_(self.menu, None, p, view)
