# /pet theme 的命令行入口（M4，specs/theme.md §4）：hooks 用 python 跑本脚本，
# stdout 原样回显给用户。校验/安装/切换主体在 theme/ 包里（纯 stdlib，
# 系统 python3 即可跑，不依赖插件 venv）。
# 用法：python theme_cli.py <命令> [参数…] <运行目录>   ——详见 theme.manager.USAGE
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

# Windows 默认 stdout 是 ANSI 代码页，中文 print 直接 UnicodeEncodeError；
# hooks 抓的就是本脚本 stdout，先把输出流钉死成 UTF-8 再干活（同 doctor.py）。
for _stream in (sys.stdout, sys.stderr):
    _reconfigure = getattr(_stream, 'reconfigure', None)
    if _reconfigure is not None:
        try:
            _reconfigure(encoding='utf-8')
        except ValueError:
            pass

from theme import manager  # noqa: E402  (pet/ 进 sys.path 后才能导入)


def main():
    text, code = manager.main(sys.argv[1:])
    if text:
        print(text)
    sys.exit(code)


if __name__ == '__main__':
    main()
