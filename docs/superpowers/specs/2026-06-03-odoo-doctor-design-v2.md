# Odoo Doctor — Design Spec

**Date:** 2026-06-03
**Status:** Approved
**Approach:** Contract-first pipeline (Approach A), aggregator + full graph engine

> Bản spec này thay thế bản aggregator-first trước đó. Hướng cốt lõi vẫn là
> **unified health score**, nhưng kiến trúc được tổ chức lại quanh một pipeline
> `Diagnostic` làm xương sống, và bổ sung graph engine cross-module đầy đủ ngay
> trong MVP.

---

## Problem

Team 10+ Odoo developers đã có Pylint-Odoo, OCA pre-commit hooks, và Ruff nhưng
thiếu **một câu trả lời duy nhất**: "module này có đủ khỏe để deploy không?". Mỗi
tool báo lỗi riêng lẻ, không ai tổng hợp thành một con số. Ngoài ra nhiều lỗi
Odoo nghiêm trọng là **cross-file / cross-module** (view trỏ field không tồn tại,
button gọi method thiếu, thiếu access rule, thiếu `depends`) mà không tool đơn lẻ
nào bắt được.

## Solution

Odoo Doctor là một Python CLI hoạt động như **orchestrator + graph analyzer + scorer**:

1. Chạy các external tool (Pylint-Odoo, Ruff, OCA hooks) song song, normalize
   output về một format diagnostic thống nhất.
2. Dựng một **graph engine cross-module** (ModuleContext + Hybrid Resolver) và
   chạy native rules bắt lỗi mà external tool không thấy.
3. Gom mọi diagnostic vào một pipeline chung (dedup → override → ignore →
   version-gate), tính **health score 0–100 per module**.

Giá trị cốt lõi: **một con số duy nhất** cho mỗi module, tổng hợp từ mọi nguồn.

**Target:** multi-version Odoo (14–18), phục vụ developer và coding agent.

**MVP surfaces:** CLI local + Agent skills. (PR comment / GitHub Action thiết kế
sẵn chỗ cắm, làm sau MVP.)

**Tinh thần:** build chắc, ưu tiên độ chính xác (false-positive thấp) hơn tốc độ.

---

## Architecture (Approach A — pipeline làm xương sống)

Trung tâm hệ thống là **hợp đồng `Diagnostic` duy nhất** và **pipeline xử lý**.
Mọi nguồn lỗi — external adapter và native graph engine — đều sản xuất cùng kiểu
`Diagnostic` rồi đổ vào pipeline. Pipeline không quan tâm nguồn gốc; nó chỉ chuẩn
hóa, lọc, chấm điểm, render.

```text
odoo-doctor scan ./addons/sale_custom
      |
      v
  Discovery  ── tìm module (__manifest__.py), detect Odoo version
      |
      v
  ModuleContext build ── parse manifest + python AST + xml + access CSV
      |                   + Hybrid Resolver (stub core  ▸  optional source path)
      |
      +───────────────┬──────────────────────────┐
      v               v                          v
  Native Rules    PylintOdoo Adapter        Ruff Adapter / OCA Adapter
  (đọc Context)   (chạy tool, map output)   (chạy tool, map output)
      |               |                          |
      └───────────────┴──────────────────────────┘
                      v
        ===  DIAGNOSTIC PIPELINE  ===
        dedup → severity override → ignore filter → version-gate
                      v
                Scoring engine (0–100, theo category + tier)
                      v
        Renderers:  terminal  |  json   ( |  PR comment — sau MVP )
                      v
                Agent skills tiêu thụ JSON
```

### Nguyên tắc ranh giới

- **`Diagnostic` là interface chung.** Adapter và native rule không biết gì về
  scoring/renderer; chúng chỉ trả `list[Diagnostic]`. Đổi nguồn không ảnh hưởng
  pipeline.
- **Rủi ro resolve cross-module bị nhốt trong `ModuleContext` + Resolver.** Phần
  còn lại của hệ thống không đụng Odoo core; resolver chưa hoàn hảo thì chỉ vài
  native rule bị ảnh hưởng, score/pipeline vẫn chạy.
- **Surface chỉ là renderer đọc output cuối.** PR comment sau này = thêm một
  renderer, không sửa engine.
- **Adapter là optional.** Tool không cài → adapter báo skip kèm cảnh báo, không
  làm sập scan. Adapter timeout/crash → log cảnh báo, trả list rỗng, scan tiếp
  tục với các nguồn còn lại.

---

## Diagnostic Schema

Mọi nguồn lỗi trả về list các object này:

```python
@dataclass(frozen=True)
class Diagnostic:
    module: str            # "sale_custom"
    file_path: str         # "models/sale.py" (relative tới module root)
    line: int
    column: int
    rule: str              # "view-field-not-in-model"
    category: str          # Security | Correctness | Performance | ...
    severity: str          # "error" | "warning"  (user override được)
    tier: str              # "P0" | "P1" | "P2" | "P3"  (cố định theo rule, dùng chấm điểm)
    source: str            # "native" | "pylint-odoo" | "ruff" | "oca"
    title: str             # ngắn gọn, 1 dòng
    message: str           # chi tiết: dòng nào, pattern gì
    help: str              # gợi ý fix cụ thể
    odoo_version: str      # version detect cho module này
    url: str | None        # link tới docs rule
```

**Tách bạch `tier` và `severity`:**

- `tier` (P0–P3) là *độ nghiêm trọng cố định của rule*, dùng để chấm điểm, user
  **không** đổi được.
- `severity` (error/warning) là *nhãn hiển thị + cổng CI*, user override được.

Như vậy user tinh chỉnh cái họ thấy mà không bóp méo điểm số.

`source` bắt buộc — là khóa để dedup và để debug "lỗi này từ đâu ra".

---

## Diagnostic Pipeline

Mỗi stage là một hàm thuần `list[Diagnostic] -> list[Diagnostic]`, chạy đúng thứ tự:

1. **Dedup** — gom theo `(file_path, line, category)`. Trong mỗi nhóm giữ
   `message` chi tiết hơn, ưu tiên `source="native"`. Khác category ở cùng
   file+line thì giữ cả hai (là hai lỗi thật sự khác nhau).
2. **Severity override** — config đổi `error`↔`warning` hoặc tắt rule.
3. **Ignore filter** — bỏ theo rule / file glob / module.
4. **Version-gate** — loại rule không áp dụng cho Odoo version đã detect.

**Dedup chạy trước scoring** để một lỗi bị hai tool báo không bị tính điểm hai lần.

---

## ModuleContext & Hybrid Resolver

`ModuleContext` dựng một lần cho mỗi module, *trước* khi native rules chạy:

```python
@dataclass
class ModuleContext:
    name: str
    path: Path
    odoo_version: str
    manifest: dict
    depends: list[str]
    models: dict[str, ModelInfo]      # model_name -> fields, methods, _inherit/_inherits
    xml_ids: dict[str, XmlIdInfo]
    views: list[ViewInfo]
    controllers: list[ControllerInfo]
    access_rules: list[AccessRule]    # từ ir.model.access.csv
    resolver: SymbolResolver          # tra field/method xuyên module
```

### Hybrid Resolver

Khi rule hỏi "model `res.partner` có field `partner_id` không?", resolver trả lời
theo thứ tự:

1. **Trong repo** — model/field do chính các module được scan khai báo (kể cả qua
   `_inherit`).
2. **Stub database** — bảng symbol đóng gói sẵn cho các module Odoo phổ biến theo
   từng version 14–18. (MVP: **top ~15 module** — base, mail, web, sale, purchase,
   stock, account, product, contacts, và các module hay dùng nhất.)
3. **Source path (tùy chọn)** — nếu user cấu hình `odoo_source_path`, parse thêm
   để resolve sâu, độ chính xác cao nhất.
4. **Unknown** — nếu cả ba đều không biết, trả `UNKNOWN` (KHÔNG phải `NOT_FOUND`).

### Quy tắc vàng (mặc định)

**Rule chỉ báo lỗi khi resolver khẳng định `NOT_FOUND`. Tuyệt đối không báo khi
`UNKNOWN`.** "Tôi chắc field này không tồn tại" mới flag; "tôi không biết" thì im.
Đánh đổi một ít độ phủ để đổi lấy độ tin cậy — đúng tiêu chí false-positive thấp.

### Stub database

Build bằng một **script offline** chạy một lần trên mỗi version Odoo: parse source
chính thức, trích model/field/method, lưu thành dữ liệu nén theo version, ship kèm
package. Không bắt user có Odoo source. Version Odoo mới → chạy lại script.

---

## Backend Adapters

```python
class BackendAdapter(Protocol):
    name: str
    def is_available(self) -> bool: ...          # tool đã cài chưa
    def run(self, module_path: Path, odoo_version: str) -> list[Diagnostic]: ...
```

MVP: **PylintOdoo, Ruff, OCA pre-commit** — chạy song song với nhau và với native
engine.

**Rule mapping** cho mỗi adapter, lưu dạng file dữ liệu (vd
`adapters/pylint_odoo/rule_mapping.toml`):

```toml
"sql-injection"         = { category = "Security",      tier = "P0" }
"translation-required"  = { category = "UX",            tier = "P3" }
"manifest-required-key" = { category = "ModuleHygiene", tier = "P2" }
```

Rule chưa map → category `Uncategorized`, tier `P3`, **mặc định không tính điểm**
(để rule lạ không tự kéo điểm xuống). Map dần theo thời gian.

**OCA pre-commit** phức tạp hơn (tập hợp nhiều hook qua framework pre-commit):
adapter gọi pre-commit ở chế độ máy-đọc-được, chỉ map hook tín hiệu cao, phần còn
lại để `Uncategorized`. Đây là ứng viên **lùi sang sau đầu tiên** nếu quá rối —
không ảnh hưởng kiến trúc.

---

## Scoring Model

### Điểm trừ theo tier (cố định mỗi finding)

- **P0** (critical): −25 — SQL injection, thiếu access rule, secret hardcode
- **P1** (serious): −10 — N+1 query, sudo không an toàn, kế thừa hỏng
- **P2** (moderate): −4 — thiếu ondelete, API deprecated, thiếu index
- **P3** (minor): −1 — style, thiếu string attribute, manifest warning

### Công thức

- Điểm category = `max(0, 100 − tổng_điểm_trừ_trong_category)`.
- Điểm tổng blend các category:
  `overall = 0.4 * min(category_scores) + 0.6 * avg(category_scores)`.
  (Một category thảm họa kéo mạnh điểm chung — đúng cho mục tiêu "đừng deploy
  module có lỗ bảo mật dù phần khác đẹp".)

### Category weights

`category_weights` trong config (mặc định 1.0) nhân vào điểm trừ *trước* khi tính
— cho team tạm hạ/nâng ưu tiên một mảng. Tier vẫn cố định.

### Quy tắc mặc định

- Finding `UNKNOWN`/low-confidence và `Uncategorized` **không tính điểm**.
- Đã dedup trước scoring → một lỗi hai tool báo chỉ trừ một lần.

### Nhãn

90–100 Excellent (green) · 75–89 Good (blue) · 50–74 Needs work (yellow) ·
0–49 Critical (red).

### Categories (8)

Security · Correctness · Performance · Data Integrity · Architecture · UX ·
Module Hygiene · Multi-company.

---

## Native Rules — MVP Set (12)

Nguyên tắc: chỉ làm những gì external tool không làm được. Không làm trùng việc
Pylint-Odoo/Ruff đã bắt tốt.

### Cross-file (cần ModuleContext + Resolver) — moat

1. `missing-access-rules` [Security, P0] — model persistent khai báo nhưng không
   có dòng nào trong `ir.model.access.csv`.
2. `view-field-not-in-model` [Correctness, P1] — view trỏ field mà resolver
   khẳng định NOT_FOUND trên model.
3. `button-method-not-found` [Correctness, P1] — object button gọi method không
   có trên model resolved.
4. `missing-xml-ref` [Correctness, P1] — `ref`/`inherit_id`/`env.ref()` trỏ XML
   ID không resolve được.
5. `manifest-missing-dependency` [Module Hygiene, P1] — code dùng model/XML ID
   của addon khác nhưng không khai trong `depends`.
6. `duplicate-xml-id` [Correctness, P1] — cùng một XML ID định nghĩa trùng trong
   module.

### AST pattern (per-file, không cần context)

7. `raw-sql-string-interpolation` [Security, P0] — `cr.execute()` dùng
   f-string/format/nối chuỗi thay vì tham số.
8. `public-controller-sudo-risk` [Security, P1] — controller public/`auth='public'`
   dùng `sudo()` không kèm kiểm tra quyền.
9. `search-in-loop` [Performance, P1] — `search/browse/read/write/create` gọi
   trong vòng lặp.
10. `compute-missing-depends` [Correctness, P1] — compute method đọc field không
    khai trong `@api.depends`.

### Version-aware (gated bởi Odoo version qua resolver/stub)

11. `override-missing-super` [Correctness, P1] — override `create/write/unlink`
    mà không gọi `super()`.
12. `deprecated-api` [Architecture, P2] — `api.multi`, `api.one`, `osv.osv`...
    theo version.

### Rule registration

```python
@rule(name="missing-access-rules", category="Security", severity="error",
      tier="P0", min_version="14.0", needs_context=True)
def check_missing_access_rules(ctx: ModuleContext) -> list[Diagnostic]: ...
```

`needs_context=False` chạy ở pha per-file (song song theo file);
`needs_context=True` chạy sau khi ModuleContext dựng xong.

### Cố ý KHÔNG đưa vào MVP (noisy / dễ false-positive)

`missing-string-attribute`, `no-compute-without-store`, `no-hardcoded-xml-id`,
OWL/JS rules, multi-company rules. Để dành sau khi có dữ liệu false-positive thực
tế.

---

## Config

File `odoo-doctor.toml` ở repo root hoặc thư mục module (config gần override config
xa; CLI flag override tất cả):

```toml
[odoo-doctor]
odoo_version = "17.0"          # bỏ trống thì auto-detect
odoo_source_path = ""           # tùy chọn: trỏ tới source Odoo cho resolve sâu
min_score = 60                  # ngưỡng cho --fail-on score (CI sau này)

[adapters]
pylint_odoo = true
ruff = true
oca = false                     # mặc định tắt vì nặng hơn

[severity]                       # đổi nhãn hiển thị / cổng CI, KHÔNG đổi tier/điểm
"missing-ondelete" = "warning"
"search-in-loop" = "off"

[ignore]
rules   = ["deprecated-api"]
files   = ["**/migrations/**", "**/tests/**"]
modules = ["legacy_module"]

[category_weights]               # nhân vào điểm trừ trước khi chấm
Security = 1.0
Performance = 1.5
Architecture = 0.5
```

Nguyên tắc:

- `severity` chỉ đổi nhãn + cổng CI; muốn rule biến mất hẳn thì `"off"` hoặc cho
  vào `ignore.rules`.
- `category_weights` điều chỉnh điểm (tier vẫn cố định).
- `ignore.files`/`modules` né legacy/vendor mà không phá score phần còn lại.
- `odoo_source_path` rỗng → resolver dùng repo + stub; có giá trị → resolve sâu.

**YAGNI:** MVP **không** có mô hình `[surfaces.*]` (cli/pr_comment/score/ci_failure
riêng). Thêm lại đúng lúc khi làm PR comment.

---

## CLI & Agent Skills (MVP surfaces)

### CLI (`typer` + `rich`)

```bash
odoo-doctor scan ./addons/sale_custom      # scan 1 module
odoo-doctor scan ./addons                   # scan mọi module trong thư mục
odoo-doctor scan ./addons --diff main       # chỉ file đổi so với base branch
odoo-doctor scan ./addons --json            # output JSON cho tự động hóa/agent
odoo-doctor scan ./addons --fail-on error   # exit code != 0 nếu có error
odoo-doctor rules                           # liệt kê rule đang bật
odoo-doctor explain view-field-not-in-model # giải thích rule + cách fix
odoo-doctor init                            # tạo odoo-doctor.toml mẫu
odoo-doctor install                         # cài agent skills + git hook (tùy chọn, gọn)
```

Terminal report nhóm theo module → category, in điểm tổng + điểm từng category +
finding kèm `help`. `--json` xuất đúng cùng dữ liệu để máy đọc.

### Agent skills (ship 2)

- `odoo-doctor` — dùng sau khi sửa code Odoo hoặc khi user bảo "scan/fix". Chạy
  `odoo-doctor scan --diff --json`, ưu tiên fix P0/P1 trước, rồi scan lại xác nhận.
- `odoo-doctor-explain` — dùng khi user hỏi "vì sao rule này báo" hoặc muốn tinh
  chỉnh config. Chạy `explain`, áp dụng thay đổi config hẹp nhất có thể.

Cả hai tiêu thụ **JSON output** — agent và CI (sau này) dùng chung một nguồn dữ
liệu, không đường đi riêng nào dễ lệch.

### Inline suppression

```python
# odoo-doctor: disable=search-in-loop
for record in records:
    partners = self.env['res.partner'].search([...])
```

```xml
<!-- odoo-doctor: disable=view-field-not-in-model -->
<field name="x_custom_field"/>
```

---

## Testing Strategy

- **Pipeline stages** — hàm thuần, test với input/output dựng tay, không cần file thật.
- **Scoring** — test thuần số: list finding theo tier → kiểm tra điểm category +
  công thức blend.
- **Native rules** — mỗi rule có **cặp fixture**: module "xấu" (phải bắt) +
  module "sạch" (không được báo nhầm). Tuyến phòng thủ false-positive chính.
- **Resolver** — test riêng FOUND / NOT_FOUND / UNKNOWN; khẳng định rule
  **không flag khi UNKNOWN**.
- **Adapters** — recorded fixtures (output tool ghi sẵn) để không phụ thuộc việc
  cài tool; thêm vài integration test gọi tool thật (skip nếu chưa cài).
- **Fixtures đa version** — module mẫu kiểu Odoo 16/17/18 để kiểm version-gating.

Dùng `pytest`. Bộ fixture xấu/sạch cho từng rule là thước đo "low false-positive".

---

## Technology Choices

| Concern        | Choice                            | Rationale                                  |
|----------------|-----------------------------------|--------------------------------------------|
| Language       | Python                            | Tự nhiên cho hệ Odoo, team đã biết         |
| CLI            | `typer`                           | Gọn, type-hint friendly                    |
| Terminal UI    | `rich`                            | Report đẹp, dễ đọc                         |
| Python AST     | stdlib `ast`                      | Không phụ thuộc, đủ cho pattern detection  |
| XML parsing    | `lxml`                            | Nhanh, hỗ trợ XPath cho view analysis      |
| Manifest parse | `ast.literal_eval` (không `eval`) | An toàn                                     |
| Config         | TOML                              | Quen thuộc với Python dev                  |
| Scoring        | Công thức cục bộ có trọng số      | Không phụ thuộc API ngoài, minh bạch       |
| Package        | pip/uv, publish PyPI              | Phân phối Python chuẩn                      |
| Tests          | `pytest`                          | Chuẩn                                       |

> Chốt dùng stdlib `ast` thay vì `libcst`: MVP không làm autofix/codemod, và
> suppression bằng comment làm được với `ast` + `tokenize`. `libcst` để dành khi
> nào thêm autofix.

---

## Repository Layout

```text
odoo-doctor/
  src/odoo_doctor/
    cli/                 # typer app, commands, renderers
    core/
      diagnostics.py     # Diagnostic dataclass
      pipeline.py        # dedup, override, ignore, version-gate
      scoring.py
      config.py
    discovery/           # addon finder, version detect
    context/
      builder.py         # ModuleContext builder
      resolver.py        # Hybrid SymbolResolver
      stubs/             # stub database + build script
    adapters/
      base.py            # BackendAdapter protocol
      pylint_odoo/       # adapter + rule_mapping.toml
      ruff/
      oca/
    rules/
      registry.py        # @rule decorator + registry
      security/ correctness/ performance/ module_hygiene/ architecture/
    reporters/
      terminal.py
      json_report.py
  skills/
    odoo-doctor/SKILL.md
    odoo-doctor-explain/SKILL.md
  tests/
    fixtures/            # module xấu/sạch per rule, đa version
```

---

## Build Roadmap (tinh thần "build chắc")

Mỗi phase đều chạy được end-to-end.

### Phase 1 — Spine
Hợp đồng `Diagnostic` + pipeline (4 stage) + scoring engine + CLI khung
(`scan`, `init`) + terminal/JSON renderer + config loader + discovery + version
detect. *Cuối phase: scan ra điểm từ một nguồn diagnostic giả lập.*

### Phase 2 — Adapters
PylintOdoo + Ruff + rule_mapping; dedup thực chiến. (OCA sau cùng, lùi được.)
*Cuối phase: điểm thật từ tool ngoài.*

### Phase 3 — Graph engine
ModuleContext builder (manifest + Python AST + XML + access CSV) + Hybrid Resolver
+ stub database (~15 module) + script build stub. *Cuối phase: resolver trả
FOUND/NOT_FOUND/UNKNOWN đúng.*

### Phase 4 — Native rules
12 rule + decorator/registry + inline suppression. *Cuối phase: bắt đủ bộ tiêu
chí thành công.*

### Phase 5 — Agent surface
Hai skill + `odoo-doctor install` + `explain` + `--diff`.

### Sau MVP
PR comment renderer + GitHub Action composite (sticky comment, score delta) ·
`[surfaces.*]` config · OWL/JS rules · multi-company rules · trỏ source mặc định.

> Phase 2 (adapters) đặt **trước** Phase 3 (graph engine) có chủ ý: cho giá trị
> "unified score" chạy được sớm nhất từ tool team đã có, trước khi đụng phần rủi
> ro cao là resolver. Có thể đảo 2↔3 nếu muốn dò rủi ro resolver sớm.

---

## Success Criteria

Phiên bản hữu ích đầu tiên scan một repo custom addon và bắt được, với
**false-positive thấp**:

- Model thiếu access rights.
- View trỏ field không tồn tại.
- Button gọi method thiếu.
- Manifest thiếu dependency.
- XML reference hỏng.
- Raw SQL không an toàn.
- Public controller `sudo()` rủi ro.
- Search trong loop.

Đồng thời tổng hợp các finding đó (cùng output của Pylint-Odoo/Ruff/OCA) thành
**một health score 0–100 per module**. Nếu làm được điều này tin cậy, sản phẩm đã
có giá trị; mọi thứ khác xây tiếp từ đó.
