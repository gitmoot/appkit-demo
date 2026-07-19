#!/bin/sh
# Internal appkit-pro completion notifier. The bot token reaches curl only
# through stdin-backed config and therefore never appears in curl's argv.

emit_result() {
  decision=$1
  summary=$2
  printf '%s\n' "{\"gitmoot_result\":{\"decision\":\"${decision}\",\"summary\":\"${summary}\",\"findings\":[],\"changes_made\":[],\"tests_run\":[],\"needs\":[],\"delegations\":[]}}"
}

TOKEN=${TELEGRAM_BOT_TOKEN:-}
CHAT_ID=${TELEGRAM_CHAT_ID:-}
RID=${GITMOOT_TRIGGER_UPSTREAM_RUN_ID:-}

if [ -z "$TOKEN" ] || [ -z "$CHAT_ID" ]; then
  printf '%s\n' 'notify-pro: Telegram configuration is missing' >&2
  emit_result failed 'notification configuration missing'
  exit 0
fi

case "$TOKEN" in
  *[!A-Za-z0-9:_-]*|'')
    printf '%s\n' 'notify-pro: bot token has an unsafe shape' >&2
    emit_result failed 'notification configuration invalid'
    exit 0
    ;;
  *:*) ;;
  *)
    printf '%s\n' 'notify-pro: bot token has an unsafe shape' >&2
    emit_result failed 'notification configuration invalid'
    exit 0
    ;;
esac
if [ "${#TOKEN}" -gt 200 ]; then
  printf '%s\n' 'notify-pro: bot token has an unsafe shape' >&2
  emit_result failed 'notification configuration invalid'
  exit 0
fi

case "$RID" in
  [A-Za-z0-9]*) ;;
  *)
    printf '%s\n' 'notify-pro: upstream run id is missing or invalid' >&2
    emit_result failed 'invalid upstream run id'
    exit 0
    ;;
esac
case "$RID" in
  *[!A-Za-z0-9._:-]*)
    printf '%s\n' 'notify-pro: upstream run id is missing or invalid' >&2
    emit_result failed 'invalid upstream run id'
    exit 0
    ;;
esac
if [ "${#RID}" -gt 128 ]; then
  printf '%s\n' 'notify-pro: upstream run id is missing or invalid' >&2
  emit_result failed 'invalid upstream run id'
  exit 0
fi

DATA_ROOT=${APPKIT_PRO_DATA_DIR:-/root/appkit-pro-data}
case "$DATA_ROOT" in
  /*) ;;
  *)
    printf '%s\n' 'notify-pro: APPKIT_PRO_DATA_DIR is not absolute' >&2
    emit_result failed 'personal data root invalid'
    exit 0
    ;;
esac

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
APP_NAME=''
ORDER_NAME_READ=0
if [ -f "$DATA_ROOT/order.yaml" ] && [ ! -L "$DATA_ROOT/order.yaml" ]; then
  if APP_NAME=$(PYTHONPATH="$SCRIPT_DIR" python3 - <<'PY'
import pro_inputs

try:
    value = pro_inputs.load_persisted_app_name()
    print("" if value is None else value)
except Exception:
    raise SystemExit(2)
PY
  ); then
    ORDER_NAME_READ=1
  else
    APP_NAME=''
    printf '%s\n' 'notify-pro: persisted order is invalid; omitting app name' >&2
  fi
else
  printf '%s\n' 'notify-pro: persisted order is unavailable; omitting app name' >&2
fi
if [ "$ORDER_NAME_READ" = '1' ] && [ -z "$APP_NAME" ]; then
  printf '%s\n' 'notify-pro: persisted order has no explicit app name; omitting it' >&2
fi

if [ -n "$APP_NAME" ]; then
  CAPTION="appkit-pro built a kit for ${APP_NAME} (run ${RID})"
else
  CAPTION="appkit-pro built a kit (run ${RID})"
fi
KIT="$DATA_ROOT/kit/launch-kit.zip"

telegram_config() {
  endpoint=$1
  printf 'url = "https://api.telegram.org/bot%s/%s"\n' "$TOKEN" "$endpoint"
}

send_document() {
  document_code=''
  document_code=$(telegram_config sendDocument | curl --config - \
    --silent --show-error --output /dev/null --write-out '%{http_code}' \
    --connect-timeout 20 --max-time 240 \
    --form-string "chat_id=${CHAT_ID}" \
    --form-string "caption=${CAPTION}" \
    --form "document=@\"${KIT}\"")
  document_status=$?
  if [ "$document_status" -ne 0 ]; then
    printf '%s\n' 'notify-pro: sendDocument transport failed; using text fallback' >&2
    document_code=''
  fi
}

send_message() {
  fallback_text=$1
  message_code=''
  message_code=$(telegram_config sendMessage | curl --config - \
    --silent --show-error --output /dev/null --write-out '%{http_code}' \
    --connect-timeout 20 --max-time 240 \
    --data-urlencode "chat_id=${CHAT_ID}" \
    --data-urlencode "text=${fallback_text}")
  message_status=$?
  if [ "$message_status" -ne 0 ]; then
    printf '%s\n' 'notify-pro: sendMessage transport failed' >&2
    message_code=''
  fi
}

attached=0
fallback_reason=''
if [ ! -e "$KIT" ]; then
  fallback_reason='kit missing'
  printf '%s\n' 'notify-pro: persisted kit is missing; using text fallback' >&2
elif [ -L "$KIT" ] || [ ! -f "$KIT" ]; then
  fallback_reason='kit path unsafe'
  printf '%s\n' 'notify-pro: persisted kit path is unsafe; using text fallback' >&2
elif [ ! -r "$KIT" ] || [ ! -s "$KIT" ]; then
  fallback_reason='kit unreadable'
  printf '%s\n' 'notify-pro: persisted kit is unreadable or empty; using text fallback' >&2
else
  send_document
  if [ "$document_code" = '200' ]; then
    attached=1
  else
    fallback_reason="sendDocument HTTP ${document_code:-transport-error}"
    printf '%s\n' "notify-pro: ${fallback_reason}; using text fallback" >&2
  fi
fi

if [ "$attached" = '1' ]; then
  emit_result approved "operator notified for ${RID} (kit attached: 1)"
  exit 0
fi

send_message "${CAPTION} (kit attachment unavailable: ${fallback_reason})"
if [ "$message_code" = '200' ]; then
  emit_result approved "operator notified for ${RID} (kit attached: 0)"
else
  printf '%s\n' "notify-pro: Telegram text fallback failed with HTTP ${message_code:-transport-error}" >&2
  emit_result failed "telegram returned ${message_code:-transport-error}"
fi
exit 0
