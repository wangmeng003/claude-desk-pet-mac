# core：把异常安全地写进运行目录。只用 stdlib，不碰平台 API。
import os
import traceback


def log_exception(run_dir, name='pet-error.log') -> bool:
    """把当前异常写进 run_dir；写不进去就退回 stderr。

    绝不能让「记日志」本身抛异常：
    - AppKit 会对 drawRect 里抛出的异常直接杀进程；
    - 顶层异常处理器抛异常会把原始堆栈也弄丢。
    """
    try:
        os.makedirs(run_dir, exist_ok=True)
        with open(os.path.join(run_dir, name), 'a', encoding='utf-8') as f:
            f.write(traceback.format_exc())
            f.write('\n')
        return True
    except Exception:
        traceback.print_exc()
        return False
