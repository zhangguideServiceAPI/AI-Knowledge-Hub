"""创建应用级 PromptCenter 实例。

FastAPI 的依赖注入可以直接使用 ``get_prompt_center``：第一次调用会创建实例并预加载
全部模板，后续调用复用同一个实例。测试可以单独构造 ``PromptCenter(tmp_path)``，
不必依赖这里的全局缓存。
"""

from functools import lru_cache

from app.ai.prompt_center.center import PromptCenter


@lru_cache(maxsize=1)
def get_prompt_center() -> PromptCenter:
    """返回已经完成预加载的应用级 PromptCenter。

    ``@lru_cache`` 原本用于缓存“函数参数 -> 返回值”。这里的函数没有参数，所有调用
    的缓存键都相同；``maxsize=1`` 因而使它表现为一个懒加载的单例：

    1. 第一次调用执行函数体，校验全部 Prompt，然后缓存 ``center``；
    2. 后续调用直接返回同一个对象，不再重复读取磁盘；
    3. 如果首次 ``preload()`` 抛出异常，本次结果不会进入缓存，应用启动应失败。

    单例的生命周期由函数缓存管理，不代表 ``PromptCenter`` 类本身只能创建一个实例。
    """

    center = PromptCenter()
    center.preload()
    return center
