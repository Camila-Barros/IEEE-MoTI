import os, time, re, csv, json, pathlib, logging, requests
from datetime import datetime

DATA_URL = os.getenv("DATA_URL", "https://18.216.73.135:8443/moti/data.jsonl")
CA_PATH  = "certs/nginx-ca.crt"
CRT_PATH = "certs/nginx-client.crt"
KEY_PATH = "certs/nginx-client.key"

OUT_DIR  = pathlib.Path("exports")
LOG_DIR  = pathlib.Path("logs")
STATE_F  = LOG_DIR / "csv_seen_ids.json"   # para não duplicar linhas
CSV_F    = OUT_DIR / "moti_dados.csv"      

LOG_DIR.mkdir(parents=True, exist_ok=True)
OUT_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# regex para extrair campos das linhas "soltas" (não-JSON estrito)
RE = {
    "id":        re.compile(r'\bid\s*:\s*([0-9a-fA-F-]{8,})'),
    "timestamp": re.compile(r'\btimestamp\s*:\s*([0-9T:\-+.Z]+)'),
    "topic":     re.compile(r'\btopic\s*:\s*([^\s,}]+)'),
    "payload":   re.compile(r'\bpayload\s*:\s*([^\s,}]+)'),
    "qos":       re.compile(r'\bqos\s*:\s*([0-2])'),
    "cid":       re.compile(r'\bcid\s*:\s*([A-Za-z0-9]+)'),
}

HEADERS = ["id","timestamp_utc","topic","payload","qos","cid"]

def load_state():
    if STATE_F.exists():
        try:
            return set(json.loads(STATE_F.read_text()).get("seen", []))
        except Exception:
            pass
    return set()

def save_state(seen):
    STATE_F.write_text(json.dumps({"seen": sorted(seen)}, ensure_ascii=False, indent=2))

def ensure_csv():
    if not CSV_F.exists():
        with CSV_F.open("w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(HEADERS)

def parse_line(line: str):
    # tenta JSON primeiro
    try:
        obj = json.loads(line)
        return {
            "id":        str(obj.get("id") or ""),
            "timestamp": str(obj.get("timestamp") or ""),
            "topic":     str(obj.get("topic") or ""),
            "payload":   str(obj.get("payload") or ""),
            "qos":       str(obj.get("qos") or ""),
            "cid":       str(obj.get("cid") or ""),
        }
    except Exception:
        pass
    # fallback: regex
    fields = {}
    for k, rgx in RE.items():
        m = rgx.search(line)
        if m:
            fields[k] = m.group(1)
        else:
            fields[k] = ""
    return {
        "id":        fields["id"],
        "timestamp": fields["timestamp"],
        "topic":     fields["topic"],
        "payload":   fields["payload"],
        "qos":       fields["qos"],
        "cid":       fields["cid"],
    }

def fetch_index():
    r = requests.get(DATA_URL, verify=CA_PATH, cert=(CRT_PATH, KEY_PATH), timeout=30)
    r.raise_for_status()
    return r.text

def main():
    ensure_csv()
    seen = load_state()
    logging.info("Iniciando exportador CSV (a partir do data.jsonl)…")
    while True:
        try:
            text = fetch_index()
            new = False
            rows_to_append = []
            for line in text.splitlines():
                if not line.strip():
                    continue
                rec = parse_line(line)
                if not rec["id"] and rec["cid"]:
                    # se não tiver o id, usa o cid como chave
                    rec_id = f"cid:{rec['cid']}"
                else:
                    rec_id = rec["id"]
                if not rec_id:
                    # sem id nem cid: pula
                    continue
                if rec_id in seen:
                    continue
                # normaliza timestamp
                ts = rec["timestamp"] or datetime.utcnow().isoformat()
                rows_to_append.append([
                    rec_id, ts, rec["topic"], rec["payload"], rec["qos"], rec["cid"]
                ])
                seen.add(rec_id); new = True

            if rows_to_append:
                with CSV_F.open("a", newline="", encoding="utf-8") as f:
                    w = csv.writer(f)
                    for row in rows_to_append:
                        w.writerow(row)
                logging.info(f"➕ {len(rows_to_append)} linha(s) adicionadas a {CSV_F}")

            if new:
                save_state(seen)

        except Exception as e:
            logging.error(f"Erro: {e}")

        time.sleep(10)

if __name__ == "__main__":
    main()
