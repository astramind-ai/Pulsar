-- Create user if not exists
DO
$$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'astramind') THEN
    CREATE USER astramind WITH PASSWORD '';
  END IF;
END
$$;

-- Create database if not exists
DO
$$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_database WHERE datname = 'pulsar') THEN
    CREATE DATABASE pulsar;
  END IF;
END
$$;

-- Grant privileges on the database
GRANT ALL PRIVILEGES ON DATABASE pulsar TO astramind;