-- PostgreSQL / SQLite schema for CRM actions persistence verification

CREATE TABLE IF NOT EXISTS customers (
    customer_id VARCHAR(64) PRIMARY KEY,
    name VARCHAR(128),
    phone_number VARCHAR(32),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS customer_tags (
    id SERIAL PRIMARY KEY,
    customer_id VARCHAR(64) NOT NULL,
    tag VARCHAR(64) NOT NULL,
    reason TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
);

CREATE TABLE IF NOT EXISTS call_notes (
    id SERIAL PRIMARY KEY,
    call_id VARCHAR(64) NOT NULL,
    customer_id VARCHAR(64),
    summary TEXT NOT NULL,
    action_items TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS scheduled_callbacks (
    id SERIAL PRIMARY KEY,
    customer_id VARCHAR(64) NOT NULL,
    phone_number VARCHAR(32) NOT NULL,
    scheduled_time VARCHAR(64) NOT NULL,
    status VARCHAR(32) DEFAULT 'PENDING',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
