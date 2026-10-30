# core：命令行参数解析。纯函数，不碰平台/文件系统。
import os

SHOT_FLAG = '--shot'


def parse_args(argv, default_run_dir):
    """拆出 (run_dir, shot_path)。

    - 开关（--xxx）不是位置参数；
    - --shot 后面跟的是**截图输出路径**，不能当成运行目录
      （否则桌宠会去 /tmp/shot.png/sessions 里找状态文件）；
    - shot_path 为 None 表示没给 --shot，为 '' 表示给了 --shot 但没给路径。

    argv 只传位置参数（不含程序名）。
    """
    run_dir = None
    shot_path = None
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == SHOT_FLAG:
            nxt = argv[i + 1] if i + 1 < len(argv) else ''
            shot_path = '' if nxt.startswith('-') else nxt
            i += 2
            continue
        if arg.startswith('-'):
            i += 1
            continue
        if run_dir is None:
            run_dir = arg
        i += 1
    return (run_dir or default_run_dir), shot_path


def default_run_dir():
    """默认运行目录 ~/.claude/desk-pet。"""
    return os.path.join(os.path.expanduser('~'), '.claude', 'desk-pet')
