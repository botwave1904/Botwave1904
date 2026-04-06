import sqlite3

def create_tenants_table(conn):
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tenants (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL UNIQUE
        )
    ''')
    conn.commit()

def insert_initial_tenant(conn):
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tenants WHERE name = 'JPS Inc.'")
    if not cursor.fetchone():
        cursor.execute("INSERT INTO tenants (id, name) VALUES (?, ?)", (1, 'JPS Inc.'))
    conn.commit()

def create_customers_table(conn):
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY,
            tenant_id INTEGER DEFAULT 1,
            name TEXT NOT NULL,
            phone TEXT,
            email TEXT
        )
    ''')
    conn.commit()

def create_jobs_table(conn):
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY,
            tenant_id INTEGER DEFAULT 1,
            customer_id INTEGER,
            description TEXT,
            status TEXT
        )
    ''')
    conn.commit()

def create_invoices_table(conn):
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS invoices (
            id INTEGER PRIMARY KEY,
            tenant_id INTEGER DEFAULT 1,
            job_id INTEGER,
            amount REAL,
            status TEXT
        )
    ''')
    conn.commit()

def main():
    conn = sqlite3.connect('src/core/botwave.db')
    
    # Create tenants table and insert initial tenant
    create_tenants_table(conn)
    insert_initial_tenant(conn)
    
    # Create other tables
    create_customers_table(conn)
    create_jobs_table(conn)
    create_invoices_table(conn)
    
    conn.close()

if __name__ == '__main__':
    main()
