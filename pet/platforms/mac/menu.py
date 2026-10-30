# platform/mac：右键菜单。只负责 NSMenu 构建与勾选状态；动作经 PetView 转发回 Pet（app 层用例）。
from __future__ import annotations

from AppKit import NSMenu, NSMenuItem

from core.models import SIZES


class PetMenu:
    def __init__(self, pet) -> None:
        self.pet = pet
        self.menu = NSMenu.alloc().init()
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
        self.menu.addItem_(NSMenuItem.separatorItem())
        quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_('退出桌宠', 'quit:', '')
        quit_item.setTarget_(pet.view)
        self.menu.addItem_(quit_item)

    def update_size_state(self, name: str) -> None:
        for n, it in self.size_items.items():
            it.setState_(1 if n == name else 0)

    def popup(self, view, point) -> None:
        p = view.convertPoint_fromView_(point, None)
        self.menu.popUpMenu_positionItem_atPoint_inView_(self.menu, None, p, view)
