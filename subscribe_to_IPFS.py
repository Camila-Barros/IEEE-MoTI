import paho.mqtt.client as mqtt
import requests
import logging
import json
import ssl
import time
import hashlib
import subprocess
import shlex
from datetime import datetime, timezone

# CONFIGURAÇÃO DE LOGS
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# CERTIFICADOS TLS MQTT 
CA_CERT = "/home/camila/Documentos/MoTI/mqtt_tls_certs/ca.crt"
CLIENT_CERT = "/home/camila/Documentos/MoTI/mqtt_tls_certs/server.crt"
CLIENT_KEY = "/home/camila/Documentos/MoTI/mqtt_tls_certs/server.key"

# CONFIGURAÇÕES DO IPFS PROTEGIDO POR mTLS VIA NGINX
IPFS_API_URL = "https://18.216.73.135:8443/api/v0/add" #PORTA 8443, COM IPFS PROTEGIDO POR mTLS VIA NGINX
NGINX_CA    = "/home/camila/Documentos/MoTI/mqtt_tls_certs/nginx-ca.crt"
CERT_CLIENT = "/home/camila/Documentos/MoTI/mqtt_tls_certs/nginx-client.crt"
KEY_CLIENT  = "/home/camila/Documentos/MoTI/mqtt_tls_certs/nginx-client.key"

# CONFIGURAÇÕES DO SSH PARA APPEND REMOTO
SSH_KEY      = "/home/camila/aws-keys/ipfs-key.pem"
SSH_HOST     = "ubuntu@18.216.73.135"
REMOTE_FILE  = "/var/www/ipfs_data/data.jsonl"
SSH_BIN      = "/usr/bin/ssh"

# CONFIGURAÇÕES DO BROKER MQTT MOSQUITTO
BROKER = "localhost" # Endereço do broker Mosquitto, roda localmente
PORT = 8883 # (1883) porta padrão do MQTT / (8883) porta para TLS
#TOPIC = "fabricaBeta/maquina1/temperatura" #Tópico
QOS = 2
ROOT = "fabricaBeta/maquina1" # Raiz do tópico desta fábrica/máquina

# Variáveis/medidas da maquina1 
PUB_TOPICS = [
    f"{ROOT}/temperatura",
    f"{ROOT}/pressao",
    f"{ROOT}/torque",
    f"{ROOT}/umidade",
]

# TÓPICO PARA RTT
ACK_ROOT = "moti/ack"  # ACK por variável: moti/ack/<var>

def ack_topic(var: str) -> str:
    return f"{ACK_ROOT}/{var}"

def processar_payload(data: dict, var: str):
    """
    Envia ao IPFS (HTTPS+mTLS), notifica via MQTT com o CID
    e faz append remoto (SSH) no data.jsonl.
    """
    payload_json = json.dumps(data).encode()
    response = requests.post(
        IPFS_API_URL,
        files={"file": payload_json},
        cert=(CERT_CLIENT, KEY_CLIENT),
        verify=NGINX_CA,
        timeout=15
    )

    if response.status_code != 200:
        logging.error(f"❌ Erro IPFS: {response.status_code} {response.text}")
        return

    cid = response.json().get("Hash")
    logging.info(f"Enviado ao IPFS: CID={cid}")

    # Notifica consumidores remotos com o CID
    try:
        notify_payload = {
            "cid": cid,
            "ts": datetime.now(timezone.utc).isoformat(),
            "source_topic": data.get("topic"),
            "id": data.get("id"),
            "qos": data.get("qos"),
            "sha256": data.get("hash"),
            "value": data.get("value"),
            "filename": f"{var}_{data.get('id','')}.json"
        }
        client.publish("moti/ipfs/notify", json.dumps(notify_payload), qos=0, retain=False)
        logging.info(f"Notificado moti/ipfs/notify com CID={cid}")
    except Exception as e:
        logging.error(f"❌ Falha ao notificar CID no MQTT: {e}")

    # Append no índice remoto
    data["cid"] = cid
    line = json.dumps(data)

    ssh_cmd = (
        f"{SSH_BIN} -i {shlex.quote(SSH_KEY)} "
        "-o BatchMode=yes -o StrictHostKeyChecking=no "
        f"{SSH_HOST} "
        f"\"echo {shlex.quote(line)} >> {REMOTE_FILE}\""
    )

    try:
        proc = subprocess.run(
            ssh_cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=15
        )
        if proc.returncode:
            logging.error(f"❌ SSH falhou ({proc.returncode}): {proc.stderr.strip()}")
        else:
            logging.info("Append remoto OK")
    except Exception:
        logging.exception("❌ Exceção ao executar SSH append")

    logging.info(f"https://ipfs.io/ipfs/{cid}")

# CALLBACK DE CONEXÃO
def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        for t in PUB_TOPICS:
            client.subscribe(t, qos=QOS)
            logging.info(f"CONECTADO e inscrito em {t}")
    else:
        logging.error(f"❌ Falha na conexão MQTT: {rc}")

# CALLBACK PARA MENSAGENS
def on_message(client, userdata, msg):
    """
    Processa mensagens para qualquer uma das variáveis.
    Espera payload: {"id","t0","var","value"}
    """
    try:
        data_in = json.loads(msg.payload.decode())
    except json.JSONDecodeError:
        logging.error("Payload inválido (não-JSON)")
        return

     # Identifica variável a partir do payload (preferível) ou do tópico
    var = data_in.get("var")
    if not var:
        # fallback pelo tópico
        try:
            var = msg.topic.split("/")[-1]
        except Exception:
            var = "desconhecida"
    msg_id = data_in.get("id")
    t0     = data_in.get("t0")
    value  = data_in.get("value")

    # Log do valor recebido
    logging.info(f"�� Recebido {var}={value} de {msg.topic} (QoS={msg.qos}, id={msg_id})")

    # Prepara registro para IPFS/índice
    record = {
        "id": msg_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "topic": msg.topic,
        "var": var,
        "value": value,
        "payload": str(value),   # compatibilidade (string)
        "qos": msg.qos,
        # Hash256 somente em QoS 2 
        "hash": hashlib.sha256(msg.payload).hexdigest() if msg.qos == 2 else None
    }

    # Envia ao IPFS e faz append remoto
    processar_payload(record, var)

    # envia ACK de volta para medir RTT
    ack_payload = json.dumps({
        "id": msg_id,
        "t0": t0,
        "var": var,
        "value": value,
        "source_topic": msg.topic
    })

    client.publish(ack_topic(var), ack_payload, qos=QOS)
    logging.info(f"ACK enviado ({var}) para id={msg_id}")

# MONTA E CONFIGURA MQTT CLIENT
client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
client.on_connect = on_connect
client.on_message = on_message
client.enable_logger()

# TLS MQTT
client.tls_set(ca_certs=CA_CERT, certfile=CLIENT_CERT, keyfile=CLIENT_KEY)
client.tls_insecure_set(False)

# CONECTA E INICIA LOOP
client.connect(BROKER, PORT, keepalive=60)
client.loop_forever()
