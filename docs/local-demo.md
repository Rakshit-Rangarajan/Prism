# PRISM local demonstration

## One-click automated rehearsal

Double-click `Run PRISM Demo.cmd` at the repository root. On the prepared PC,
the Outputs folder also contains a launcher with the same name that saves each
run under `Outputs/Demo Runs`. It starts/verifies the existing Podman MySQL,
GPU model and PRISM services, then runs 20 datasets in a fresh isolated rehearsal
company. It opens a self-contained HTML report containing before/after metrics,
retrieval provenance and downloadable source/processed packages.

This automated rehearsal **simulates approvals on synthetic data**. It does not
claim human review, update model weights, promote an adapter or upload to Qlik.
Interactive PRISM still requires human approval. Each launch retains previous
results and leaves the active company's memory untouched. The script does not
install software or download models; use the prepared local environment below.

For a shorter rehearsal or unattended verification:

```powershell
.\scripts\demo-one-click.ps1 -Datasets 2
.\scripts\demo-one-click.ps1 -NoBrowser -OutputRoot C:\PRISM-Demo-Runs
```

The launcher validates source hashes, preserved row counts and quality improvement
before announcing success. Failures preserve logs in the run folder. The latest
successful run is recorded in `.local/latest-demo.json`.

## SQL source database samples

Every one-click run includes importable source samples with the same 81 vendors,
80 materials and 80 invoices. Generate them independently in a new directory:

```powershell
.venv\Scripts\python -m scripts.export_erp_samples --output C:\PRISM-SQL-Samples
```

| File | Setup |
| --- | --- |
| `prism-erp-source.sqlite` | Open directly or upload to PRISM |
| `prism-erp-sqlite.sql` | Import into a new empty SQLite database |
| `prism-erp-mysql.sql` | phpMyAdmin Import or MySQL client; creates `prism_erp_sample` |
| `prism-erp-sqlserver.sql` | Execute in SSMS; creates `prism_erp_sample` using T-SQL/GO batches |

No sample script drops existing data. Amounts and dates intentionally remain text
to preserve invalid source values. SQLite and MySQL imports were executed locally.
The SQL Server script is provided for SSMS but has not been executed against a local
SQL Server instance. PRISM's live source adapters currently support MySQL and SQLite;
SSMS import support does not imply a direct SQL Server connector.

PRISM continues the existing React/Vite and FastAPI application. The Render Docker service still automatically deploys commits pushed to `main`. The local GPU model is intentionally not exposed to Render or uploaded to GitHub. No paid API is required.

## Prepared Windows machine

Verified 27 November 2026: Windows 11 Pro x64 (10.0.26300), 32 GB RAM, NVIDIA GeForce RTX 3060 12 GB, driver 610.88, Python 3.12.10, Node 24.16, Podman 6.1.4/WSL. A portable llama.cpp CUDA 12.4 runtime is used because it requires no system-wide installation. PyTorch 2.11.0+cu128 detects the GPU.

From the repository in PowerShell:

```powershell
.\scripts\start-local.ps1
```

Open `http://127.0.0.1:8091`. Username is `prism`; the generated local password is in `.local/settings.json`. This credential is separate from the hosted demo password. Startup verifies the quantized model hash, all 20 source dataset hashes, model availability, the company binding, and the actual read-only MySQL connection. It starts existing Podman/MySQL and launches the model and app in hidden background processes. It does not overwrite source databases or approved memory.

Use the PRISM sign-in form rather than a browser-native password dialog. Browser sessions use a signed, HttpOnly, SameSite=Strict cookie with an eight-hour lifetime; hosted cookies require HTTPS. Signing out clears the browser cookie, and changing the configured demo password invalidates previous sessions. Cross-origin cookie-authenticated mutations are rejected. Existing HTTP Basic API clients continue to work. Browser sign-in and dashboard rendering were verified in the Codex in-app browser; the local password was not changed.

```powershell
.venv\Scripts\python -m scripts.check_local_demo
.\scripts\stop-local.ps1
```

Stopping preserves MySQL and all data. Processes are stopped only after matching saved PIDs and expected command lines. If another process owns the selected ports, resolve that conflict before launching. Do not run training and inference together on this GPU: stop the local processes first, train, then launch the demo again.

## Five-minute presentation

1. Open **Local AI & Learning**. Confirm company `prism-demo`, `qwen3-4b`, **Local inference online**, and base weights.
2. Click **Connect local MySQL**, or load dataset 1. MySQL contains the same batch-1 synthetic vendors, materials and invoices. Its `prism_reader` account has SELECT privileges only. The snapshot is a SQLite staging representation, not a faithful MySQL schema clone.
3. Click **Ask local SLM**. The model interprets quality findings, classifies ERP domains, proposes advisory field mappings, selects finite transformation candidates, and explains unresolved migration risks. No model-authored SQL runs.
4. Review the editable structured plan. Correct or remove a rule if needed. Enter the reviewer/rationale, check the approval box, then click **Approve & store correction**.
5. Generate the processed package. It contains a separate SQLite database, UTF-8 CSV files, a manifest, before/after metrics, approved rule audit and source/target SHA-256 hashes. Source rows are never deleted or merged.
6. Load dataset 2 and click **Retrieve approved resolutions**. PRISM retrieves only approved corrections from the current company. It still requires a fresh approval for the new source digest. This is retrieval-based learning, not a weight update.
7. Alternatively ask the local model on dataset 2: approved resolutions are included as evidence and explicit candidates. Compare its provenance with the first request.

The generic database workbench remains under **Migration Studio**, including SQLite uploads, MySQL snapshots, opt-in normalization, approval gates and Qlik-compatible exports. The earlier ERP learning scenario demo is also retained.

## Data and model locations

| Location | Purpose |
| --- | --- |
| `.local/settings.json` | Private launcher paths, generated local login, expected model hash, optional promoted GGUF adapter |
| `.local/artifacts.json` | Canonical model identity and 20 dataset hashes |
| `.local/datasets/erp-01.sqlite` … `erp-20.sqlite` | Reproducible messy ERP source datasets |
| `.local/companies/<company>/config.json` | Operator-controlled base model, inference URL, adapter label, business rules and migration knowledge |
| `.local/companies/<company>/memory.sqlite3` | Source-bound plans, approved corrections, reviewer notes and mapping/execution history |
| `<company>/training/<run>/` | Approved training examples, source-separated held-out data and evaluation report |
| `<company>/adapters/<run>/` | Actual PEFT adapter and evaluation metadata; remains a candidate until promoted |
| `.local/base-model/` | Local Hugging Face base weights/tokenizer for offline training |
| `../models/` and `../runtime/` on this prepared machine | Quantized inference model and portable CUDA llama.cpp runtime; absolute paths are recorded in private settings |

`prepare_local_demo` creates missing canonical datasets and checks existing ones for drift, without replacing data or memory. It refuses modified datasets. Source datasets, generated targets and model artifacts remain local and are excluded from Git and Docker build context. Approved plans expire after 24 hours; approved corrections and history persist.

Company identity is bound by `PRISM_COMPANY_ID` and `PRISM_COMPANY_ROOT` on the server. A browser cannot select a tenant. Separate company directories isolate configurations, memory, examples, adapters and histories. Run separate server instances/ports for separate companies. Existing demo Basic Auth is not multi-tenant production SSO. Render's filesystem remains ephemeral, so local approved memory is the demonstration's durable record.

## Reproduce on another machine

Create `.venv`, install `requirements.txt`, then `npm ci --prefix frontend` and `npm run build --prefix frontend`. Download the selected GGUF and a compatible official CUDA llama.cpp release, create private `.local/settings.json` matching the launcher fields, and run `python -m scripts.prepare_local_demo`. Start a loopback-only MySQL 8.4 container named `prism-mysql`, with port `127.0.0.1:3307:3306`, database `prism_erp`, user `prism_reader`, and private credentials in `.local/mysql.env`.

Run `python -m scripts.seed_mysql_demo` with `PRISM_MYSQL_ROOT_PASSWORD` and `PRISM_MYSQL_PORT=3307` in the process environment. The seeder refuses nonempty databases and is restricted to the synthetic `prism_erp` schema. It seeds 81 vendors, 80 materials and 80 invoices, then reduces the reader to SELECT-only access. Local setup is opt-in; the application never automatically downloads models or installs system software.

## Rules and validation

Executable operations are `trim`, nullable `blank_to_null`, code `uppercase`, email-domain normalization, explicit US decimal parsing and bounded value crosswalks. The initial synthetic UOM crosswalk maps pieces → EA, kilograms → KG and meters → M. Unknown codes are preserved. Protected keys, indexed or constrained fields, trigger-bearing tables, generated columns and foreign-key tables follow the existing conservative protection policy.

Execution stages are deterministic: trim, blank-to-NULL, value crosswalks, uppercase, decimal parsing, then email-domain normalization. Crosswalks run before uppercasing so source spellings remain matchable regardless of model/retrieval rule ordering. The export audit records the actual execution order.

ERP validation reports missing values, spaces, allowed country/currency/UOM vocabularies, invalid/negative amounts, invalid ISO dates, malformed emails, unknown cost centres, orphan invoice references and duplicate business-record candidates. These are illustrative ERP vocabularies, not comprehensive SAP validation. Findings can overlap; the quality score is `100 × max(0, 1 − finding_count/cell_count)`, not certification or acceptance. CSV NULLs appear empty and binary values are hexadecimal; SQLite retains type/null fidelity. Qlik-compatible exports remain available. A local Qlik Desktop demonstration is supported as described below; Qlik Cloud, Talend and SAP credentials are not configured.

## Local Qlik Desktop demonstration

Qlik Sense Desktop November 2026 Patch 1 was installed locally with a valid QlikTech publisher signature and matching release checksum. Qlik's official courtesy developer unlock instructions currently specify expiry on February 4, 2027. This is time-limited local access, not a Cloud subscription. See [Qlik's support policy](https://community.qlik.com/t5/Official-Support-Articles/What-to-do-when-the-Qlik-Sense-Desktop-unlock-file-has-expired/ta-p/2545033) and [official downloads](https://github.com/qlik-download/qlik-sense-desktop/releases). Installers and unlock files are not redistributed in this repository.

Start Qlik Sense Desktop and click **Launch** on its welcome screen to activate the local session. On this machine Documents is redirected to OneDrive. The launch configuration's LogPath was corrected to the actual Qlik log directory following [Qlik's troubleshooting instructions](https://community.qlik.com/t5/Official-Support-Articles/Qlik-Sense-Desktop-showing-white-screen-or-blank-screen-on-start/ta-p/1714577). The official unlock is in the installation's `trial` folder. No authentication or license checks were disabled.

The one-click demo always generates a `Qlik Demo` folder for its own completed rehearsal. If Qlik is already listening on loopback port 4848 and its session has been launched, it also creates and saves a new Qlik app using the documented Engine JSON API. An optional Qlik failure does not invalidate PRISM's core demonstration: inspect `qlik-load.log` and `Qlik Demo/qlik-app.json` for the precise state. Each launch preserves earlier apps and runs. The app contains the first processed ERP database and quality comparisons for all datasets in that run; these are synthetic records with simulated steward approvals.

To prepare and load an existing run manually:

```powershell
.venv\Scripts\python -m pip install -r requirements-qlik.txt
.venv\Scripts\python -m scripts.prepare_qlik_demo --run PATH_TO_COMPLETED_RUN --output NEW_QLIK_FOLDER
.venv\Scripts\python -m scripts.load_qlik_demo --folder NEW_QLIK_FOLDER
```

Preparation checks the processed database hash and first-dataset metrics against its audit before exporting. The loader only connects to localhost, refuses to overwrite an existing package's app, verifies loaded row counts and chart dataset counts, then saves the app URL. If interrupted after app creation, recovery details remain in `qlik-app.json`; inspect that app rather than deleting the recovery record and blindly retrying. The CSV and QVS files can also be imported manually using the supplied README.

The initial 20-dataset app was verified through the actual Qlik engine and visually in the local browser: 81 vendors, 80 materials, 80 invoices, 40 metric rows; the first dataset shows 786 findings before and 125 after. Both comparison charts rendered. Company memory and models remain managed by PRISM and are not copied into Qlik.

### Direct MySQL source connection

The installed Qlik ODBC connector also connects directly to the real local MySQL 8.4 container at `127.0.0.1:3307/prism_erp`. `scripts.connect_qlik_mysql` uses the existing `prism_reader` account from private `.local/mysql.env`. It is limited to this synthetic source and fixed SELECT queries over the three known ERP tables, bounded to 5,000 rows per table. MySQL 8.4 connectivity was tested on this machine; Qlik's published MySQL support matrix lists older versions, so this demonstration does not claim general 8.4 vendor certification.

```powershell
.venv\Scripts\python -m scripts.connect_qlik_mysql --folder EXISTING_QLIK_FOLDER
```

The command validates the connector, creates or updates its named connection, adds a marked script section, reloads, compares actual Qlik source counts with MySQL, and saves. Repeating it updates that section rather than duplicating source tables. Raw fields use a separate `source_` prefix; only the intended vendor link is shared among raw tables. Processed tables retain their separate approved file connection. The first script backup is preserved in `PRISM-before-mysql.qvs`; credentials are never written into that script or the status JSON. Qlik Desktop itself retains connection credentials inside its local app, so do not redistribute the credential-bearing QVF. The one-click rehearsal attempts this attachment after its processed-data Qlik load.

Verified source counts are 81 vendors, 80 materials and 80 invoices. This is a direct database connection refreshed on Qlik reload, not streaming, CDC or a Talend migration. Qlik Cloud, Qlik Answers, Talend and SAP still require suitable activated services and credentials. REST and SAP connector availability alone does not establish an active service connection.

## Offline QLoRA

Install CUDA PyTorch compatible with the driver, then `requirements-training.txt`. Download `Qwen/Qwen3-4B-Instruct-2507` into a local directory before disconnecting. The training command sets Hugging Face and Transformers offline mode and uses `local_files_only=True`.

```powershell
.\scripts\stop-local.ps1
.venv\Scripts\python -m scripts.train_company_adapter --base-model .local/base-model --company-root .local/validation-final/companies --company synthetic-validation --steps 20 --max-length 3072
.\scripts\start-local.ps1
```

Training uses only approved plans, separates examples by source database digest, masks prompt tokens from labels, and saves a new per-company LoRA adapter plus base/adapted held-out loss. No adapter is automatically promoted. The active demonstration continues using the validated base model plus approved retrieval. A GGUF-converted adapter can be selected using the launcher's `adapterPath` and `adapterSha256` after separate structured-output and migration regression evaluation; update company configuration only to describe what is actually loaded. PEFT artifacts cannot be passed directly to llama.cpp.

The completed synthetic validation run used 16 training databases and four held-out databases, 20 QLoRA steps, rank 8 on query/value projections, NF4 quantization and microbatch size 1. It trained 2,949,120 parameters. Token-loss improvement is evidence that training ran, not proof of general migration-risk improvement or SAP correctness. Near-duplicate synthetic schemas also limit the strength of this evaluation.

## Verification commands

```powershell
.venv\Scripts\python -m unittest discover -s tests -p 'test_*.py' -q
.venv\Scripts\python -m unittest discover -s demo -p 'test_*.py' -q
npm run build --prefix frontend
.venv\Scripts\python -m scripts.demo_local_pipeline --mysql --output .local/new-validation --model-batches 2
```

The end-to-end command is explicitly a synthetic steward demonstration: it approves synthetic model recommendations, verifies export is blocked before approval, processes 20 datasets, checks source hashes/row counts/integrity, and records real model timing separately from retrieval. Use a fresh output directory. The initial desktop-browser verification was blocked by URL detection. A later in-app browser check verified the new PRISM sign-in form and authenticated dashboard. Full migration-flow visual review remains separate from the completed API/build checks.
