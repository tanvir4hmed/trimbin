# Whole-application cost estimate

Price check: 23 October 2026. USD, us-east-1, on-demand Linux, 730 running hours/month, before tax, currency conversion, discounts and unrelated account resources. This is a planning estimate, not an invoice or a measured cost per film. No resource or plan was resized by this calculation.

## Basic monthly usage assumptions

Assume 50 uploads averaging 200 MB (about 10 GB of new originals), 20 GB average total S3 backup/release/state storage including retained versions, 10 GB average private ECR image storage, 10,000 app requests, and under 20 GB viewer delivery. Keep CI on standard public-repository runners with cache/artifact storage inside included allowances.

For model usage, assume 300 vision requests, 100 reasoning requests and one million total embedding input tokens. A vision request averages 20,000 billed input tokens and 1,000 output tokens; a reasoning request averages 10,000 input and 2,000 billed output tokens, including charged reasoning where applicable. These are explicit hypothetical averages, not measurements from 50 videos. A clip can require many eight-image batches and additional merge/retry calls. File bytes or film minutes cannot establish model token cost.

## Estimate summary

| Estimate item | USD | Basis |
| --- | ---: | --- |
| AWS hosting/storage/overhead subtotal | $165.17/month | Always-on CPU host, current disks and the basic stored/served workload |
| All active model APIs subtotal | $2.56/month | Explicit request and token assumptions below |
| **Gross operating estimate** | **$167.73/month** | Before promotional credits and tax |
| Annual planning equivalent | $2,012.76/year | 12 identical months; prices/workload may change |
| Credits deducted in base estimate | $0.00 | Remaining eligible balance/expiry not certified |
| Tax / exchange / development labour | Not included | Account/country/team-specific |

This is an operating estimate for the declared PoC, not a vendor quote, cost ceiling or all-inclusive customer product price. No new hardware purchase or one-time development budget is priced here.

## Infrastructure bill of materials and calculation

| Component | Monthly quantity | Unit rate (USD) | Calculation | Monthly USD |
| --- | ---: | ---: | --- | ---: |
| EC2 m7i-flex.xlarge (4 vCPU / 16 GiB) | 730 hours | $0.19152/hour | 730 x 0.19152 | $139.81 |
| Root gp3 EBS | 40 provisioned GiB-month | $0.08/GiB-month | 40 x 0.08 | $3.20 |
| Persistent data gp3 EBS (baseline IOPS/throughput) | 200 provisioned GiB-month | $0.08/GiB-month | 200 x 0.08 | $16.00 |
| One public IPv4 | 730 address-hours | $0.005/hour | 730 x 0.005 | $3.65 |
| Advanced SSM runtime parameter | 1 parameter-month | $0.05/month | 1 x 0.05 | $0.05 |
| CloudFront + associated WAF plan | 1 FREE plan-month | $0/month | Existing active plan | $0.00 |
| S3 Standard backup/release/state | 20 GB-month | $0.023/GB-month | 20 x 0.023, before storage credits | $0.46 |
| Private ECR image storage | 10 GB-month | $0.10/GB-month | 10 x 0.10 | $1.00 |
| Small request/decryption/other overhead | 1 allowance | $1 allowance | Planning allowance; not a fixed tariff | $1.00 |
| **Infrastructure subtotal** | | | Sum of above, rounded | **$165.17** |
| NVIDIA / Qwen APIs | Detailed below | Token-based | Sum of model rows | $2.56 |
| **Illustrative operating total** | | | 165.17 + 2.56 | **$167.73/month** |

The compute and gp3 rates were read from the authenticated AWS Price List API, filtered to the exact instance/storage and N. Virginia. Reproduce with the [AWS Price List API](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/price-changes.html); the local raw response is private operator evidence. Public reference pages: [EC2 on-demand](https://aws.amazon.com/ec2/pricing/on-demand/), [EBS](https://aws.amazon.com/ebs/pricing/), [IPv4](https://aws.amazon.com/vpc/pricing/), [S3](https://aws.amazon.com/s3/pricing/), [ECR](https://aws.amazon.com/ecr/pricing/) and [SSM](https://aws.amazon.com/systems-manager/pricing/).

Read-only account inspection confirmed the reused CloudFront distribution has an active FREE flat-rate subscription. The published allowance is 1 million requests and 100 GB delivery/month; associated WAF is bundled. Do not confuse that with the pay-as-you-go free tier or assume unlimited movie delivery. Upgrading to Pro is currently $15/month, but this estimate does not request or apply an upgrade. Separate or unassociated resources may still bill. See [CloudFront plan pricing](https://aws.amazon.com/cloudfront/pricing/). Existing domain registration, unrelated hosted zones, taxes, optional support, inter-region transfer and any future plan changes are excluded.

## Model/API costs in the same workload

| API/model | Public list rate per million tokens | Basic assumed usage | Estimate |
| --- | --- | --- | ---: |
| Nemotron 3.5 Super VL | $0.30 input / $0.90 output | 300 x (20k input + 1k output) = 6M input + 0.3M output | $2.07 |
| Nemotron 3 Super 120B-A12B | $0.30 input / $0.90 output | 100 x (10k input + 2k output) = 1M input + 0.2M output | $0.48 |
| Qwen3 Embedding 8B | $0.01 input | 1M input, including indexing and queries | $0.01 |
| **Total model API** | No cache discounts assumed | All batches/retries must count in request totals | **$2.56** |

Rates were retrieved from Nebius's [public model/pricing catalog](https://tokenfactory.nebius.com/api/public/models_info). The catalog advertises BF16 for the vision alias and FP4 for reasoning; that is not a per-response serving attestation. Tokenized image inputs, repeated context, merges, retries and reasoning output can substantially change cost. Obtain actual provider usage/billing before claiming a per-minute or per-movie figure.

## Software and APIs with no separate charge in this scenario

| Tool / service | What pays for it |
| --- | --- |
| Self-hosted ClickHouse | No ClickHouse Cloud invoice; CPU/RAM/disk/backups are included in the AWS lines |
| Self-hosted PostgreSQL and durable queue | No managed database/queue service; shared host and storage pay for execution |
| Whisper large-v3 / faster-whisper | No speech API charge; CPU time and model cache occupy this host/disk |
| FFmpeg / ffprobe | No per-render API charge; compute, scratch space and output storage still cost |
| FastAPI, Next.js, Nginx, Docker Engine/Compose | No separate hosted SaaS API assumed; licenses still apply |
| Terraform | CLI and self-managed S3 state, not paid HCP Terraform; state storage/requests included above |
| GitHub source + standard Actions runners | Public repository and standard runners; $0 runner-minutes under current policy; storage allowances still matter |
| SSM administration / IAM / GitHub OIDC | No public SSH server or paid secrets SaaS; parameter and small metered overhead counted above |
| Optional Google OAuth / Google Fonts | No paid Google Cloud application service enabled; normal browser traffic and third-party boundaries remain |
| Tavily, LangSmith/LangChain, Toloka, Tendem | **Not integrated into the active core path: $0 assumed usage**, not a claim that their APIs are free |
| GCP / Vertex / managed ClickHouse | Retired from the canonical app; no such service is assumed in this application's estimate |

GitHub confirms [standard runners are free for public repositories](https://docs.github.com/en/billing/concepts/product-billing/github-actions). Larger runners, additional storage, Docker Desktop commercial licensing on a future workstation, optional integrations and other account products require their own budget. AWS Docker Engine deployment does not use Docker Desktop.

## Credit treatment

| Scenario | Infrastructure | Model API gross | Assumed eligible model credit applied | Estimated cash cost before tax |
| --- | ---: | ---: | ---: | ---: |
| Base estimate; no balance assumed | $165.17 | $2.56 | $0.00 | **$167.73** |
| Same month, if at least $2.56 eligible unexpired Token Factory credit remains | $165.17 | $2.56 | -$2.56 | **$165.17** |

Credits do not reduce the economic usage cost and must not be deducted from AWS hosting. Never assume the original promotional grant is still the remaining balance.

## Credits and heavier usage

The reported $25 Token Factory promotional grant can offset eligible model usage while valid; the remaining balance and expiry were not certified in this estimate. It does not offset the $139.81 EC2 line or other AWS costs. Partner credits apply only to their respective offers. Open-source weights/software do not make managed inference, electricity or hardware free.

Holding the small storage/hosting assumptions constant, multiplying only the model workload by ten makes model cost $25.60 and the illustrative total $190.77; by one hundred, $256.00 and $421.17. These are arithmetic scenarios, not promises the same host or disk can sustain that workload. Real retries and longer/dense-window footage must be counted.

Every additional 100 provisioned GiB of gp3 adds about $8/month at the quoted baseline, and every extra 100 GB average S3 Standard storage adds about $2.30/month in the first tier, before requests/transfer. Current 200 GiB data storage cannot hold terabytes of originals plus databases, proxies, scratch and exports. Daily database snapshots, object versions and retained exports increase occupied storage over time; there is no claimed automatic cost ceiling.

A future studio installation substitutes hardware purchase/amortization, electricity, maintenance, storage and backup for AWS rental. External Token Factory API costs remain unless model serving is separately implemented and sized. No GPU purchase quote or on-premises savings benchmark is implied. Do not reduce analysis detail or change model quality merely to fit this illustrative budget.
