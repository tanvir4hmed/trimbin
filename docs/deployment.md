# Deployment

Everything is Terraform. Nothing in this project is created by clicking in a
console, and nothing exists that Terraform cannot also destroy.

There is exactly one manual apply, and it is itself Terraform.

---

## What cannot be automated

Five things, each for a structural reason rather than convenience.

| Step | Why it resists automation |
|---|---|
| Create the Google Cloud project, link billing | Terraform must authenticate to something that already exists |
| Apply `infra/bootstrap/` once | Terraform cannot create the bucket that stores its own state |
| Generate a ClickHouse Cloud API key | Issued through the ClickHouse console; the provider needs it to create anything |
| Add secrets to the GitHub repository | Repository configuration, outside cloud infrastructure |
| Configure the OAuth consent screen | Not fully covered by the Google provider |

Everything else — buckets, Cloud Run services, Agent Engine, Pub/Sub, IAM, CDN,
Firestore, the ClickHouse service itself — is declared in `infra/`.

---

## First-time setup

### 1. Project and billing

```bash
gcloud auth login
gcloud projects create YOUR_PROJECT_ID
gcloud billing projects link YOUR_PROJECT_ID --billing-account=BILLING_ACCOUNT_ID
```

### 2. Bootstrap

Creates the state bucket, enables APIs, and establishes keyless CI authentication.

```bash
cd infra/bootstrap
cp terraform.tfvars.example terraform.tfvars   # fill in your values
terraform init
terraform apply
```

The output prints exactly what to paste into GitHub secrets.

**Fill in `billing_account_id`.** Left empty, the budget guard's `count` is zero
and no guard is created — nothing watches spend, silently. It was empty here for
weeks beside a comment claiming the alerting lived somewhere else; it did not.

```
billing_account_id = "01BF97-E4E92D-6319C7"   # gcloud billing accounts list
monthly_budget_usd = 100                      # alerts at 50%, 80%, 100%
```

`terraform.tfvars` is gitignored, so this has to be re-entered on a fresh
machine and there is nothing in the repository to remind you. That is what this
paragraph is for.

The guard also needs `billingbudgets.googleapis.com`, which bootstrap enables —
but the API takes a minute to propagate, so a first apply can fail on it and
succeed on the second. That is the API waking, not a misconfiguration.

### 3. ClickHouse credentials

In the ClickHouse Cloud console: **Organization → API Keys → New key**. Grant it
permission to create services. Keep the organization id, key id and secret.

### 4. GitHub secrets

**Settings → Secrets and variables → Actions**

| Secret | Source |
|---|---|
| `GCP_PROJECT_ID` | Your project id |
| `GCP_REGION` | Your region |
| `GCP_WORKLOAD_IDENTITY_PROVIDER` | Bootstrap output |
| `GCP_SERVICE_ACCOUNT` | Bootstrap output |
| `TF_STATE_BUCKET` | Bootstrap output |
| `CLICKHOUSE_ORG_ID` | ClickHouse console |
| `CLICKHOUSE_TOKEN_KEY` | ClickHouse console |
| `CLICKHOUSE_TOKEN_SECRET` | ClickHouse console |

None of these is a private key. Workload Identity Federation means CI proves
which repository and which ref is running, and Google issues a short-lived token
in return — so there is no long-lived credential to leak, rotate, or find in a
git history two years from now.

### 5. Push

```bash
git push origin main
```

Plan, apply, migrate, build, deploy, smoke test. There is no other route to
production.

---

## Tearing down

The **Destroy** workflow, triggered by hand, requires typing `destroy-demo` to
confirm. It removes the demo environment and leaves the bootstrap state bucket
alone.

It is deliberately not on a schedule and not on a push. A destroy that can fire
on its own is a footgun with a hair trigger.

---

## Local development

```bash
cd agents
uv sync --all-extras --dev
uv run pytest
```

Agents run against real Vertex AI; there is no local model. Point at a scratch
project rather than the demo environment, and remember that video tokens are
billed whether the call was a mistake or not.
