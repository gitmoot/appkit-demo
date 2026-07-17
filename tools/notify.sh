#!/bin/sh
# appkit-notify stage: ping the operator's Telegram when the exposed pipeline serves an order.
RID="${GITMOOT_TRIGGER_UPSTREAM_RUN_ID:-unknown}"
TEXT="🧾 appkit-demo served an order: run ${RID} succeeded. Receipt: https://gitmoot.themartian.app/receipts/${RID}"
code=$(curl -s -o /tmp/notify-resp.$$ -w "%{http_code}" "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
  --data-urlencode "chat_id=${TELEGRAM_CHAT_ID}" --data-urlencode "text=${TEXT}")
rm -f /tmp/notify-resp.$$
if [ "$code" = "200" ]; then
  printf '%s' "{\"gitmoot_result\":{\"decision\":\"approved\",\"summary\":\"operator notified for ${RID}\",\"findings\":[],\"changes_made\":[],\"tests_run\":[],\"needs\":[],\"delegations\":[]}}"
else
  printf '%s' "{\"gitmoot_result\":{\"decision\":\"failed\",\"summary\":\"telegram sendMessage returned ${code}\",\"findings\":[],\"changes_made\":[],\"tests_run\":[],\"needs\":[],\"delegations\":[]}}"
  exit 1
fi
