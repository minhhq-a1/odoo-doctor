from . import __helpers


def post_init_hook(env):
    eval(env.context.get("expr"))
