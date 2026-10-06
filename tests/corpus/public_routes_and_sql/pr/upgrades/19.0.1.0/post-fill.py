def migrate(cr, version):
    table = cr.dbname
    cr.execute(f"UPDATE {table} SET active = TRUE")
