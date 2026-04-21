# 🔥 GasBook

<div align="center">

<p align="center">
  <a href="https://github.com/NITHISHKUMAR006/Gas-Booking-System">
    <img src="https://capsule-render.vercel.app/api?type=waving&color=gradient&customColorList=12,20,24&height=220&section=header&text=GasBook&fontSize=80&fontColor=ffffff&animation=fadeIn&fontAlignY=38&desc=Modern%20LPG%20Cylinder%20Management%20System&descAlignY=60&descSize=18" />
  </a>
</p>

<p align="center">
  <em>A sleek, full-stack platform to streamline LPG distribution — from booking to doorstep delivery.</em>
</p>


<p align="center">
  <a href="https://gas.nithishkps.workers.dev">
    <img src="https://img.shields.io/badge/LIVE_DEMO-FF6B35?style=plastic&logoColor=white&logo=rocket" width = "120" alt="Live Demo">
  </a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11-3776AB?style=plastic&logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/Flask-2.3-FF6B6B?style=plastic&logo=flask&logoColor=white" />
  <img src="https://img.shields.io/badge/MySQL-8.0-845EC2?style=plastic&logo=mysql&logoColor=white" />
  <img src="https://img.shields.io/badge/Docker-Compose-1F77D2?style=plastic&logo=docker&logoColor=white" />
  <img src="https://img.shields.io/badge/License-MIT-00D9FF?style=plastic" />
</p>

</div>

---

## 🌐 Live Preview

> **Try it now →** **[gas.nithishkps.workers.dev](https://gas.nithishkps.workers.dev)**

<div align="center">

| Role  | Username | Password   |
| :---- | :------- | :--------- |
| 👑 Admin | `admin`  | `admin123` |
| 👔 Staff | `staff`  | `staff123` |
| 👤 Member | _sign up yourself_ | _sign up yourself_ |

</div>

---

## ✨ Features

<div align="center">

<table>
<tr>
<td width="50%" valign="top">

### 🎨 **Modern Interface**
- Gemini-inspired clean layout
- Fluid **Day / Night** theme toggle
- Collapsible 3-dot sidebar
- Top-right profile dropdown
- Fully responsive across devices
- CSS variable-driven theming

### 👥 **Customer Management**
- Full CRUD with live validation
- Auto-generated customer IDs
- Loyalty tracking (bookings & spend)
- Search by name, phone, or ID
- Click-to-view detail modal

</td>
<td width="50%" valign="top">

### 📦 **Booking & Delivery**
- Create cylinder orders in seconds
- Assign delivery personnel
- Status pipeline: `Pending → Confirmed → Out → Delivered`
- Auto-calculated pricing
- **PDF Invoice** download & print

### 📊 **Smart Analytics**
- Real-time dashboard metrics
- Monthly revenue trends
- Low-stock warnings
- 1-click inventory restock
- Interactive sortable tables

</td>
</tr>
</table>

</div>

---

## 🛠️ Tech Stack

<div align="center">

| Layer        | Technology                                                   |
| :----------- | :----------------------------------------------------------- |
| **Frontend** | HTML5 · CSS3 (Custom Design System) · Vanilla JavaScript     |
| **Backend**  | Python 3.11 · Flask · Flask-CORS                             |
| **Database** | MySQL 8.0                                                    |
| **DevOps**   | Docker · Docker Compose · Gunicorn-ready                     |
| **Extras**   | jsPDF · html2canvas · python-dotenv                          |

</div>

---

## ⚙️ Prerequisites & Installation

<details>
  <summary><strong>View All Installation  <kbd>Click Here</kbd></strong></summary>


Before you start, make sure you have the required tools installed. Choose your operating system below:

### 🐳 Install Docker & Docker Compose

<details>
<summary><b>🪟 Windows</b></summary>

#### Option 1: Docker Desktop (Recommended)
1. Download [Docker Desktop for Windows](https://www.docker.com/products/docker-desktop)
2. Run the installer and follow the setup wizard
3. Enable WSL 2 backend (recommended during installation)
4. Restart your computer
5. Open PowerShell and verify:
```bash
docker --version
docker-compose --version
```

#### Option 2: Manual Installation
```bash
# Using Chocolatey (if installed)
choco install docker-desktop docker-compose

# Verify installation
docker --version
docker-compose --version
```

</details>

<details>
<summary><b>🐧 Linux (Ubuntu/Debian)</b></summary>

#### Install Docker
```bash
# Update package manager
sudo apt-get update
sudo apt-get install -y apt-transport-https ca-certificates curl software-properties-common

# Add Docker repository
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo apt-key add -
sudo add-apt-repository "deb [arch=amd64] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable"

# Install Docker
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io

# Start Docker service
sudo systemctl start docker
sudo systemctl enable docker

# Add user to docker group (optional - avoid sudo)
sudo usermod -aG docker $USER
newgrp docker
```

#### Install Docker Compose
```bash
# Download Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/download/v2.20.0/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose

# Make it executable
sudo chmod +x /usr/local/bin/docker-compose

# Verify installation
docker-compose --version
```

</details>

<details>
<summary><b>🍎 macOS</b></summary>

#### Option 1: Docker Desktop (Recommended)
1. Download [Docker Desktop for Mac](https://www.docker.com/products/docker-desktop)
2. Open the `.dmg` file and drag Docker to Applications
3. Launch Docker from Applications
4. Open terminal and verify:
```bash
docker --version
docker-compose --version
```

#### Option 2: Using Homebrew
```bash
# Install Homebrew if not already installed
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install Docker & Docker Compose
brew install --cask docker
brew install docker-compose

# Verify
docker --version
docker-compose --version
```

</details>

### ✅ Verify Installation

After installing, run these commands in your terminal to confirm everything works:

```bash
# Check Docker version
docker --version
# Expected output: Docker version 20.10+

# Check Docker Compose version
docker-compose --version
# Expected output: Docker Compose version 2.0+
```

---

## 🚀 Quick Start

GasBook can run in **three flexible ways** — pick what suits your environment.

<div align="center">

| Method | Best For | Setup Time |
| :----- | :------- | :--------: |
| 🐳 **Docker Compose** | Production / Quick demo | ~30 sec |
| 🧱 **Manual Docker** | Custom port / DB control | ~2 min |
| 🐍 **Local Python** | Active development | ~5 min |

</div>

---

<details>
  
### 🐳 Option A — Docker Compose (Easiest)

Spin up the **full stack** (Flask app + MySQL) with a single command.

```bash
# 1. Clone the repository
git clone https://github.com/NITHISHKUMAR006/Gas-Booking-System gasbook
cd gasbook

# 2. Spin up all containers
docker-compose up --build -d

# 3. Open your browser
http://localhost:5002
```

> ✅ Auto-creates the database, seeds tables via `init.sql`, and starts Flask on **port 5002**.

<details>
<summary><b>Docker Compose - Useful commands:</b></summary>

```bash
docker-compose logs -f app      # Live app logs
docker-compose logs -f db       # MySQL logs
docker-compose ps               # List running containers
docker-compose down             # Stop & remove containers
docker-compose down -v          # Stop + wipe DB volume
docker-compose restart app      # Restart only the app
```
</details>

</details>
---

### 🧱 Option B — Manual Docker Build & Run

Prefer running containers manually without Compose? Follow these steps:

#### **Step 1 — Build the Docker image**

```bash
docker build -t gasbook:latest .
```

#### **Step 2 — Create a shared network**

```bash
docker network create gasbook_net
```

#### **Step 3 — Start the MySQL container**

```bash
docker run -d \
  --name gasbook_db \
  --network gasbook_net \
  -e MYSQL_ROOT_PASSWORD=rootpassword \
  -e MYSQL_DATABASE=gasbook \
  -e MYSQL_USER=gasbook_user \
  -e MYSQL_PASSWORD=gasbook_pass \
  -p 3306:3306 \
  -v gasbook_mysql_data:/var/lib/mysql \
  -v $(pwd)/src/init.sql:/docker-entrypoint-initdb.d/init.sql:ro \
  mysql:8.0
```

#### **Step 4 — Run the GasBook app container**

```bash
docker run -d \
  --name gasbook_app \
  --network gasbook_net \
  -e MYSQL_HOST=gasbook_db \
  -e MYSQL_PORT=3306 \
  -e MYSQL_USER=gasbook_user \
  -e MYSQL_PASSWORD=gasbook_pass \
  -e MYSQL_DATABASE=gasbook \
  -e FLASK_PORT=5002 \
  -p 5002:5002 \
  gasbook:latest
```

#### **Step 5 — Visit the app**

```
🌐  http://localhost:5002
```

<details>
<summary><b>🔧 Run on a custom port</b></summary>

Just remap the host port — the **container internal port stays `5002`**.

```bash
# Run GasBook on host port 8080 instead
docker run -d --name gasbook_app -p 8080:5002 gasbook:latest

# Access via → http://localhost:8080
```

</details>

<details>
<summary><b>🧹 Cleanup commands</b></summary>

```bash
docker stop gasbook_app gasbook_db
docker rm   gasbook_app gasbook_db
docker volume rm gasbook_mysql_data
docker network rm gasbook_net
docker rmi gasbook:latest
```

</details>

---

### 🐍 Option C — Local Machine (No Docker)

Run Flask **directly on your machine** — perfect for active development & debugging.

#### **Prerequisites**

- 🐍 Python **3.9+** ([download](https://python.org/downloads))
- 🗄️ MySQL Server **8.0+** ([download](https://dev.mysql.com/downloads/mysql/))
- 📦 `pip` package manager

#### **Step 1 — Clone & enter directory**

```bash
git clone https://github.com/NITHISHKUMAR006/Gas-Booking-System gasbook
cd gasbook
```

#### **Step 2 — Create a virtual environment _(recommended)_**

<details open>
<summary><b>🪟 Windows (PowerShell)</b></summary>

```powershell
python -m venv venv
venv\Scripts\activate
```
</details>

<details>
<summary><b>🐧 Linux / 🍎 macOS</b></summary>

```bash
python3 -m venv venv
source venv/bin/activate
```
</details>

#### **Step 3 — Install Python dependencies**

```bash
pip install -r requirements.txt
```

#### **Step 4 — Set up MySQL locally**

Open MySQL CLI and run:

```sql
CREATE DATABASE gasbook CHARACTER SET utf8mb4;
CREATE USER 'gasbook_user'@'localhost' IDENTIFIED BY 'gasbook_pass';
GRANT ALL PRIVILEGES ON gasbook.* TO 'gasbook_user'@'localhost';
FLUSH PRIVILEGES;
```

> 💡 GasBook will **auto-seed tables** on first run — no need to import `init.sql` manually.

#### **Step 5 — Update `config.env`**

Edit `config.env` and point to your **local** MySQL:

```env
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=gasbook_user
MYSQL_PASSWORD=gasbook_pass
MYSQL_DATABASE=gasbook
FLASK_PORT=5002
DEBUG=True
```

#### **Step 6 — Launch the app**

```bash
python app.py
```

You should see:

```
[INFO] =======================================================
[INFO]   GasBook Backend  |  http://localhost:5002
[INFO]   DB: localhost:3306/gasbook
[INFO] =======================================================
```

#### **Step 7 — Open the dashboard**

```
🌐  http://localhost:5002
```

<details>
<summary><b>🔧 Run on a custom port</b></summary>

Edit `config.env`:

```env
FLASK_PORT=8080
```

Or override via shell:

```bash
# Linux / macOS
FLASK_PORT=8080 python app.py

# Windows PowerShell
$env:FLASK_PORT=8080; python app.py
```

</details>
  
<details>
<summary><b>⚠️ Troubleshooting</b></summary>

| Issue | Fix |
| :---- | :-- |
| `Access denied for user` | Verify MySQL user/password in `config.env` |
| `Can't connect to MySQL` | Ensure MySQL service is running (`sudo service mysql start`) |
| `Port 5002 already in use` | Change `FLASK_PORT` in `config.env` |
| `ModuleNotFoundError` | Re-run `pip install -r requirements.txt` inside venv |

</details>
</details>

---

## 🔌 Port Reference

<div align="center">

| Service       | Internal Port | External (Host) Port | Purpose                |
| :------------ | :-----------: | :------------------: | :--------------------- |
| 🐍 Flask App  | `5002`        | `5002`               | Web UI + REST API      |
| 🗄️ MySQL DB   | `3306`        | `3306`               | Database access        |

</div>

> 💡 To avoid conflicts with existing services, change the **host port** in `docker-compose.yml`, the `-p` flag, or `config.env`.

---

## 📂 Project Structure

```text
📦 Gas-Booking-System/
├── 📁 src/
│   ├── 🌐 index.html          # Login + Signup page
│   ├── 📊 dashboard.html      # Main dashboard UI
│   └── 🗄️  init.sql            # Schema + seed data
├── 🐍 app.py                  # Flask API & routing
├── 🔐 config.env              # Environment variables
├── 🐳 docker-compose.yml      # Multi-container orchestration
├── 📦 Dockerfile              # Python image build
└── 📋 requirements.txt        # Python dependencies
```

---

## 🔌 API Endpoints

<details>
<summary><b>📚 View all routes</b></summary>

| Method  | Endpoint                        | Purpose                  |
| :------ | :------------------------------ | :----------------------- |
| `POST`  | `/api/login`                    | Authenticate user        |
| `POST`  | `/api/register`                 | Create customer account  |
| `POST`  | `/api/logout`                   | End session              |
| `GET`   | `/api/profile`                  | Fetch logged-in profile  |
| `PUT`   | `/api/profile`                  | Update profile           |
| `GET`   | `/api/customers`                | List customers           |
| `POST`  | `/api/customers`                | Add customer             |
| `PUT`   | `/api/customers/<id>`           | Update customer          |
| `DELETE`| `/api/customers/<id>`           | Delete customer          |
| `GET`   | `/api/bookings`                 | List bookings            |
| `POST`  | `/api/bookings`                 | Create booking           |
| `PUT`   | `/api/bookings/<id>/status`     | Update booking status    |
| `GET`   | `/api/inventory`                | View stock levels        |
| `POST`  | `/api/inventory/restock`        | Add stock                |
| `GET`   | `/api/analytics/dashboard`      | Dashboard metrics        |
| `GET`   | `/api/health`                   | Server health check      |

</details>

---

## 🧠 Self-Healing Database

GasBook ships with intelligent recovery logic. On every startup, `app.py`:

1. 🔍 Verifies the `users` table exists
2. 🔧 Auto-runs `init.sql` if tables are missing
3. 🔄 Migrates legacy schemas (adds `customer/member` role support, `customer_id` column)
4. 🔗 Relinks orphaned user-customer records

> **Result:** No manual DB setup required — even across container rebuilds.

---

## 🤝 Contributing

Contributions make open-source thrive! 🌱

```bash
# 1. Fork the repo
# 2. Create your feature branch
git checkout -b feature/amazing-feature

# 3. Commit your changes
git commit -m "✨ Add amazing feature"

# 4. Push & open a PR
git push origin feature/amazing-feature
```

Found a bug? [**Open an issue →**](https://github.com/NITHISHKUMAR006/Gas-Booking-System/issues)

---

## 📄 License

Released under the **MIT License** — free to use, modify, and distribute.

---

<div align="center">

### ⭐ If GasBook helped you, consider starring the repo!

<p align="center">Built with ❤️ by <b><a href="https://github.com/NITHISHKUMAR006">Nithishkumar S</a> 🔥</b></p>

<p align="center">Powered by Flask & MySQL</p>

<p align="center">
  <a href="#">
    <img src="https://capsule-render.vercel.app/api?type=waving&color=gradient&customColorList=12,20,24&height=100&section=footer" />
  </a>
</p>

</div>
