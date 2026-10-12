def migrate(cr, version):
    # Runs on a pre-removal database, where name_get still exists.
    env = None
    return env.name_get()
