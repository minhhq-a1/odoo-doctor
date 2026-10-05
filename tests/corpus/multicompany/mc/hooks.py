def post_init_hook(env):
    env.ref("base.main_company").write({"name": "Configured"})
