#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# MCP Instagram Analytics — AWS Deploy (always-free tier only, S3 不使用)
#
# CloudFormation でリソースを一括管理。削除は 1 コマンド。
#
#   ./deploy.sh                  # 初回デプロイ (スタック作成 + コードアップロード)
#   ./deploy.sh --update         # コード更新のみ
#   ./deploy.sh --rotate-cookie  # Session Cookie だけ差し替え (再デプロイ不要)
#   ./deploy.sh --status         # 無料枠の使用状況を表示
#   ./deploy.sh --destroy        # 全リソース一括削除
#
# 事前準備:
#   aws configure                # AWS CLI 設定
#   export SESSION_COOKIE=xxx    # ブラウザ DevTools > Cookies > sessionid
#   export API_KEY=xxx           # MCP アクセス用 Bearer トークン (任意の文字列)
# =============================================================================

STACK_NAME="mcp-insta-analytics"
FUNCTION_NAME="mcp-insta-analytics"
REGION="${AWS_REGION:-ap-northeast-1}"
TEMPLATE_FILE="template.yaml"
BUNDLE_DIR=".build/lambda"
ZIP_FILE=".build/lambda.zip"

GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }

# -----------------------------------------------------------------------------
# Build
# -----------------------------------------------------------------------------
build_bundle() {
    info "Lambda パッケージをビルド中..."
    rm -rf "${BUNDLE_DIR}" "${ZIP_FILE}"
    mkdir -p "${BUNDLE_DIR}"

    uv export --no-dev --extra lambda --no-hashes \
        --no-emit-project --python 3.12 -o requirements-lambda.txt

    uv pip install --no-cache -r requirements-lambda.txt \
        --target "${BUNDLE_DIR}" \
        --python-platform linux --python-version 3.12 \
        --python "$(mise where python@3.12)/bin/python3.12"

    cp -r src/mcp_insta_analytics "${BUNDLE_DIR}/mcp_insta_analytics"
    rm -f requirements-lambda.txt

    (cd "${BUNDLE_DIR}" && zip -q -r "../../${ZIP_FILE}" .)

    local size
    size=$(du -m "${ZIP_FILE}" | cut -f1)
    info "バンドルサイズ: ${size}MB"
    if [ "${size}" -gt 50 ]; then
        error "50MB 超過 — S3 なしではデプロイ不可"
    fi
}

# -----------------------------------------------------------------------------
# Deploy stack (CloudFormation inline template — no S3)
# -----------------------------------------------------------------------------
deploy_stack() {
    local stack_exists
    stack_exists=$(aws cloudformation describe-stacks \
        --stack-name "${STACK_NAME}" \
        --region "${REGION}" 2>/dev/null && echo "yes" || echo "no")

    if [ "${stack_exists}" = "yes" ]; then
        info "スタックを更新中: ${STACK_NAME}"
        aws cloudformation update-stack \
            --stack-name "${STACK_NAME}" \
            --template-body "file://${TEMPLATE_FILE}" \
            --parameters \
                ParameterKey=SessionCookie,ParameterValue="${SESSION_COOKIE:-}" \
                ParameterKey=ApiKey,ParameterValue="${API_KEY:-}" \
            --capabilities CAPABILITY_NAMED_IAM \
            --region "${REGION}" \
            --output text >/dev/null 2>&1 || {
                warn "テンプレート変更なし (No updates to perform)"
            }
        info "スタック更新を待機中..."
        aws cloudformation wait stack-update-complete \
            --stack-name "${STACK_NAME}" --region "${REGION}" 2>/dev/null || true
    else
        info "スタックを作成中: ${STACK_NAME}"
        aws cloudformation create-stack \
            --stack-name "${STACK_NAME}" \
            --template-body "file://${TEMPLATE_FILE}" \
            --parameters \
                ParameterKey=SessionCookie,ParameterValue="${SESSION_COOKIE:-}" \
                ParameterKey=ApiKey,ParameterValue="${API_KEY:-}" \
            --capabilities CAPABILITY_NAMED_IAM \
            --region "${REGION}" \
            --output text >/dev/null

        info "スタック作成を待機中 (2-3 分)..."
        aws cloudformation wait stack-create-complete \
            --stack-name "${STACK_NAME}" --region "${REGION}"
    fi

    info "スタック作成/更新完了"
}

# -----------------------------------------------------------------------------
# Upload Lambda code (zip → direct upload, no S3)
# -----------------------------------------------------------------------------
upload_code() {
    info "Lambda コードをアップロード中..."
    aws lambda update-function-code \
        --function-name "${FUNCTION_NAME}" \
        --zip-file "fileb://${ZIP_FILE}" \
        --region "${REGION}" \
        --output text >/dev/null

    info "デプロイ反映を待機中..."
    aws lambda wait function-updated-v2 \
        --function-name "${FUNCTION_NAME}" --region "${REGION}"
}

# -----------------------------------------------------------------------------
# Show outputs
# -----------------------------------------------------------------------------
show_outputs() {
    local url
    url=$(aws cloudformation describe-stacks \
        --stack-name "${STACK_NAME}" \
        --region "${REGION}" \
        --query "Stacks[0].Outputs[?OutputKey=='FunctionUrl'].OutputValue" \
        --output text)

    echo ""
    echo "============================================"
    echo "  MCP Endpoint: ${url}mcp/"
    echo "============================================"
    echo ""
    echo "Claude Code / Claude Desktop 設定:"
    echo ""
    if [ -n "${API_KEY:-}" ]; then
        echo "  \"insta-analytics\": {"
        echo "    \"type\": \"streamable-http\","
        echo "    \"url\": \"${url}mcp/\","
        echo "    \"headers\": {"
        echo "      \"Authorization\": \"Bearer ${API_KEY}\""
        echo "    }"
        echo "  }"
    else
        echo "  \"insta-analytics\": {"
        echo "    \"type\": \"streamable-http\","
        echo "    \"url\": \"${url}mcp/\""
        echo "  }"
        warn "API_KEY 未設定 — エンドポイントは認証なしで公開されています"
    fi
    echo ""
}

# -----------------------------------------------------------------------------
# Rotate cookie (スタック更新・再デプロイ不要)
# -----------------------------------------------------------------------------
rotate_cookie() {
    [ -z "${SESSION_COOKIE:-}" ] && error "SESSION_COOKIE が未設定です (export SESSION_COOKIE=xxx)"

    info "現在の環境変数を取得中..."
    local current_env
    current_env=$(aws lambda get-function-configuration \
        --function-name "${FUNCTION_NAME}" \
        --region "${REGION}" \
        --query 'Environment.Variables' \
        --output json)

    local new_env
    new_env=$(echo "${current_env}" | python3 -c "
import sys, json
env = json.load(sys.stdin)
env['INSTA_ANALYTICS_SESSION_COOKIE'] = '${SESSION_COOKIE}'
print(json.dumps({'Variables': env}))
")

    info "Cookie を更新中..."
    aws lambda update-function-configuration \
        --function-name "${FUNCTION_NAME}" \
        --environment "${new_env}" \
        --region "${REGION}" \
        --output text >/dev/null

    aws lambda wait function-updated-v2 \
        --function-name "${FUNCTION_NAME}" --region "${REGION}"

    info "Cookie 更新完了。"
}

# -----------------------------------------------------------------------------
# Destroy (1 コマンドで全リソース削除)
# -----------------------------------------------------------------------------
destroy() {
    warn "全リソースを削除します: ${STACK_NAME}"
    read -rp "本当に削除しますか? (yes/no): " confirm
    [ "${confirm}" != "yes" ] && { info "キャンセルしました。"; exit 0; }

    aws cloudformation delete-stack \
        --stack-name "${STACK_NAME}" --region "${REGION}"

    info "削除を待機中..."
    aws cloudformation wait stack-delete-complete \
        --stack-name "${STACK_NAME}" --region "${REGION}"

    info "全リソース削除完了。"
}

# -----------------------------------------------------------------------------
# Status (無料枠の使用状況)
# -----------------------------------------------------------------------------
show_status() {
    info "無料枠の使用状況を取得中..."

    local now
    now=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    local month_start
    month_start=$(date -u +%Y-%m-01T00:00:00Z)

    # --- Lambda -----------------------------------------------------------
    local invocations avg_duration_ms max_duration_ms
    invocations=$(aws cloudwatch get-metric-statistics \
        --namespace AWS/Lambda \
        --metric-name Invocations \
        --dimensions Name=FunctionName,Value="${FUNCTION_NAME}" \
        --start-time "${month_start}" --end-time "${now}" \
        --period 2592000 --statistics Sum \
        --region "${REGION}" \
        --query 'Datapoints[0].Sum' --output text 2>/dev/null || echo "0")
    [ "${invocations}" = "None" ] || [ -z "${invocations}" ] && invocations=0

    local duration_json
    duration_json=$(aws cloudwatch get-metric-statistics \
        --namespace AWS/Lambda \
        --metric-name Duration \
        --dimensions Name=FunctionName,Value="${FUNCTION_NAME}" \
        --start-time "${month_start}" --end-time "${now}" \
        --period 2592000 --statistics Average Maximum \
        --region "${REGION}" \
        --query 'Datapoints[0]' --output json 2>/dev/null || echo "null")

    if [ "${duration_json}" != "null" ] && [ -n "${duration_json}" ]; then
        avg_duration_ms=$(echo "${duration_json}" | python3 -c "import sys,json; print(json.load(sys.stdin).get('Average',0))")
        max_duration_ms=$(echo "${duration_json}" | python3 -c "import sys,json; print(json.load(sys.stdin).get('Maximum',0))")
    else
        avg_duration_ms=0
        max_duration_ms=0
    fi

    local memory_mb=256
    local gb_seconds
    gb_seconds=$(python3 -c "
inv=${invocations}; avg_ms=${avg_duration_ms}; mem=${memory_mb}
gb_sec = inv * (avg_ms / 1000.0) * (mem / 1024.0)
print(f'{gb_sec:.1f}')
")

    local inv_pct gb_pct
    inv_pct=$(python3 -c "print(f'{${invocations}/1000000*100:.4f}')")
    gb_pct=$(python3 -c "print(f'{${gb_seconds}/400000*100:.4f}')")

    # --- DynamoDB ---------------------------------------------------------
    local dynamo_json
    dynamo_json=$(aws dynamodb describe-table \
        --table-name mcp-insta-analytics \
        --region "${REGION}" \
        --query 'Table.{Items:ItemCount,Bytes:TableSizeBytes}' \
        --output json 2>/dev/null || echo '{"Items":0,"Bytes":0}')

    local dynamo_items dynamo_bytes dynamo_mb
    dynamo_items=$(echo "${dynamo_json}" | python3 -c "import sys,json; print(json.load(sys.stdin).get('Items',0))")
    dynamo_bytes=$(echo "${dynamo_json}" | python3 -c "import sys,json; print(json.load(sys.stdin).get('Bytes',0))")
    dynamo_mb=$(python3 -c "print(f'{${dynamo_bytes}/1048576:.2f}')")

    # --- CloudWatch Logs --------------------------------------------------
    local log_bytes log_mb
    log_bytes=$(aws logs describe-log-groups \
        --log-group-name-prefix "/aws/lambda/${FUNCTION_NAME}" \
        --region "${REGION}" \
        --query 'logGroups[0].storedBytes' --output text 2>/dev/null || echo "0")
    [ "${log_bytes}" = "None" ] || [ -z "${log_bytes}" ] && log_bytes=0
    log_mb=$(python3 -c "print(f'{${log_bytes}/1048576:.2f}')")

    # --- 表示 -------------------------------------------------------------
    echo ""
    echo "============================================"
    echo "  MCP Instagram Analytics — 無料枠使用状況 (今月)"
    echo "============================================"
    echo ""
    echo "■ Lambda (無料枠: 100万リクエスト + 400,000 GB秒/月)"
    echo "  リクエスト数:   ${invocations} / 1,000,000  (${inv_pct}%)"
    echo "  GB秒:          ${gb_seconds} / 400,000  (${gb_pct}%)"
    echo "  平均実行時間:   ${avg_duration_ms}ms"
    echo "  最大実行時間:   ${max_duration_ms}ms"
    echo ""
    echo "■ DynamoDB (無料枠: 25 RCU/WCU + 25GB)"
    echo "  アイテム数:     ${dynamo_items}"
    echo "  データサイズ:   ${dynamo_mb} MB / 25,600 MB"
    echo ""
    echo "■ CloudWatch Logs (無料枠: 5GB/月)"
    echo "  保存サイズ:     ${log_mb} MB / 5,120 MB"
    echo "  保持期間:       7日"
    echo ""
}

# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
main() {
    case "${1:-}" in
        --destroy)
            destroy ;;
        --update)
            build_bundle
            upload_code
            info "コード更新完了。" ;;
        --rotate-cookie)
            rotate_cookie ;;
        --status)
            show_status ;;
        *)
            build_bundle
            deploy_stack
            upload_code
            show_outputs
            info "デプロイ完了! すべて常時無料枠内のリソースです。" ;;
    esac
}

main "$@"
