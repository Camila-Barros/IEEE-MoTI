import paho.mqtt.client as mqtt
import time
import uuid #para RTT
import random
import logging
import ssl # para autenticação SSL
import json
import threading
import csv
from datetime import datetime, timezone

# CONFIGURAÇÃO DE LOGS
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
mqtt_logger = logging.getLogger("paho.mqtt.client")
mqtt_logger.setLevel(logging.DEBUG)

# CERTIFICADOS TLS (acaminhos absolutos)
CA_CERT = "/home/camila/Documentos/MoTI/mqtt_tls_certs/ca.crt"
CLIENT_CERT = "/home/camila/Documentos/MoTI/mqtt_tls_certs/server.crt"
CLIENT_KEY = "/home/camila/Documentos/MoTI/mqtt_tls_certs/server.key"

# CONFIGURAÇÕES DO BROKER MQTT MOSQUITTO
BROKER = "localhost" # Endereço do broker Mosquitto, roda localmente
PORT = 8883 # porta para TLS, porta padrão é 1883 
QOS = 0  
ROOT = "fabricaBeta/maquina1" # Raiz do tópico desta fábrica/máquina

# Variáveis/medidas a publicar: (nome -> gerador de valor)
def gen_temp():   return round(random.uniform(20, 40), 2)       # °C
def gen_press():  return round(random.uniform(1.0, 6.0), 2)     # bar
def gen_torque(): return round(random.uniform(10, 250), 1)      # N·m
def gen_umid():   return round(random.uniform(30, 80), 1)       # %UR

MEASURES = {
    "temperatura": gen_temp,
    "pressao":     gen_press,
    "torque":      gen_torque,
    "umidade":     gen_umid,
}

# Tópicos de publicação e de ACK (um por variável)
def pub_topic(var): return f"{ROOT}/{var}"
def ack_topic(var): return f"moti/ack/{var}"

# caminho do CSV
CSV_PATH = "/home/camila/Documentos/MoTI/rtt_log.csv"
# cria o cabeçalho antes de rodar:
with open(CSV_PATH, "w", newline="") as f:
    csv.writer(f).writerow([
        "id","qos","var","t0","t1","rtt_ms","value","datetime","date","time","topic"
    ])

# Guarda t0 por id de mensagem
sent_times = {}   # id -> t0
sent_var   = {}   # id -> nome da variável (temperatura/pressao/torque/umidade)

# CONECTANDO
def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        logging.info("CONECTADO AO BROKER - subscrevendo a todos os ACKs…")
        # Um único wildcard para todos os ACKs
        client.subscribe("moti/ack/#", qos=QOS)
    else:
        logging.error(f"FALHA NA CONEXÃO: {rc}")

# PUBLISH
def on_publish(client, userdata, mid, reason_code, properties=None):
    logging.debug(f"Mensagem {mid} publicada. Código: {reason_code}")

# LOOP
def on_ack(client, userdata, msg):
    try:
        data = json.loads(msg.payload.decode())
        msg_id = data["id"]
        t0 = data["t0"]
        value = data.get("value")
        var = data.get("var") or data.get("metric")  # compat
        t1 = time.monotonic()
        if msg_id in sent_times:
            rtt = (t1 - sent_times.pop(msg_id))*1000  # ms
            var = var or sent_var.pop(msg_id, "desconhecida")
            agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            data_str, hora_str = agora.split(" ")
            logging.info(f"RTT {var}={value} (id={msg_id}) => {rtt:.1f} ms")
            # grava no CSV
            with open(CSV_PATH, "a", newline="") as f:
                csv.writer(f).writerow([
                    msg_id, QOS, var, t0, t1, f"{rtt:.1f}", value,
                    agora, data_str, hora_str, data.get("source_topic", "")
                ])
    except Exception as e:
        logging.error(f"Erro no on_ack: {e}")

# MONTA CLIENTE MQTT
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.on_connect = on_connect 
client.on_publish = on_publish
client.enable_logger()
client.message_callback_add("moti/ack/#", on_ack)

# CONFIGURAÇÕES TLS
client.tls_set(ca_certs=CA_CERT, certfile=CLIENT_CERT, keyfile=CLIENT_KEY,
    cert_reqs=ssl.CERT_REQUIRED,
    tls_version=ssl.PROTOCOL_TLS_CLIENT,
    ciphers=None)
client.tls_insecure_set(False)  # Rejeita certificados inválidos

# conecta e inicia loop
client.connect(BROKER, PORT, keepalive=60)
client.loop_start()
time.sleep(3) # aguarda 3s para iniciar, dando tempo dos logs de conexão aparecerem

# loop principal de publish das variáveis
try:
    while True:
        for var, gen in MEASURES.items():
            msg_id = str(uuid.uuid4())
            t0 = time.monotonic()
            value = gen()

            sent_times[msg_id] = t0
            sent_var[msg_id]   = var

            payload = json.dumps({
                "id": msg_id,
                "t0": t0,
                "var": var,
                "value": value
            })
            topic = pub_topic(var)
            client.publish(topic, payload, qos=QOS)
            logging.info(f"�� Publicando: {var}={value} (QoS={QOS}, id={msg_id}) em {topic}")

            time.sleep(5)  # pequeno espaçamento entre variáveis
        # após um ciclo completo (4 variáveis), aguarda mais um pouco
        time.sleep(10)

except KeyboardInterrupt:
    client.loop_stop()
    client.disconnect()
    logging.info("Publisher encerrado")
