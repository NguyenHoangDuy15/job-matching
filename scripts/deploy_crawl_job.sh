#!/usr/bin/env bash
# S2-T05 (US-07): đóng gói pipeline crawl & upsert lên GCP.
#   Cloud Build  → image trong Artifact Registry (Dockerfile ở gốc repo)
#   Cloud Run Job → python scripts/crawl.py run --run-type daily ...
#   Cloud Scheduler → gọi job lúc 02:00 giờ Việt Nam mỗi ngày
#   Secret Manager → DATABASE_URL (không nằm trong image, không nằm trong lệnh deploy)
#
# Chạy từ gốc repo, bằng Git Bash (Windows) hoặc bash (macOS/Linux), sau `gcloud auth login`:
#   PROJECT_ID=<project> DATABASE_URL='postgresql://...pooler.supabase.com:5432/postgres' \
#     bash scripts/deploy_crawl_job.sh
# Chạy lại nhiều lần được: cái gì đã có thì giữ, chỉ build image mới và cập nhật job + lịch.
# Xem trước các lệnh, không gọi GCP:  DRY_RUN=1 PROJECT_ID=demo bash scripts/deploy_crawl_job.sh
# Hướng dẫn đầy đủ + cách nghiệm thu: docs/deploy/crawl-job.md
set -euo pipefail

cd "$(dirname "$0")/.."

DRY_RUN="${DRY_RUN:-0}"
PROJECT_ID="${PROJECT_ID:-}"
if [[ -z "$PROJECT_ID" && "$DRY_RUN" != "1" ]]; then
  PROJECT_ID="$(gcloud config get-value project 2>/dev/null || true)"
fi
if [[ -z "$PROJECT_ID" || "$PROJECT_ID" == "(unset)" ]]; then
  echo "Thiếu PROJECT_ID (hoặc chạy: gcloud config set project <project>)." >&2
  exit 1
fi

REGION="${REGION:-asia-southeast1}"            # Singapore: gần Việt Nam và gần Supabase nhất
JOB_NAME="${JOB_NAME:-crawl-daily}"
SCHEDULER_NAME="${SCHEDULER_NAME:-crawl-daily-0200}"
SCHEDULE="${SCHEDULE:-0 2 * * *}"              # 02:00 hằng ngày theo TIME_ZONE
TIME_ZONE="${TIME_ZONE:-Asia/Ho_Chi_Minh}"
SECRET_NAME="${SECRET_NAME:-job-matching-database-url}"
AR_REPO="${AR_REPO:-job-matching}"
# Một nguồn "failed" là cả lượt chạy báo đỏ. Ngày 11/11/2026 trang danh sách VietnamWorks trả
# 0 link tin (probe), nên mặc định chỉ chạy itviec; sửa xong config/sources.yaml thì deploy lại với
# CRAWL_SOURCES="itviec vietnamworks".
CRAWL_SOURCES="${CRAWL_SOURCES:-itviec}"
CRAWL_MAX_JOBS="${CRAWL_MAX_JOBS:-150}"        # số tin tối đa mỗi nguồn mỗi đêm (mặc định của crawl.py)
TASK_TIMEOUT="${TASK_TIMEOUT:-3600s}"
MEMORY="${MEMORY:-1Gi}"
RAW_BUCKET="${RAW_BUCKET:-}"                   # tùy chọn: bucket GCS giữ HTML gốc (data/raw)
MODEL_FILE="models/jev_local_v1.joblib"

TAG="${TAG:-$(git rev-parse --short HEAD 2>/dev/null || date +%Y%m%d%H%M)}"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO}/pipeline:${TAG}"
RUN_SA="crawl-job@${PROJECT_ID}.iam.gserviceaccount.com"
SCHED_SA="crawl-scheduler@${PROJECT_ID}.iam.gserviceaccount.com"

step() { printf '\n== %s ==\n' "$*"; }

# In lệnh rồi chạy. DRY_RUN=1 thì chỉ in.
run() {
  printf '+ %s\n' "$*"
  if [[ "$DRY_RUN" != "1" ]]; then "$@"; fi
}

# Tài nguyên đã có chưa? DRY_RUN=1 coi như chưa có để in đủ lệnh tạo.
exists() {
  [[ "$DRY_RUN" != "1" ]] && "$@" >/dev/null 2>&1
}

g() { run gcloud --project "$PROJECT_ID" --quiet "$@"; }
has() { exists gcloud --project "$PROJECT_ID" "$@"; }

# ---- kiểm tra trước khi đụng tới GCP ---------------------------------------------
if [[ ! -f "$MODEL_FILE" && "${ALLOW_NO_MODEL:-0}" != "1" ]]; then
  cat >&2 <<EOF
Không thấy $MODEL_FILE trên máy này.
Thiếu model thì job gắn kỹ năng bằng luật (phiên bản "...+no-model") và mỗi đêm sẽ gắn lại,
ghi đè các tin đã gắn bằng model ở máy. Chép file model vào models/ (hoặc chạy
scripts/train_tier2.py) rồi deploy lại. Vẫn muốn deploy không model: thêm ALLOW_NO_MODEL=1.
EOF
  exit 1
fi

if [[ -n "${DATABASE_URL:-}" && "$DATABASE_URL" =~ @db\.[a-z0-9]+\.supabase\.co ]]; then
  cat >&2 <<EOF
DATABASE_URL đang là "Direct connection" của Supabase (db.<ref>.supabase.co): địa chỉ này chỉ có
IPv6, Cloud Run không kết nối được. Lấy chuỗi "Session pooler" trong Supabase Dashboard → Connect
(host dạng aws-...pooler.supabase.com, cổng 5432, user postgres.<ref>).
EOF
  exit 1
fi

# ---- 1. API ---------------------------------------------------------------------
step "1/7 Bật API"
g services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com \
  secretmanager.googleapis.com cloudscheduler.googleapis.com

# ---- 2. Kho image ------------------------------------------------------------------
step "2/7 Artifact Registry"
if ! has artifacts repositories describe "$AR_REPO" --location "$REGION"; then
  g artifacts repositories create "$AR_REPO" --repository-format docker --location "$REGION" \
    --description "Image pipeline job-matching"
fi

# ---- 3. Service account: một cho job chạy, một cho Scheduler gọi job -------------------
step "3/7 Service account"
if ! has iam service-accounts describe "$RUN_SA"; then
  g iam service-accounts create crawl-job --display-name "Cloud Run Job crawl (S2-T05)"
fi
if ! has iam service-accounts describe "$SCHED_SA"; then
  g iam service-accounts create crawl-scheduler --display-name "Cloud Scheduler goi job crawl"
fi

# ---- 4. Secret DATABASE_URL -----------------------------------------------------------
# Giá trị đi qua stdin: không hiện trong lệnh in ra, không vào lịch sử shell của gcloud.
step "4/7 Secret Manager"
if ! has secrets describe "$SECRET_NAME"; then
  if [[ -z "${DATABASE_URL:-}" ]]; then
    echo "Secret $SECRET_NAME chưa có: đặt biến DATABASE_URL (chuỗi Session pooler) rồi chạy lại." >&2
    exit 1
  fi
  printf '+ gcloud secrets create %s --data-file=-   (giá trị lấy từ biến DATABASE_URL)\n' "$SECRET_NAME"
  if [[ "$DRY_RUN" != "1" ]]; then
    printf '%s' "$DATABASE_URL" | gcloud --project "$PROJECT_ID" --quiet secrets create \
      "$SECRET_NAME" --replication-policy automatic --data-file=-
  fi
elif [[ "${UPDATE_SECRET:-0}" == "1" ]]; then
  : "${DATABASE_URL:?UPDATE_SECRET=1 cần biến DATABASE_URL}"
  printf '+ gcloud secrets versions add %s --data-file=-   (giá trị lấy từ biến DATABASE_URL)\n' "$SECRET_NAME"
  if [[ "$DRY_RUN" != "1" ]]; then
    printf '%s' "$DATABASE_URL" | gcloud --project "$PROJECT_ID" --quiet secrets versions add \
      "$SECRET_NAME" --data-file=-
  fi
else
  echo "Secret $SECRET_NAME đã có, giữ nguyên (đổi giá trị: thêm UPDATE_SECRET=1)."
fi
# Chỉ service account của job đọc được đúng secret này.
g secrets add-iam-policy-binding "$SECRET_NAME" \
  --member "serviceAccount:${RUN_SA}" --role roles/secretmanager.secretAccessor

# ---- 5. Build image bằng Cloud Build (máy không cần Docker) ---------------------------
step "5/7 Build image $IMAGE"
g builds submit --tag "$IMAGE" .

# ---- 6. Cloud Run Job -----------------------------------------------------------------
step "6/7 Cloud Run Job $JOB_NAME"
args="scripts/crawl.py,run"
# Viết dạng --co=gia_tri: gcloud không cho một phần tử ("--source") lặp lại trong --args.
for source in $CRAWL_SOURCES; do args+=",--source=${source}"; done
args+=",--run-type=daily,--max-jobs=${CRAWL_MAX_JOBS}"

deploy=(run jobs deploy "$JOB_NAME" --image "$IMAGE" --region "$REGION"
  --service-account "$RUN_SA"
  --set-secrets "DATABASE_URL=${SECRET_NAME}:latest"
  --command python "--args=${args}"
  --tasks 1 --max-retries 0 --task-timeout "$TASK_TIMEOUT" --memory "$MEMORY" --cpu 1)
if [[ -n "$RAW_BUCKET" ]]; then
  # HTML gốc (data/raw) ghi thẳng vào bucket thay vì mất theo container.
  g storage buckets add-iam-policy-binding "gs://${RAW_BUCKET}" \
    --member "serviceAccount:${RUN_SA}" --role roles/storage.objectUser
  deploy+=(--add-volume "name=raw,type=cloud-storage,bucket=${RAW_BUCKET}"
    --add-volume-mount "volume=raw,mount-path=/app/data/raw")
fi
g "${deploy[@]}"

# Scheduler chỉ được quyền chạy đúng job này.
g run jobs add-iam-policy-binding "$JOB_NAME" --region "$REGION" \
  --member "serviceAccount:${SCHED_SA}" --role roles/run.invoker

# ---- 7. Lịch 02:00 hằng ngày ----------------------------------------------------------
step "7/7 Cloud Scheduler $SCHEDULER_NAME ($SCHEDULE, $TIME_ZONE)"
if has scheduler jobs describe "$SCHEDULER_NAME" --location "$REGION"; then verb=update; else verb=create; fi
g scheduler jobs "$verb" http "$SCHEDULER_NAME" --location "$REGION" \
  --schedule "$SCHEDULE" --time-zone "$TIME_ZONE" \
  --uri "https://run.googleapis.com/v2/projects/${PROJECT_ID}/locations/${REGION}/jobs/${JOB_NAME}:run" \
  --http-method POST --oauth-service-account-email "$SCHED_SA"

cat <<EOF

Xong. Nghiệm thu S2-T05:
  gcloud run jobs execute $JOB_NAME --region $REGION --project $PROJECT_ID --wait   # chạy thử ngay
  gcloud scheduler jobs describe $SCHEDULER_NAME --location $REGION --project $PROJECT_ID \\
    --format 'value(state,schedule,timeZone)'                                        # ENABLED  $SCHEDULE  $TIME_ZONE
EOF
