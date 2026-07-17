#!/bin/sh
# appkit-notify stage: ping the operator's Telegram when the exposed pipeline serves an order,
# attaching the launch-kit zip from the run's frozen server-side bundle.
RID="${GITMOOT_TRIGGER_UPSTREAM_RUN_ID:-unknown}"
API="https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}"
CAPTION="🧾 appkit-demo served an order: run ${RID}. Receipt: https://gitmoot.themartian.app/receipts/${RID}"
BUNDLE="/root/.gitmoot/pipeline-service-runs/${RID}/bundle.zip"
KIT="/tmp/appkit-notify-${RID}-launch-kit.zip"
sent=0
if [ -f "$BUNDLE" ] && unzip -p "$BUNDLE" artifacts/kit/launch-kit.zip > "$KIT" 2>/dev/null && [ -s "$KIT" ]; then
  code=$(curl -s -o /dev/null -w "%{http_code}" "$API/sendDocument" \
    -F "chat_id=${TELEGRAM_CHAT_ID}" -F "caption=${CAPTION}" -F "document=@${KIT};filename=launch-kit-${RID}.zip")
  [ "$code" = "200" ] && sent=1
fi
rm -f "$KIT"
if [ "$sent" != "1" ]; then
  code=$(curl -s -o /dev/null -w "%{http_code}" "$API/sendMessage" \
    --data-urlencode "chat_id=${TELEGRAM_CHAT_ID}" --data-urlencode "text=${CAPTION} (kit attachment unavailable)")
fi
if [ "$code" = "200" ]; then
  printf '%s' "{\"gitmoot_result\":{\"decision\":\"approved\",\"summary\":\"operator notified for ${RID} (kit attached: ${sent})\",\"findings\":[],\"changes_made\":[],\"tests_run\":[],\"needs\":[],\"delegations\":[]}}"
else
  printf '%s' "{\"gitmoot_result\":{\"decision\":\"failed\",\"summary\":\"telegram returned ${code}\",\"findings\":[],\"changes_made\":[],\"tests_run\":[],\"needs\":[],\"delegations\":[]}}"
  exit 1
fi
