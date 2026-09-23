-- 1. Create new tables
CREATE TABLE IF NOT EXISTS user_passport_history (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    virtual_location JSON NOT NULL,
    activated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    active_until TIMESTAMP NULL,
    city VARCHAR(100),
    country VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS user_location_history (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    latitude DECIMAL(10, 8) NOT NULL,
    longitude DECIMAL(11, 8) NOT NULL,
    accuracy DECIMAL(10, 2),
    is_virtual BOOLEAN DEFAULT FALSE,
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS feature_flags (
    id INT AUTO_INCREMENT PRIMARY KEY,
    flag_name VARCHAR(50) UNIQUE NOT NULL,
    enabled BOOLEAN DEFAULT FALSE,
    rollout_percentage INT DEFAULT 0,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- 3. Insert default feature flags
INSERT IGNORE INTO feature_flags (flag_name, enabled, description) VALUES
    ('location_services', FALSE, 'Enable location-based features'),
    ('passport_mode', FALSE, 'Enable virtual location mode'),
    ('real_time_notifications', FALSE, 'Enable RabbitMQ notifications'),
    ('advanced_analytics', FALSE, 'Enable analytics dashboard');

-- 4. Add columns to existing tables ONLY if they don't exist
DELIMITER //
CREATE PROCEDURE AddColumnsSafely()
BEGIN
    IF NOT EXISTS (SELECT * FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = 'penzi_dating_db' AND TABLE_NAME = 'users' AND COLUMN_NAME = 'last_location_update') THEN
        ALTER TABLE users ADD COLUMN last_location_update TIMESTAMP NULL;
    END IF;
    
    IF NOT EXISTS (SELECT * FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = 'penzi_dating_db' AND TABLE_NAME = 'users' AND COLUMN_NAME = 'is_passport_active') THEN
        ALTER TABLE users ADD COLUMN is_passport_active BOOLEAN DEFAULT FALSE;
    END IF;
    
    IF NOT EXISTS (SELECT * FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = 'penzi_dating_db' AND TABLE_NAME = 'users' AND COLUMN_NAME = 'preferred_radius') THEN
        ALTER TABLE users ADD COLUMN preferred_radius INT DEFAULT 50;
    END IF;
END //
DELIMITER ;

CALL AddColumnsSafely();
DROP PROCEDURE AddColumnsSafely;
