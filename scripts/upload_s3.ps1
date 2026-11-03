# ECMPS bronze, ECMPS silver, K-TMS silver -> S3 (sync only adds/updates, never deletes).
# Run from a PowerShell where `aws sts get-caller-identity` works.  Add -DryRun to preview.
param(
    [string]$Bucket = "smokestack-tms-raw-952900391026",
    [string]$Account = "952900391026",
    [string]$Raw = "C:\smokestack-guard\data\raw",
    [string]$Silver = "C:\smokestack-guard-silver\data\silver",
    [switch]$DryRun
)
$ErrorActionPreference = "Stop"

$who = aws sts get-caller-identity --query Account --output text
if ($who -ne $Account) { throw "Wrong AWS account '$who', expected $Account" }
aws s3api head-bucket --bucket $Bucket | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Cannot access bucket $Bucket" }

$extra = @(); if ($DryRun) { $extra += "--dryrun" }

# bronze: only the ECMPS CSVs (no CAMPD, K-TMS test files, json, no-data markers, zip)
aws s3 sync $Raw "s3://$Bucket/bronze/ecmps/" --exclude "*" --include "epa_emissions_*.csv" @extra
# silver
aws s3 sync "$Silver\ecmps" "s3://$Bucket/silver/ecmps/" --exclude "*" --include "*.parquet" @extra
aws s3 sync "$Silver\ktms" "s3://$Bucket/silver/ktms/" --exclude "*" --include "*.parquet" @extra
