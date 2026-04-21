# 🔥 GasBook

<div align="center">

![GasBook Banner](https://capsule-render.vercel.app/api?type=waving&color=gradient&customColorList=12,20,24&height=220&section=header&text=GasBook&fontSize=80&fontColor=ffffff&animation=fadeIn&fontAlignY=38&desc=Modern%20LPG%20Cylinder%20Management%20System&descAlignY=60&descSize=18)

<p align="center">
  <em>A sleek, full-stack platform to streamline LPG distribution — from booking to doorstep delivery.</em>
</p>

<p align="center">
  <a href="https://gas.nithishkps.workers.dev">
    <img src="https://img.shields.io/badge/LIVE_DEMO-2ED573?style=plastic&logoColor=white&logo=rocket" width = "120" alt="Live Demo">
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

<table style="background-color: #ffffff; border-radius: 12px; padding: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
<tr>
<td width="50%" valign="top" style="background-color: #ffffff; padding: 20px; border-radius: 8px;">

### 🎨 **Modern Interface**
<span style="background-color: #f0f0f0; padding: 10px; border-radius: 5px; display: block;">
- Gemini-inspired clean layout
- Fluid **Day / Night** theme toggle
- Collapsible 3-dot sidebar
- Top-right profile dropdown
- Fully responsive across devices
- CSS variable-driven theming
</span>

### 👥 **Customer Management**
<span style="background-color: #f0f0f0; padding: 10px; border-radius: 5px; display: block;">
- Full CRUD with live validation
- Auto-generated customer IDs
- Loyalty tracking (bookings & spend)
- Search by name, phone, or ID
- Click-to-view detail modal
</span>

</td>
<td width="50%" valign="top" style="background-color: #ffffff; padding: 20px; border-radius: 8px;">

### 📦 **Booking & Delivery**
<span style="background-color: #f0f0f0; padding: 10px; border-radius: 5px; display: block;">
- Create cylinder orders in seconds
- Assign delivery personnel
- Status pipeline: `Pending → Confirmed → Out → Delivered`
- Auto-calculated pricing
- **PDF Invoice** download & print
</span>

### 📊 **Smart Analytics**
<span style="background-color: #f0f0f0; padding: 10px; border-radius: 5px; display: block;">
- Real-time dashboard metrics
- Monthly revenue trends
- Low-stock warnings
- 1-click inventory restock
- Interactive sortable tables
</span>

</td>
</tr>
</table>

---

## 🛠️ Tech Stack

<div align="center" style="background-color: #ffffff; padding: 25px; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">

<table style="background-color: #ffffff;">
<tr style="background-color: #f9f9f9;">

| Layer        | Technology                                                   |
| :----------- | :----------------------------------------------------------- |
| **Frontend** | HTML5 · CSS3 (Custom Design System) · Vanilla JavaScript     |
| **Backend**  | Python 3.11 · Flask · Flask-CORS                             |
| **Database** | MySQL 8.0                                                    |
| **DevOps**   | Docker · Docker Compose · Gunicorn-ready                     |
| **Extras**   | jsPDF · html2canvas · python-dotenv                          |

</tr>
</table>

</div>

---

## 🚀 Quick Start

<div align="center" style="background-color: #ffffff; padding: 25px; border-radius: 12px; margin: 20px 0; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">

GasBook can run in **three flexible ways** — pick what suits your environment.

<div style="background-color: #f9f9f9; padding: 15px; border-radius: 8px; display: inline-block;">

| Method | Best For | Setup Time |
| :----- | :------- | :--------: |
| 🐳 **Docker Compose** | Production / Quick demo | ~30 sec |
| 🧱 **Manual Docker** | Custom port / DB control | ~2 min |
| 🐍 **Local Python** | Active development | ~5 min |

</div>

</div>

---

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

**Useful commands:**

```bash
docker-compose logs -f app      # Live app logs
docker-compose logs -f db       # MySQL logs
docker-compose ps               # List running containers
docker-compose down             # Stop & remove containers
docker-compose down -v          # Stop + wipe DB volume
docker-compose restart app      # Restart only the app
```

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

<div align="center">

<details>
<summary><b>🚀 Click to expand all routes</b></summary>

```
╔══════════════════════════════════════════════════════════╗
║            🔌 COMPLETE REST API REFERENCE                ║
╠══════════════════════════════════════════════════════════╣
║ AUTH ENDPOINTS                                           ║
├─ POST   /api/login               → Authenticate         ║
├─ POST   /api/register            → Create Account       ║
├─ POST   /api/logout              → End Session          ║
║                                                          ║
║ PROFILE ENDPOINTS                                        ║
├─ GET    /api/profile             → Fetch Profile        ║
├─ PUT    /api/profile             → Update Profile       ║
║                                                          ║
║ CUSTOMER MANAGEMENT                                      ║
├─ GET    /api/customers           → List All             ║
├─ POST   /api/customers           → Create New           ║
├─ PUT    /api/customers/<id>      → Update               ║
├─ DELETE /api/customers/<id>      → Delete               ║
║                                                          ║
║ BOOKING SYSTEM                                           ║
├─ GET    /api/bookings            → View All             ║
├─ POST   /api/bookings            → Create Order         ║
├─ PUT    /api/bookings/<id>/status → Update Status       ║
║                                                          ║
║ INVENTORY & ANALYTICS                                    ║
├─ GET    /api/inventory           → Stock Levels         ║
├─ POST   /api/inventory/restock   → Add Stock            ║
├─ GET    /api/analytics/dashboard → Metrics              ║
├─ GET    /api/health              → Server Status        ║
╚══════════════════════════════════════════════════════════╝
```

</details>

</div>

---

## 🧠 Self-Healing Database

```
GasBook automatically:
  ✓ Verifies database schema on startup
  ✓ Creates tables if missing via init.sql
  ✓ Migrates legacy database structures
  ✓ Relinks orphaned user records
  ✓ Maintains data integrity

→ Result: Zero manual database setup needed!
```

---

## 🤝 Contributing

<div align="center">

```bash
# 🔗 Fork → Clone → Create Branch

git checkout -b feature/amazing-feature
git commit -m "✨ Add amazing feature"
git push origin feature/amazing-feature

# → Open Pull Request
```

[🐛 Found a bug?](https://github.com/NITHISHKUMAR006/Gas-Booking-System/issues)

</div>

---

## 📄 License

<div align="center">

```
MIT License © 2025

Free to use, modify, and distribute!
```

</div>

---

<div align="center">

### 🌟 Show your support by starring this repo!

```
╔════════════════════════════════════════════════════════╗
║  Built with 🔥 by NITHISHKUMAR006                     ║
║  Powered by: Python · Flask · MySQL · Docker          ║
╚════════════════════════════════════════════════════════╝
```

![Footer](https://capsule-render.vercel.app/api?type=waving&color=gradient&customColorList=12,20,24&height=100&section=footer)

</div>
