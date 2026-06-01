# Free Deployment Guide: Oracle Cloud Always Free Tier

Oracle Cloud provides an "Always Free" tier that includes an ARM Ampere A1 Compute instance with up to 4 vCPUs and 24 GB of RAM. This is incredibly generous and the absolute best way to run your entire `docker-compose.yml` stack (API, Engine, Frontend, Scanner, and Postgres) for $0/month.

Here is the step-by-step guide to get your trading app live.

## Step 1: Sign up for Oracle Cloud

1. Go to the [Oracle Cloud Free Tier sign-up page](https://www.oracle.com/cloud/free/).
2. Fill out your details. _Note: They will ask for a credit card to verify your identity and prevent bot signups. They will charge a small temporary authorization fee (like $1) and immediately refund it. You will **never** be charged for Always Free resources._
3. Select your "Home Region" (pick the one closest to you or your crypto exchanges for lowest latency).

## Step 2: Create the Server (Compute Instance)

1. Once logged into the Oracle Cloud Console, click **Create a VM instance**.
2. **Name:** `smart-trading-server`
3. **Image and Shape:**
   - Click **Edit**.
   - **Image:** Change to **Ubuntu 22.04** or **Ubuntu 24.04**.
   - **Shape:** Click Change Shape -> Virtual Machine -> **Ampere** -> select `VM.Standard.A1.Flex`.
   - Check the box to adjust the slider: give it **2 vCPUs** and **12 GB RAM** (or max it out at 4 vCPUs / 24 GB RAM if you want). _Make sure it says "Always Free Eligible" next to the shape._
4. **Networking:** Leave the default Virtual Cloud Network (VCN) settings.
5. **Add SSH Keys:**
   - Select **Save Private Key** and **Save Public Key**. _Download these! You need the private key to connect to your server._
6. **Boot Volume:** Leave as default (50GB is free and more than enough).
7. Click **Create** at the bottom. Wait a minute or two until the big square turns from "Provisioning" to "Running", and note your **Public IP Address**.

## Step 3: Connect to your Server

Open your terminal (on your local machine) and connect to the server using the private key you downloaded.

```bash
# First, change the permissions of the key file you downloaded so it's secure
chmod 400 ~/Downloads/ssh-key-202X-XX-XX.key

# Connect via SSH (replace with your downloaded key name and your Public IP)
ssh -i ~/Downloads/ssh-key-202X-XX-XX.key ubuntu@<YOUR_PUBLIC_IP>
```

## Step 4: Install Docker and Git

Once you are logged into your Oracle Ubuntu server, run these commands to install the required tools:

```bash
# Update the system
sudo apt update && sudo apt upgrade -y

# Install Git
sudo apt install git -y

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Add your user to the docker group so you don't have to use 'sudo' every time
sudo usermod -aG docker $USER

# Activate the new group (or log out and log back in)
newgrp docker
```

## Step 5: Clone your Repository and Deploy

Now, clone your code onto the server and start it up!

```bash
# Clone your private repo (you may need to set up a GitHub Personal Access Token or SSH key on the server to clone a private repo)
git clone <YOUR_GITHUB_REPO_URL>
cd smart-trading

# Since you are on a fresh server, create a .env file if your app needs one, or ensure environment variables in docker-compose.yml are correct.
# Note: In docker-compose.yml you hardcoded the telegram tokens, which is fine for testing, but ideally these go in a .env file later!

# Start everything in the background!
docker compose up -d --build
```

> [!NOTE]
> Building the Docker images might take 5-10 minutes the first time because it has to install all the Node.js and Python dependencies.

You can verify everything is running by typing: `docker ps`

## Step 6: Open the Firewalls (Crucial Step!)

By default, Oracle Cloud blocks all incoming traffic to your server. You need to open the ports for your Frontend (`5173`) and API (`3000`).

### Open Ports in Oracle Cloud Dashboard:

1. In the Oracle Dashboard, go to your instance details.
2. Click on the attached **Subnet** link (it will look like `subnet-xxxx`).
3. Click on the **Security List** (e.g., `Default Security List for vcn-xxxx`).
4. Click **Add Ingress Rules**.
5. Add a rule:
   - Source CIDR: `0.0.0.0/0`
   - IP Protocol: `TCP`
   - Destination Port Range: `3000,5173,8000`
   - Click Add.

### Open Ports in Ubuntu Firewall (Iptables):

Run these commands on your SSH terminal to tell the Ubuntu firewall to allow the traffic:

```bash
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 3000 -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 5173 -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 8000 -j ACCEPT
sudo netfilter-persistent save
```

## Step 7: Access Your App!

You should now be able to go to your browser and access:

- **Frontend:** `http://<YOUR_PUBLIC_IP>:5173`
- **API:** `http://<YOUR_PUBLIC_IP>:3000`

> [!TIP]
> If you decide to map a custom domain name later (like `app.yourtradingbot.com`), you can set up a free Cloudflare account, point it to your Oracle Public IP, and run a reverse proxy like `Nginx Proxy Manager` or `Caddy` in Docker to handle HTTPS/SSL certificates automatically!
