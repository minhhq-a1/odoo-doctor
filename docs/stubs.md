# Generating Odoo version stubs

## From a source checkout
```bash
python -m odoo_doctor.graph.stubs.build_stubs source \
  --odoo-path /path/to/odoo \
  --version 20.0
```

## From a live instance (RPC)
```bash
python -m odoo_doctor.graph.stubs.build_stubs rpc \
  --rpc-url http://localhost:8069 \
  --rpc-db mydb \
  --rpc-password admin \
  --version 20.0
```

Output lands in `src/odoo_doctor/graph/stubs/data/20.0.json` and is bundled
into the wheel via hatch build config. Re-run whenever Odoo 20.0's base models
change before release.
