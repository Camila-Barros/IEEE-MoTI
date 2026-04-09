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

Create and activate virtual environment:

```bash
python3 -m venv venv
source venv/bin/activate
```

Install required libraries:

```bash
pip install paho-mqtt requests
```

## 1.2 MQTT Mosquitto Certificates

Create directory for certificates:

```bash
sudo mkdir -p /etc/mosquitto/certs
sudo cp server.crt server.key ca.crt /etc/mosquitto/certs/
```

Generate authority certificate (CA)

```bash
openssl genrsa -out ca.key 2048
openssl req -x509 -new -nodes -key ca.key -sha256 -days 3650 -out ca.crt \
-subj "/C=BR/ST=SP/L=SaoPaulo/O=EmpresaBeta/OU=TI/CN=EmpresaBetaRootCA"
```

Generate server certificate

```bash
openssl genrsa -out server.key 2048
openssl req -new -key server.key -out server.csr \
-subj "/C=BR/ST=SP/L=SaoPaulo/O=EmpresaBeta/OU=TI/CN=localhost"
openssl x509 -req -in server.csr -CA ca.crt -CAkey ca.key -CAcreateserial \
-out server.crt -days 1825 -sha256
```

Generate client certificate

```bash
openssl genrsa -out client.key 2048
openssl req -new -key client.key -out client.csr \
-subj "/C=BR/ST=SP/L=SaoPaulo/O=EmpresaBeta/OU=TI/CN=clienteCamila"
openssl x509 -req -in client.csr -CA ca.crt -CAkey ca.key -CAcreateserial \
-out client.crt -days 1825 -sha256
```

Configure Mosquitto (mTLS) Edit:

```bash
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

## 1.3 Local TLS Certificates

Activate virtual environment:

```bash
source venv/bin/activate
```

Create a directory within the project for the certificates with an absolute path:

```bash
mkdir ~/Documentos/MoTI/mqtt_tls_certs
```

Copy the certificates to the created directory:

```bash
sudo cp /etc/mosquitto/certs/*.crt ~/Documentos/MoTI/mqtt_tls_certs/
sudo cp /etc/mosquitto/certs/server.key ~/Documentos/MoTI/mqtt_tls_certs/
```

Grant read permission to the certificates:

```bash
sudo chmod 644 ~/Documentos/MoTI/mqtt_tls_certs/* 
```


## 1.4 Publisher

Run:

```bash
python publish_to_mosquitto.py
```

Or configure as a service:

```bash
sudo nano /etc/systemd/system/moti-publisher.service
```

Service:

```bash
[Unit]
Description=MoTI MQTT Publisher Service
After=network.target

[Service]
Type=simple
User=camila
WorkingDirectory=/home/camila/Documentos/MoTI
ExecStart=/home/camila/MoTI/producer/venv/bin/python publish_to_mosquitto.py
Restart=on-failure
RestartSec=5s
SyslogIdentifier=moti-publisher

[Install]
WantedBy=multi-user.target
```



## 1.5 Subscriber 

Run:

```bash
python subscribe_to_ipfs.py
```


Or configure as service:

```bash
sudo nano /etc/systemd/system/moti-subscriber.service
```

Service:

```bash
[Unit]
Description=MoTI MQTT→IPFS Subscriber Service
After=network.target

[Service]
Type=simple
User=camila
WorkingDirectory=/home/camila/Documentos/MoTI
ExecStart=/home/camila/MoTI/producer/venv/bin/python subscribe_to_ipfs.py
Restart=on-failure
RestartSec=5s
SyslogIdentifier=moti-subscriber

[Install]
WantedBy=multi-user.target
```

# 2. Remote Environment (IPFS Node on AWS)

## 2.1 EC2 Instance in AWS

Access the EC2 Console at https://aws.amazon.com/pt/console/ and create an instance. Then create a new SSH key pair, type RSA, and save it in “.pem” format.

Configure the network (firewall), creating a security group for remote access to the IPFS node, and editing the security rules, considering the ports and IPs:

```bash
Port 22 → SSH
Port 8443 → HTTPS (mTLS for secure IPFS access via Nginx)
Port 4001 → IPFS P2P
Port 5001 → IPFS API
```

Click on “Start Instance” and wait for the instance to appear as “Running”.

## 2.2 EC2 instance (VM) via SSH

Move the previously saved “.pem” file to a secure folder.

```bash
mkdir -p ~/aws-keys
mv ~/Downloads/ipfs-key.pem ~/aws-keys/
```

Adjust the key permissions, as SSH requires the key to have restricted permissions:

```bash
chmod 400 ~/aws-keys/ipfs-key.pem
```

Connect to and access the EC2 instance via SSH:

```bash
#Replace with the name of the SSH key file (.pem)
#Replace xxx with the IPv4 address of the instance

ssh -i ~/aws-keys/seuarquivo.pem ubuntu@54.xxx.xxx.xxx 
```

Update the system:

```bash
sudo apt update && sudo apt upgrade -y 
```

Install the basic dependencies:

```bash
sudo apt install curl wget tar -y 
```

Download and install the Go-IPFS daemon (IPFS Server) on the EC2 virtual machine (VM):

```bash
wget https://dist.ipfs.tech/go-ipfs/v0.24.0/go-ipfs_v0.24.0_linux-amd64.tar.gz
tar -xvzf go-ipfs_v0.24.0_linux-amd64.tar.gz
cd go-ipfs
sudo bash install.sh 
```

Verify the installation:

```bash
ipfs --version 
```

Initialize IPFS. This command creates the basic directory structure and IPFS settings for the Ubuntu user:

```bash
ipfs init 
```

Run the IPFS daemon and configure it to start automatically:

```bash
ipfs daemon &
```

Install Nginx on the EC2 server (protects the gateway with an authenticated reverse proxy):

```bash
sudo apt update && sudo apt install nginx
```

Create the directory to store the IPFS digital certificates:

```bash
sudo mkdir -p /etc/nginx/certs
```

Open the configuration file of Nginx:

```bash
sudo nano /etc/nginx/sites-available/ipfs.conf
```

Edit the configuration file:

```bash
server {
    listen 8443 ssl;
    server_name _;
    # Serve certs
    ssl_certificate      /etc/nginx/certs/nginx-server.crt;
    ssl_certificate_key  /etc/nginx/certs/nginx-server.key;

    # CA que verifica clientes
    ssl_client_certificate /etc/nginx/certs/nginx-ca.crt;
    ssl_verify_client    on;

    # Proxy para API do IPFS
    location / {
        proxy_pass http://127.0.0.1:5001;
        proxy_set_header Host $host;
    }
    
    # Expor o arquivo data.jsonl
    location /data.jsonl {
        alias /var/www/ipfs_data/data.jsonl;
       # add_header Content-Type text/plain;
    }

    # Expor o índice de CIDs via HTTPS+mTLS
    location /moti/data.jsonl {
        # Aponta diretamente para o arquivo fora da raiz web
        alias /var/www/ipfs_data/data.jsonl;
        # Conteúdo como JSON (sugestão)
        default_type application/json;
        # Evita cache para ver os novos registros sempre
        add_header Cache-Control "no-store";
        # Opcional: só permitir GET/HEAD
        limit_except GET HEAD { deny all; }
    }

    # Bloco de proxy da API no Nginx (na EC2)
    location /api/v0/ {
        proxy_pass http://127.0.0.1:5001/;
        proxy_http_version 1.1;
        proxy_set_header Host              $host;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Connection        "";
        client_max_body_size    0;
        proxy_request_buffering off;
        proxy_read_timeout  600s;
        proxy_send_timeout  600s;
    }
}
```

Activate Nginx:

```bash
sudo ln -s /etc/nginx/sites-available/ipfs.conf /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

Prepare the log file:

```bash
sudo mkdir -p /var/www/ipfs_data
sudo touch /var/www/ipfs_data/data.jsonl
sudo chown www-data:www-data /var/www/ipfs_data/data.jsonl
```

Adjust remote file permissions:

```bash
sudo chown ubuntu:www-data /var/www/ipfs_data/data.jsonl
sudo chmod 664 /var/www/ipfs_data/data.jsonl
sudo chmod 755 /var/www/ipfs_data
```

Create the service \verb|ipfs.service| (user mode) for IPFS, so IPFS starts automatically:

```bash
mkdir -p ~/.config/systemd/user
cat > ~/.config/systemd/user/ipfs.service <<'EOF'
```

Paste into the editor:

```bash
[Unit]
Description=IPFS daemon (user)
After=network-online.target

[Service]
ExecStart=/usr/local/bin/ipfs daemon --enable-pubsub-experiment
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
EOF

# Permitir serviços de usuário persistirem após logout
sudo loginctl enable-linger ubuntu

# Carregar/ativar o serviço
systemctl --user daemon-reload
systemctl --user enable --now ipfs

# Ver status
systemctl --user status ipfs --no-pager
```

## 2.3 TLS Nginx Certificates

Generate digital certificates for TLS security using OpenSSL to generate certificates that will be used in MQTT and IPFS communication:

```bash
openssl req -newkey rsa:2048 -nodes -keyout client.key -x509 -days 365 -out client.crt
```

Transfer certificates from the EC2 server to the local network device (local environment):

```bash
scp -i ~/aws-keys/ipfs-key.pem ubuntu@IP_DA_EC2:/etc/nginx/certs/nginx-client.* ~/Documentos/MoTI/mqtt_tls_certs/
```

# 3. Remote User (Data Access)

## 3.1 Environment Setup

Update the Ubuntu operating system repositories and packages before starting the installation, ensuring that all components are the latest version:

```bash
sudo apt update && sudo apt upgrade -y
```

Install system dependencies. These tools are essential for secure communication via MQTT and the use of IPFS:

```bash
sudo apt install -y python3 python3-venv python3-pip mosquitto mosquitto-clients openssl curl
```

Install the Python libraries:

```bash
pip install paho-mqtt requests
```

Create a virtual environment (venv) and install the necessary packages within it.

```bash
python3 -m venv .venv 
source venv/bin/activate 
pip install -U pip requests
```


## 3.2 Mosquitto and Nginx TLS Certificates

Create a directory within the user's project for the certificates with an absolute path:

```bash
mkdir -p ~/Projetos/moti-viewer/certs
```

Copy the same certificates created previously to the certs/ folder:

```bash
# TLS MQTT Mosquitto Certificates:
ca.crt
client.crt
client.key

# TLS Nginx/IPFS Certificates:
nginx-ca.crt
nginx-client.crt
nginx-client.key
```

To ensure the certificates can be accessed without problems, read permissions must be granted:

```bash
cd ~/Projetos/moti-viewer/certs
chmod 600 client.key nginx-client.key
chmod 644 ca.crt client.crt nginx-ca.crt nginx-client.crt
```


## 3.3 Viewer

In the project directory, create the file `viewer_csv_from_index.py` in Python, responsible for periodically reading the file `data.jsonl` via HTTPS+mTLS, generating the corresponding CSV, and automatically saving the result in the `exports` directory. 

Create the `moti-viewer` service to start automatically on boot and restart if it fails:

```bash
mkdir -p ~/.config/systemd/user
nano ~/.config/systemd/user/moti-viewer.service
```

Paste into the editor:

```bash
[Unit]
Description=MoTI Viewer (CSV from data.jsonl)
After=network-online.target

[Service]
WorkingDirectory=/home/mila/Projetos/moti-viewer
ExecStart=/home/mila/Projetos/moti-viewer/.venv/bin/python /home/mila/Projetos/moti-viewer/viewer_csv_from_index.py
Restart=on-failure
RestartSec=5
# Variáveis
Environment=DATA_URL=https://<EC2_PUBLIC_IP>:8443/moti/data.jsonl
Environment=INTERVAL=10

[Install]
WantedBy=default.target
```

Activate and start the service:

```bash
systemctl --user daemon-reload
systemctl --user enable --now moti-viewer.service
systemctl --user status moti-viewer.service –no-pager
```

---

# Final Workflow

1. Publisher sends MQTT messages
2. Subscriber receives and processes data
3. Data is stored in IPFS
4. Metadata is recorded in data.jsonl
5. Remote users access data securely via HTTPS + mTLS

---

# Reproducibility Notes

- Certificates must be generated locally
- Network conditions may affect performance
- AWS infrastructure is required for full replication
