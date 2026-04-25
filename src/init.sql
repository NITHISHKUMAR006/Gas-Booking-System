-- ─────────────────────────────────────────────────────────────────────────────
--  Gas Booking System  |  init.sql
--  Auto-executed by MySQL Docker container on first start
--  Creates schema + seed data for gasbook database
-- ─────────────────────────────────────────────────────────────────────────────

CREATE DATABASE IF NOT EXISTS `gasbook` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE `gasbook`;

-- ── Users ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    user_id     INT          AUTO_INCREMENT PRIMARY KEY,
    username    VARCHAR(50)  NOT NULL UNIQUE,
    password    VARCHAR(255) NOT NULL,
    role        ENUM('admin','staff','customer') NOT NULL DEFAULT 'staff',
    status      ENUM('active','inactive') NOT NULL DEFAULT 'active',
    customer_id VARCHAR(20)  NULL,
    created_at  TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
);

-- Default Accounts
INSERT IGNORE INTO users (username, password, role, customer_id) VALUES
    ('admin',    'admin123',    'admin',    NULL),
    ('staff',    'staff123',    'staff',    NULL),
    ('customer', 'customer123', 'customer', 'CUST0001');

-- ── cylinder_types ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS cylinder_types (
    type_id   INT          AUTO_INCREMENT PRIMARY KEY,
    type_name VARCHAR(100) NOT NULL,
    weight    DECIMAL(5,2) NOT NULL,
    price     DECIMAL(10,2) NOT NULL,
    is_active TINYINT(1)  DEFAULT 1
);

INSERT IGNORE INTO cylinder_types (type_name, weight, price) VALUES
    ('14.2 kg Domestic', 14.2, 903.00),
    ('19 kg Commercial', 19.0, 1850.00),
    ('5 kg FTL',          5.0,  500.00);

-- ── ware_houses ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ware_houses (
    warehouse_id INT         AUTO_INCREMENT PRIMARY KEY,
    name         VARCHAR(100) NOT NULL,
    location     VARCHAR(255),
    capacity     INT DEFAULT 1000
);

INSERT IGNORE INTO ware_houses (name, location) VALUES
    ('Main Warehouse', 'Central Depot'),
    ('North Hub',      'North Zone');

-- ── Customers ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS customers (
    customer_id    VARCHAR(20)  PRIMARY KEY,
    name           VARCHAR(100),
    phone          VARCHAR(15),
    email          VARCHAR(100),
    address        TEXT,
    aadhar_no      VARCHAR(20),
    status         ENUM('active','inactive') DEFAULT 'active',
    source         ENUM('signup','admin') NOT NULL DEFAULT 'admin',
    customer_since TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    total_bookings INT DEFAULT 0,
    total_spent    DECIMAL(12,2) DEFAULT 0.00
);

-- Default Customer Profile
INSERT IGNORE INTO customers (customer_id, name, phone, email, address, source) VALUES
    ('CUST0001', 'Demo Customer', NULL, NULL, NULL, 'signup');


-- ── delivery_boys ───────────────────────────────────────────────────────────

-- ── delivery_boys ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS delivery_boys (
    boy_id  INT          AUTO_INCREMENT PRIMARY KEY,
    name    VARCHAR(100) NOT NULL,
    phone   VARCHAR(15),
    status  ENUM('active','inactive') DEFAULT 'active'
);

INSERT IGNORE INTO delivery_boys (name, phone) VALUES
    ('Ravi Kumar',  '9876500001'),
    ('Suresh Singh','9876500002');

-- ── Inventory ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS inventory (
    inventory_id     INT AUTO_INCREMENT PRIMARY KEY,
    type_id          INT NOT NULL,
    warehouse_id     INT NOT NULL,
    quantity_on_hand INT DEFAULT 0,
    reorder_level    INT DEFAULT 50,
    last_restocked   TIMESTAMP NULL,
    UNIQUE KEY uq_inv (type_id, warehouse_id),
    FOREIGN KEY (type_id)      REFERENCES cylinder_types(type_id),
    FOREIGN KEY (warehouse_id) REFERENCES ware_houses(warehouse_id)
);

INSERT IGNORE INTO inventory (type_id, warehouse_id, quantity_on_hand) VALUES
    (1, 1, 200), (2, 1, 100), (3, 1, 50),
    (1, 2, 150), (2, 2, 80);

-- ── Bookings ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS bookings (
    booking_id     VARCHAR(20)  PRIMARY KEY,
    customer_id    VARCHAR(20)  NOT NULL,
    type_id        INT          NOT NULL,
    quantity       INT DEFAULT 1,
    booking_date   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    delivery_date  DATE NULL,
    amount         DECIMAL(10,2) NOT NULL,
    status         ENUM('pending','confirmed','out_for_delivery','delivered','cancelled') DEFAULT 'pending',
    delivery_boy_id INT NULL,
    FOREIGN KEY (customer_id)    REFERENCES customers(customer_id),
    FOREIGN KEY (type_id)        REFERENCES cylinder_types(type_id),
    FOREIGN KEY (delivery_boy_id) REFERENCES delivery_boys(boy_id)
);

