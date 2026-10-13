def migrate(cr, version):
    env = None
    cr.commit()  # one-off script: fine
    env.cr.commit()
