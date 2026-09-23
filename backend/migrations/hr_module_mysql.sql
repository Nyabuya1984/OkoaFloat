-- Okoa Float HR module schema for MySQL / DBeaver CE
-- Run this in the target MySQL database before enabling the HR features.

CREATE TABLE IF NOT EXISTS hr_employee_profiles (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    user_id BIGINT UNSIGNED NOT NULL,
    employee_code VARCHAR(50) NOT NULL,
    national_id VARCHAR(30) NULL,
    work_email VARCHAR(150) NULL,
    phone_number VARCHAR(30) NULL,
    department VARCHAR(120) NULL,
    job_title VARCHAR(120) NULL,
    employment_type ENUM('full_time', 'part_time', 'contract', 'intern') NOT NULL DEFAULT 'full_time',
    hire_date DATE NULL,
    status ENUM('active', 'on_leave', 'inactive', 'terminated') NOT NULL DEFAULT 'active',
    emergency_contact_name VARCHAR(120) NULL,
    emergency_contact_phone VARCHAR(30) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_hr_employee_code (employee_code),
    UNIQUE KEY uq_hr_user_id (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS hr_assets (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    employee_id BIGINT UNSIGNED NULL,
    asset_type ENUM('laptop', 'phone', 'tablet', 'accessory', 'other') NOT NULL,
    asset_name VARCHAR(120) NOT NULL,
    serial_number VARCHAR(120) NULL,
    assigned_to VARCHAR(120) NULL,
    assigned_date DATE NULL,
    status ENUM('assigned', 'available', 'returned', 'damaged', 'lost') NOT NULL DEFAULT 'assigned',
    notes TEXT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_hr_assets_employee (employee_id),
    KEY idx_hr_assets_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS hr_recruitment_jobs (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    title VARCHAR(150) NOT NULL,
    department VARCHAR(120) NOT NULL,
    employment_type ENUM('full_time', 'part_time', 'contract', 'intern') NOT NULL DEFAULT 'full_time',
    location VARCHAR(120) NULL,
    hiring_manager VARCHAR(120) NULL,
    status ENUM('draft', 'open', 'closed', 'filled') NOT NULL DEFAULT 'draft',
    description TEXT NULL,
    requirements TEXT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS hr_candidates (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    job_id BIGINT UNSIGNED NOT NULL,
    full_name VARCHAR(150) NOT NULL,
    email VARCHAR(150) NOT NULL,
    phone_number VARCHAR(30) NULL,
    application_stage ENUM('applied', 'screening', 'interview', 'offer', 'hired', 'rejected') NOT NULL DEFAULT 'applied',
    cv_url VARCHAR(255) NULL,
    notes TEXT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_hr_candidates_job (job_id),
    KEY idx_hr_candidates_stage (application_stage)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS hr_shifts (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    employee_id BIGINT UNSIGNED NOT NULL,
    shift_date DATE NOT NULL,
    shift_start TIME NOT NULL,
    shift_end TIME NOT NULL,
    location VARCHAR(120) NULL,
    status ENUM('scheduled', 'clocked_in', 'completed', 'cancelled') NOT NULL DEFAULT 'scheduled',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_hr_shifts_employee (employee_id),
    KEY idx_hr_shifts_date (shift_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS hr_performance_reviews (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    employee_id BIGINT UNSIGNED NOT NULL,
    review_cycle VARCHAR(50) NOT NULL,
    reviewer_name VARCHAR(120) NULL,
    rating DECIMAL(3,2) NOT NULL DEFAULT 0.00,
    summary TEXT NULL,
    goals TEXT NULL,
    status ENUM('draft', 'in_review', 'approved', 'rejected') NOT NULL DEFAULT 'draft',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_hr_reviews_employee (employee_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS hr_leave_policies (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    policy_name VARCHAR(120) NOT NULL,
    leave_code VARCHAR(30) NOT NULL,
    default_days SMALLINT UNSIGNED NOT NULL DEFAULT 21,
    is_paid TINYINT(1) NOT NULL DEFAULT 1,
    description TEXT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_hr_leave_code (leave_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Optional indexes to support efficient lookups by employee and status.
ALTER TABLE hr_employee_profiles
    ADD CONSTRAINT fk_hr_employee_user
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;

ALTER TABLE hr_assets
    ADD CONSTRAINT fk_hr_assets_employee
    FOREIGN KEY (employee_id) REFERENCES hr_employee_profiles(id) ON DELETE SET NULL;

ALTER TABLE hr_shifts
    ADD CONSTRAINT fk_hr_shift_employee
    FOREIGN KEY (employee_id) REFERENCES hr_employee_profiles(id) ON DELETE CASCADE;

ALTER TABLE hr_performance_reviews
    ADD CONSTRAINT fk_hr_review_employee
    FOREIGN KEY (employee_id) REFERENCES hr_employee_profiles(id) ON DELETE CASCADE;
