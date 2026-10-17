#!/bin/bash
# host-watch.sh — пінгує машину й шле в Telegram, коли вона зникла / повернулась.
# config поруч із скриптом (chmod 600): TOKEN=..., CHAT=..., HOST=192.168.1.20, LABEL=UF-3570
DIR="$(cd "$(dirname "$0")" && pwd)"; . "$DIR/config"
DOWN_AFTER=10; REPEAT=60          # хвилин
STATE="$DIR/state.$HOST"; LOG="$DIR/watch.log"
now=$(date +%s)
send() { curl -s -m 20 -X POST "https://api.telegram.org/bot$TOKEN/sendMessage" --data-urlencode "chat_id=$CHAT" --data-urlencode "text=🖨 $LABEL: $1" >/dev/null; echo "$(date '+%F %T') SEND: $1" >>"$LOG"; }

# три пінги, досить одного успішного
if ping -c 3 -W 2 "$HOST" >/dev/null 2>&1; then up=1; else up=0; fi

# стан: down_since alerted_at
read -r down_since alerted_at < "$STATE" 2>/dev/null || { down_since=0; alerted_at=0; }

if [ "$up" = 0 ]; then
  [ "$down_since" = 0 ] && down_since=$now
  mins=$(( (now - down_since) / 60 ))
  if [ "$mins" -ge "$DOWN_AFTER" ] && [ $(( (now - alerted_at) / 60 )) -ge "$REPEAT" ]; then
    send "🔌 Машина $HOST не відповідає вже $mins хв (вимкнена, зависла або без мережі)."
    alerted_at=$now
  fi
else
  [ "$alerted_at" != 0 ] && send "🟢 Машина $HOST знову в мережі (не відповідала з $(date -r "$down_since" '+%H:%M' 2>/dev/null || date -d "@$down_since" '+%H:%M'))."
  down_since=0; alerted_at=0
fi
echo "$down_since $alerted_at" > "$STATE"
