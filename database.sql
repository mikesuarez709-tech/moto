-- Import into an existing UTF-8 MySQL 8.0.16+ database (default: motor_shop_db).
CREATE TABLE IF NOT EXISTS customers (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(120) NOT NULL,
    phone VARCHAR(40) NOT NULL,
    address VARCHAR(255) NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS motorcycles (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    customer_id BIGINT UNSIGNED NOT NULL,
    brand VARCHAR(80) NOT NULL,
    model VARCHAR(80) NOT NULL,
    plate VARCHAR(30) UNIQUE,
    engine_number VARCHAR(80) NOT NULL UNIQUE,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (customer_id) REFERENCES customers(id),
    INDEX (brand, model)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS mechanics (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(120) NOT NULL,
    phone VARCHAR(40) NOT NULL,
    available BOOLEAN NOT NULL DEFAULT TRUE,
    INDEX (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS users (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(120) NOT NULL,
    username VARCHAR(80) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role ENUM('admin','cashier','mechanic') NOT NULL,
    mechanic_id BIGINT UNSIGNED UNIQUE,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    session_version INT UNSIGNED NOT NULL DEFAULT 1,
    failed_attempts INT UNSIGNED NOT NULL DEFAULT 0,
    locked_until DATETIME,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (mechanic_id) REFERENCES mechanics(id),
    CHECK ((role = 'mechanic') = (mechanic_id IS NOT NULL))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS customer_accounts (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    customer_id BIGINT UNSIGNED NOT NULL UNIQUE,
    username VARCHAR(80) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    session_version INT UNSIGNED NOT NULL DEFAULT 1,
    failed_attempts INT UNSIGNED NOT NULL DEFAULT 0,
    locked_until DATETIME,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (customer_id) REFERENCES customers(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS categories (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(90) NOT NULL UNIQUE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS products (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    category_id BIGINT UNSIGNED NOT NULL,
    sku VARCHAR(40) NOT NULL UNIQUE,
    name VARCHAR(120) NOT NULL,
    brand VARCHAR(80),
    description VARCHAR(1000),
    image_url VARCHAR(500),
    price DECIMAL(12,2) NOT NULL CHECK (price >= 0),
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (category_id) REFERENCES categories(id),
    INDEX (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS inventory (
    product_id BIGINT UNSIGNED PRIMARY KEY,
    quantity INT UNSIGNED NOT NULL DEFAULT 0,
    minimum INT UNSIGNED NOT NULL DEFAULT 5,
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS services (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    request_key CHAR(32) NOT NULL UNIQUE,
    customer_id BIGINT UNSIGNED NOT NULL,
    motorcycle_id BIGINT UNSIGNED NOT NULL,
    mechanic_id BIGINT UNSIGNED NOT NULL,
    service_type VARCHAR(100) NOT NULL,
    description VARCHAR(2000) NOT NULL,
    labor DECIMAL(12,2) NOT NULL CHECK (labor >= 0),
    status ENUM('Pending','In Progress','Completed','Cancelled') NOT NULL DEFAULT 'Pending',
    created_by BIGINT UNSIGNED NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    completed_at DATETIME,
    FOREIGN KEY (customer_id) REFERENCES customers(id),
    FOREIGN KEY (motorcycle_id) REFERENCES motorcycles(id),
    FOREIGN KEY (mechanic_id) REFERENCES mechanics(id),
    FOREIGN KEY (created_by) REFERENCES users(id),
    INDEX (created_at),
    INDEX (status, updated_at),
    INDEX (mechanic_id, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS service_requests (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    request_key CHAR(32) NOT NULL UNIQUE,
    customer_id BIGINT UNSIGNED NOT NULL,
    motorcycle_id BIGINT UNSIGNED NOT NULL,
    service_type VARCHAR(100) NOT NULL,
    description VARCHAR(2000) NOT NULL,
    status ENUM('Pending','Reviewed','Declined') NOT NULL DEFAULT 'Pending',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (customer_id) REFERENCES customers(id),
    FOREIGN KEY (motorcycle_id) REFERENCES motorcycles(id),
    INDEX (status, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS service_details (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    request_key CHAR(32) NOT NULL UNIQUE,
    service_id BIGINT UNSIGNED NOT NULL,
    product_id BIGINT UNSIGNED NOT NULL,
    product_name VARCHAR(120) NOT NULL,
    quantity INT UNSIGNED NOT NULL CHECK (quantity > 0),
    unit_price DECIMAL(12,2) NOT NULL CHECK (unit_price >= 0),
    returned_at DATETIME,
    FOREIGN KEY (service_id) REFERENCES services(id),
    FOREIGN KEY (product_id) REFERENCES products(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS transactions (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    request_key CHAR(32) NOT NULL UNIQUE,
    customer_id BIGINT UNSIGNED,
    created_by BIGINT UNSIGNED NOT NULL,
    total DECIMAL(14,2) NOT NULL CHECK (total > 0),
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (customer_id) REFERENCES customers(id),
    FOREIGN KEY (created_by) REFERENCES users(id),
    INDEX (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS transaction_items (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    transaction_id BIGINT UNSIGNED NOT NULL,
    product_id BIGINT UNSIGNED NOT NULL,
    product_name VARCHAR(120) NOT NULL,
    quantity INT UNSIGNED NOT NULL CHECK (quantity > 0),
    unit_price DECIMAL(12,2) NOT NULL CHECK (unit_price >= 0),
    FOREIGN KEY (transaction_id) REFERENCES transactions(id),
    FOREIGN KEY (product_id) REFERENCES products(id),
    UNIQUE (transaction_id, product_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS stock_movements (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    product_id BIGINT UNSIGNED NOT NULL,
    user_id BIGINT UNSIGNED NOT NULL,
    quantity_delta INT NOT NULL CHECK (quantity_delta <> 0),
    balance INT UNSIGNED NOT NULL,
    reason VARCHAR(180) NOT NULL,
    transaction_id BIGINT UNSIGNED,
    service_id BIGINT UNSIGNED,
    request_key CHAR(32) UNIQUE,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (product_id) REFERENCES products(id),
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (transaction_id) REFERENCES transactions(id),
    FOREIGN KEY (service_id) REFERENCES services(id),
    INDEX (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- One row per actual payment so installments can be audited separately.
CREATE TABLE IF NOT EXISTS payments (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    request_key CHAR(32) NOT NULL UNIQUE,
    transaction_id BIGINT UNSIGNED,
    service_id BIGINT UNSIGNED,
    user_id BIGINT UNSIGNED NOT NULL,
    method ENUM('Cash','GCash','Bank Transfer') NOT NULL,
    amount DECIMAL(14,2) NOT NULL CHECK (amount > 0),
    reference VARCHAR(100),
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (transaction_id) REFERENCES transactions(id),
    FOREIGN KEY (service_id) REFERENCES services(id),
    FOREIGN KEY (user_id) REFERENCES users(id),
    CHECK ((transaction_id IS NULL) <> (service_id IS NULL)),
    UNIQUE (transaction_id, method, reference),
    UNIQUE (service_id, method, reference),
    INDEX (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
