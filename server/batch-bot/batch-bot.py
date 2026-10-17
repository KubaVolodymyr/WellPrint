#!/usr/bin/env python3
"""batch-bot.py — хаб керування тиражем з Telegram. Python 3.8+, без сторонніх бібліотек.
(1) слухає бота (getUpdates, довге опитування), веде діалог «Старт друку → машина → по скільки → скільки всього»;
(2) сам читає PrintHistory.xml машин через мережеву шару (history у config) і рахує столи;
    запасний варіант — POST /print-done від вотчера print-watch.ps1 на машині;
(3) пише прогрес і «Тираж готовий» у канал. Стан — state.json поруч зі скриптом;
(4) віддає стан інформеру на машині: GET /status, POST /batch-start, POST /defect (заголовок X-Hub-Token).
Запуск: python3 batch-bot.py   (config.json поруч, див. гайд)
"""
import json, os, re, sys, time, threading, urllib.request, urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer

DIR = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(open(os.path.join(DIR, "config.json"), encoding="utf-8"))
TOKEN, CHAT = CFG["token"], str(CFG["chat_id"])
HUB_TOKEN, PORT = CFG["hub_token"], int(CFG.get("port", 8765))
MACHINES = list(CFG["machines"].keys())          # {"UF-3570": "<шлях до PrintHistory.xml або порожньо>"}
HISTORY = {m: p for m, p in CFG["machines"].items() if p}
STALE_SEC, HIST_POLL = 2 * 86400, 5
PERS, TOTALS = [1, 2, 4, 6, 8], [10, 20, 30, 50, 100, 200]
STATE_FILE, LOG_FILE = os.path.join(DIR, "state.json"), os.path.join(DIR, "bot.log")
API = "https://api.telegram.org/bot%s/" % TOKEN
lock = threading.Lock()


def log(m):
    line = time.strftime("%Y-%m-%d %H:%M:%S ") + m
    print(line, flush=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def load():
    try:
        return json.load(open(STATE_FILE, encoding="utf-8"))
    except Exception:
        return {"flow": None, "batch": None, "last": None, "offset": 0, "seen": {}}


def save(st):
    tmp = STATE_FILE + ".tmp"
    json.dump(st, open(tmp, "w", encoding="utf-8"), ensure_ascii=False)
    os.replace(tmp, STATE_FILE)


def tg(method, **params):
    data = json.dumps(params).encode("utf-8")
    req = urllib.request.Request(API + method, data=data, headers={"Content-Type": "application/json"})
    try:
        return json.load(urllib.request.urlopen(req, timeout=40))
    except Exception as e:
        log("tg %s fail: %s" % (method, e))
        return None


def kb(rows):
    return {"inline_keyboard": rows}


def send(text, rows=None):
    tg("sendMessage", chat_id=CHAT, text=text, parse_mode="HTML", reply_markup=kb(rows or []))


def edit(mid, text, rows=None):
    tg("editMessageText", chat_id=CHAT, message_id=mid, text=text, parse_mode="HTML", reply_markup=kb(rows or []))


def chunk(items, n):
    return [items[i:i + n] for i in range(0, len(items), n)]


# ───────── діалог ─────────
def send_start():
    send("🖨 <b>Друк</b> — керування тиражем.", [[{"text": "▶️ Старт друку", "callback_data": "start"}]])


def ask_total(mid):
    rows = chunk([{"text": str(t), "callback_data": "t:%d" % t} for t in TOTALS] + [{"text": "✏️", "callback_data": "t:ask"}], 3)
    txt = "🖨 Скільки <b>всього</b> штук у тиражі?"
    edit(mid, txt, rows) if mid else send(txt, rows)


def begin(st, machine, per, total, src=""):
    """Старт тиражу — спільний для кнопок бота і для «Старт» в інформері на машині."""
    per, total = max(1, int(per)), max(1, int(total))
    rounds = max(1, -(-total // per))             # ceil
    st["batch"] = {"machine": machine, "per": per, "total": total, "rounds": rounds, "done": 0,
                   "defects": 0, "start_ts": int(time.time()), "ticks": [], "at": time.strftime("%Y-%m-%d %H:%M")}
    st["flow"], st["last"] = None, None
    txt = ("▶️ <b>Друк запущено</b>%s\n🖨 %s\nВсього: <b>%d</b> шт · по %d за раз · %d стіл(ів)\n\nДрукуй — рахую. Напишу, коли готово."
           % ((" (%s)" % src) if src else "", machine, total, per, rounds))
    log("batch start %s" % st["batch"])
    return txt, [[{"text": "⏹ Зупинити", "callback_data": "stop"}]]


def start_batch(st, total, mid):
    flow = st["flow"] or {}
    txt, rows = begin(st, flow.get("machine", MACHINES[0]), flow.get("per", 1), total)
    edit(mid, txt, rows) if mid else send(txt, rows)


def on_callback(st, cq):
    data, mid = cq.get("data", ""), cq["message"]["message_id"]
    tg("answerCallbackQuery", callback_query_id=cq["id"])
    if data == "start":
        st["flow"] = {"step": "machine"}
        edit(mid, "🖨 <b>Друк</b> — обери машину:", [[{"text": m, "callback_data": "m:" + m} for m in MACHINES]])
    elif data.startswith("m:"):
        st["flow"] = {"step": "per", "machine": data[2:]}
        rows = chunk([{"text": str(p), "callback_data": "p:%d" % p} for p in PERS] + [{"text": "✏️", "callback_data": "p:ask"}], 3)
        edit(mid, "🖨 Скільки штук <b>за раз</b> (на стіл)?", rows)
    elif data.startswith("p:") and st["flow"]:
        if data == "p:ask":
            st["flow"]["step"] = "per_input"
            edit(mid, "✏️ Напиши <b>скільки за раз</b> (число):")
        else:
            st["flow"].update(step="total", per=int(data[2:]))
            ask_total(mid)
    elif data.startswith("t:") and st["flow"]:
        if data == "t:ask":
            st["flow"]["step"] = "total_input"
            edit(mid, "✏️ Напиши <b>скільки всього</b> штук (число):")
        else:
            start_batch(st, int(data[2:]), mid)
    elif data == "stop":
        st["batch"] = None
        edit(mid, "⏹ Тираж зупинено.")


def on_text(st, msg):
    text = (msg.get("text") or "").strip()
    low = text.lower()
    if any(w in low for w in ("друк", "старт", "print")):
        send_start()
        return
    flow = st["flow"]
    if not flow or not text.isdigit():
        return
    n = max(1, int(text))
    if flow["step"] == "per_input":
        flow.update(step="total", per=n)
        ask_total(0)
    elif flow["step"] == "total_input":
        start_batch(st, n, 0)


def poll_loop():
    while True:
        with lock:
            offset = load().get("offset", 0)
        r = tg("getUpdates", offset=offset, timeout=30, allowed_updates=["message", "channel_post", "callback_query"])
        if not r or not r.get("ok"):
            time.sleep(5)
            continue
        for u in r["result"]:
            with lock:
                st = load()
                st["offset"] = u["update_id"] + 1
                try:
                    if "callback_query" in u and str(u["callback_query"]["message"]["chat"]["id"]) == CHAT:
                        on_callback(st, u["callback_query"])
                    else:
                        msg = u.get("channel_post") or u.get("message")
                        if msg and str(msg["chat"]["id"]) == CHAT:
                            on_text(st, msg)
                except Exception as e:
                    log("update fail: %s" % e)
                save(st)


# ───────── подія «джоб надруковано» від машини ─────────
def pieces_ok(b):
    return min(max(0, b["done"] * b["per"] - b.get("defects", 0)), b["total"])


def on_print_done(machine, job):
    with lock:
        st = load()
        b = st.get("batch")
        if not b:
            log("done %s/%s — тиражу нема, ігнорую" % (machine, job))
            return
        if machine and machine != b["machine"]:
            log("done %s — інша машина (тираж на %s), ігнорую" % (machine, b["machine"]))
            return
        b["done"] += 1
        b.setdefault("ticks", []).append(int(time.time()))
        b["ticks"] = b["ticks"][-50:]
        defects = b.get("defects", 0)
        if b["done"] >= b["rounds"]:
            now = int(time.time())
            elapsed = now - b.get("start_ts", now)
            st["last"] = {"machine": b["machine"], "total": b["total"], "rounds": b["done"], "defects": defects,
                          "start": b.get("start_ts", now), "finished": now, "elapsed": elapsed,
                          "pace": elapsed // b["done"] if b["done"] else 0}
            send("✅ <b>Тираж готовий</b>\n🖨 %s\nНадруковано <b>%d</b> шт (%d стіл(ів))%s."
                 % (b["machine"], b["total"], b["done"], (", брак %d шт дотиражовано" % defects) if defects else ""))
            st["batch"] = None
        else:
            send("🖨 %s: %d/%d шт (стіл %d/%d)%s" % (b["machine"], pieces_ok(b), b["total"], b["done"], b["rounds"],
                                                     (" · брак %d" % defects) if defects else ""))
        save(st)


def defect(n, machine):
    """«Брак» з інформера: n шт зі столу → дотираж (столів стає ceil((total+defects)/per)), повідомлення в канал."""
    with lock:
        st = load()
        b = st.get("batch")
        if not b:
            return False, "Тираж не запущено"
        if machine and b["machine"] != machine:
            return False, "Тираж іде на іншій машині (%s)" % b["machine"]
        b["defects"] = b.get("defects", 0) + max(1, int(n))
        b["rounds"] = max(b["done"], -(-(b["total"] + b["defects"]) // b["per"]))
        save(st)
        send("⚠️ <b>БРАК %d шт</b> · 🖨 %s\nПридатних %d/%d, столів тепер %d."
             % (n, b["machine"], pieces_ok(b), b["total"], b["rounds"]))
        log("defect %d on %s" % (n, b["machine"]))
        return True, "ok"


def fmt_dur(s):
    s = max(0, int(s))
    return ("%d год %02d хв" % (s // 3600, s % 3600 // 60)) if s >= 3600 else ("%d хв" % (s // 60) if s >= 60 else "%d с" % s)


def round_seconds(b):
    """Очікувана тривалість столу: середнє останніх 5 інтервалів між готовими столами без явних пауз (>2×медіани), +5 %."""
    pts = [b.get("start_ts", 0)] + list(b.get("ticks", []))
    iv = [pts[i] - pts[i - 1] for i in range(1, len(pts)) if pts[i] > pts[i - 1]][-5:]
    if not iv:
        return 0
    srt = sorted(iv)
    n = len(srt)
    med = srt[n // 2] if n % 2 else (srt[n // 2 - 1] + srt[n // 2]) / 2
    ok = [x for x in iv if x <= 2 * med] or iv
    return int(round(sum(ok) / len(ok) * 1.05))


def status():
    """JSON для інформера на машині (GET /status)."""
    with lock:
        st = load()
        b, last = st.get("batch"), st.get("last")
    now = int(time.time())
    if not b:
        if last and now - last["finished"] < 300:
            txt = "✅ Тираж виконано: %d шт%s\nза %s (з %s до %s)%s" % (
                last["total"], (" (брак %d)" % last["defects"]) if last["defects"] else "", fmt_dur(last["elapsed"]),
                time.strftime("%H:%M", time.localtime(last["start"])), time.strftime("%H:%M", time.localtime(last["finished"])),
                ("\nу середньому %s на стіл" % fmt_dur(last["pace"])) if last["rounds"] > 1 else "")
            return {"ok": True, "active": False, "done": True, "text": txt, "at": time.strftime("%H:%M")}
        return {"ok": True, "active": False, "text": "Тираж не запущено", "at": time.strftime("%H:%M")}
    elapsed = now - b.get("start_ts", now)
    pace = elapsed / b["done"] if b["done"] else 0
    left = int((b["rounds"] - b["done"]) * pace) if pace else 0
    eta = time.strftime("%H:%M", time.localtime(now + left)) if left else ""
    line1 = ("%d/%d шт · стіл %d/%d" if b["per"] > 1 else "%d/%d шт") % ((pieces_ok(b), b["total"], b["done"], b["rounds"])[:4 if b["per"] > 1 else 2])
    if b.get("defects"):
        line1 += " · брак %d" % b["defects"]
    line2 = "в роботі %s (з %s)" % (fmt_dur(elapsed), time.strftime("%H:%M", time.localtime(b.get("start_ts", now))))
    line3 = ("ще ~%s · готово ≈ %s" % (fmt_dur(left), eta)) if left else "чекаю перший стіл…"
    ticks = b.get("ticks", [])
    return {"ok": True, "active": True, "machine": b["machine"], "pieces": pieces_ok(b), "total": b["total"],
            "d": b["done"], "t": b["rounds"], "per": b["per"], "defects": b.get("defects", 0),
            "last_ts": max(ticks) if ticks else b.get("start_ts", now), "round_s": round_seconds(b), "server_ts": now,
            "text": line1 + "\n" + line2 + "\n" + line3, "at": time.strftime("%H:%M")}


# ───────── читання PrintHistory.xml з мережевої шари (варіант «один сервер») ─────────
REC = re.compile(r"<SPrintHistoryRecord>(.*?)</SPrintHistoryRecord>", re.S)


def field(rec, name):
    m = re.search(r"<%s>(.*?)</%s>" % (name, name), rec, re.S)
    return (m.group(1) if m else "").strip()


def read_records(path):
    try:
        raw = open(path, "rb").read()
    except Exception:
        return None                                   # WellPrint саме пише або шара недоступна → наступного разу
    for enc in ("utf-8", "gb2312", "cp1251", "latin-1"):
        try:
            txt = raw.decode(enc)
            break
        except Exception:
            continue
    else:
        txt = raw.decode("utf-8", "ignore")
    out = []
    for body in REC.findall(txt):
        pt = field(body, "printTime")
        if not pt:
            continue
        job = os.path.splitext(os.path.basename(field(body, "jobFullPath").replace("\\", "/")))[0]
        ok = field(body, "jobCancel").lower() != "true" and field(body, "copyCount_complete") == field(body, "copyCount_all")
        out.append((pt, job, ok))
    return out


def is_stale(pt):
    try:
        return time.time() - time.mktime(time.strptime(pt[:19], "%Y-%m-%dT%H:%M:%S")) > STALE_SEC
    except Exception:
        return True


def history_loop():
    sig = {}
    while True:
        for machine, path in HISTORY.items():
            try:
                st_ = os.stat(path)
                cur = (st_.st_mtime, st_.st_size)
            except Exception:
                continue
            if sig.get(path) == cur:
                continue
            recs = read_records(path)
            if recs is None:
                continue
            sig[path] = cur
            with lock:
                st = load()
                seen = set(st["seen"].get(machine, []))
                first = not seen                      # перший запуск: усе наявне = бачене, історію не шлемо
                new = [r for r in recs if r[0] not in seen]
                st["seen"][machine] = sorted(seen | {r[0] for r in recs})[-5000:]
                save(st)
            if first:
                log("%s: базлайн %d записів" % (machine, len(recs)))
                continue
            for pt, job, ok in sorted(new):
                if is_stale(pt) or not ok:
                    continue
                log("%s: надруковано %s (%s)" % (machine, job, pt))
                on_print_done(machine, job)
        time.sleep(HIST_POLL)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):   # тихий сервер
        pass

    def reply(self, code, obj):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def authed(self):
        return self.headers.get("X-Hub-Token", "") == HUB_TOKEN

    def body(self):
        n = int(self.headers.get("Content-Length", 0))
        try:
            return json.loads(self.rfile.read(n).decode("utf-8") or "{}")
        except Exception:
            return {}

    def do_POST(self):
        if not self.authed():
            return self.reply(401, {"ok": False, "error": "unauthorized"})
        b = self.body()
        if self.path == "/print-done":            # вотчер на машині (запасний варіант без шари)
            log("event: %s" % b)
            on_print_done(str(b.get("machine", "")), str(b.get("job", "")))
            return self.reply(200, {"ok": True})
        if self.path == "/batch-start":           # кнопка «Старт» в інформері
            with lock:
                st = load()
                if st.get("batch"):
                    return self.reply(409, {"ok": False, "msg": "Тираж уже йде — спершу зупини його в Telegram"})
                machine = str(b.get("machine", "")) or MACHINES[0]
                txt, rows = begin(st, machine, min(99, int(b.get("per", 1))), min(9999, int(b.get("total", 1))), "з інформера")
                save(st)
            send(txt, rows)
            return self.reply(200, {"ok": True})
        if self.path == "/defect":                # кнопка «Брак» в інформері
            ok, msg = defect(int(b.get("pieces", 1)), str(b.get("machine", "")))
            return self.reply(200 if ok else 409, {"ok": ok, "msg": msg})
        self.reply(404, {"ok": False})

    def do_GET(self):
        if self.path == "/health":                # перевірка «хаб живий»: http://<hub>:8765/health — без токена
            self.send_response(200); self.end_headers(); self.wfile.write(b"ok"); return
        if self.path == "/status":                # інформер на машині, раз на 5 с
            if not self.authed():
                return self.reply(401, {"ok": False, "error": "unauthorized"})
            return self.reply(200, status())
        self.reply(404, {"ok": False})


if __name__ == "__main__":
    log("hub start, port %d, machines %s" % (PORT, MACHINES))
    threading.Thread(target=poll_loop, daemon=True).start()
    if HISTORY:
        threading.Thread(target=history_loop, daemon=True).start()
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
