# MoTI Implementation Guide

This guide provides a complete step-by-step implementation of the MoTI architecture, including local setup, secure MQTT communication, and remote IPFS integration using AWS.

---

## Overview

The MoTI implementation is executed in a Linux environment (Ubuntu), where MQTT publisher and subscriber services operate as independent processes.

The architecture enables:

- IoT data collection  
- Secure message exchange via MQTT (TLS/mTLS)  
- Data processing and forwarding  
- Distributed storage using IPFS  
- Data integrity validation  

This guide ensures full reproducibility of the experimental setup presented in the manuscript.

---

# 1. Local Environment (IoT Data Collection)

## 1.1 System Preparation

Update system packages:

```bash
sudo apt update && sudo apt upgrade -y
```

Install required dependencies:

```bash
sudo apt install -y python3 python3-venv python3-pip mosquitto mosquitto-clients openssl
```


## 1.2 Python Environment

Create and activate virtual environment:

```bash
python3 -m venv venv
source venv/bin/activate
```

Install required libraries:

```bash
pip install paho-mqtt requests
```

## 1.3 MQTT TLS Configuration (Mosquitto)

Create directory for certificates:

```bash
sudo mkdir -p /etc/mosquitto/certs
```

Generate CA

```bash
openssl genrsa -out ca.key 2048
openssl req -x509 -new -nodes -key ca.key -sha256 -days 3650 -out ca.crt \
-subj "/C=BR/ST=SP/L=SaoPaulo/O=EmpresaBeta/OU=TI/CN=EmpresaBetaRootCA"
```

Server Certificate

```bash
openssl genrsa -out server.key 2048
openssl req -new -key server.key -out server.csr \
-subj "/C=BR/ST=SP/L=SaoPaulo/O=EmpresaBeta/OU=TI/CN=localhost"

openssl x509 -req -in server.csr -CA ca.crt -CAkey ca.key -CAcreateserial \
-out server.crt -days 1825 -sha256
```

Client Certificate

```bash
openssl genrsa -out client.key 2048
openssl req -new -key client.key -out client.csr \
-subj "/C=BR/ST=SP/L=SaoPaulo/O=EmpresaBeta/OU=TI/CN=clienteCamila"

openssl x509 -req -in client.csr -CA ca.crt -CAkey ca.key -CAcreateserial \
-out client.crt -days 1825 -sha256
```

Configure Mosquitto (mTLS)

```bash
Edit config:

sudo nano /etc/mosquitto/conf.d/ssl.conf
listener 8883
protocol mqtt
cafile /etc/mosquitto/certs/ca.crt
certfile /etc/mosquitto/certs/server.crt
keyfile /etc/mosquitto/certs/server.key
require_certificate true
use_identity_as_username true
allow_anonymous false
```

Restart broker:

```bash
sudo systemctl restart mosquitto
```


## 1.4 Publisher



```bash
x
```
