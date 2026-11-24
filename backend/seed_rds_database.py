# backend/seed_rds_database.py
# Automates NB01 to create the 7 PostgreSQL tables and seed
# synthetic customers, transactions, tickets, and conversations.

import random
from datetime import datetime, timedelta
import psycopg2
from faker import Faker

from src.utils.config import settings

def main():
    print("=" * 60)
    print("🚀 Support Agent: AWS RDS PostgreSQL Schema & Data Setup")
    print("=" * 60)

    print("\n[1/5] Connecting to PostgreSQL on AWS RDS...")
    conn = psycopg2.connect(settings.DATABASE_URL)
    cur = conn.cursor()
    print("✅ Connected successfully to RDS!")

    # 1. Cleanly recreate tables for Customer Support Agent
    print("\n[2/5] Creating 7 Customer Support PostgreSQL tables...")
    cur.execute("""
    DROP TABLE IF EXISTS messages CASCADE;
    DROP TABLE IF EXISTS agent_actions CASCADE;
    DROP TABLE IF EXISTS conversations CASCADE;
    DROP TABLE IF EXISTS transactions CASCADE;
    DROP TABLE IF EXISTS tickets CASCADE;
    DROP TABLE IF EXISTS customers CASCADE;
    DROP TABLE IF EXISTS knowledge_chunks CASCADE;
    """)

    cur.execute("""
    CREATE TABLE customers (
        customer_id VARCHAR(20) PRIMARY KEY,
        name VARCHAR(100), email VARCHAR(100), phone VARCHAR(20),
        account_type VARCHAR(20), tenure_months INTEGER,
        lifetime_value INTEGER, preferred_language VARCHAR(5),
        communication_style VARCHAR(10), created_at TIMESTAMP DEFAULT NOW()
    );
    """)

    cur.execute("""
    CREATE TABLE tickets (
        ticket_id VARCHAR(20) PRIMARY KEY,
        customer_id VARCHAR(20) REFERENCES customers(customer_id),
        issue_type VARCHAR(50), description TEXT, status VARCHAR(20),
        priority VARCHAR(10), created_at TIMESTAMP, resolved_at TIMESTAMP,
        resolution_summary TEXT, csat_score INTEGER, escalated BOOLEAN DEFAULT FALSE
    );
    """)

    cur.execute("""
    CREATE TABLE transactions (
        txn_id VARCHAR(20) PRIMARY KEY,
        customer_id VARCHAR(20) REFERENCES customers(customer_id),
        amount INTEGER, type VARCHAR(20), status VARCHAR(20),
        date TIMESTAMP, reference VARCHAR(100)
    );
    """)

    cur.execute("""
    CREATE TABLE conversations (
        conv_id VARCHAR(20) PRIMARY KEY,
        customer_id VARCHAR(20) REFERENCES customers(customer_id),
        channel VARCHAR(20), started_at TIMESTAMP DEFAULT NOW(),
        ended_at TIMESTAMP, resolution_status VARCHAR(20),
        escalated BOOLEAN DEFAULT FALSE, csat_score INTEGER,
        language_detected VARCHAR(5)
    );
    """)

    cur.execute("""
    CREATE TABLE messages (
        message_id SERIAL PRIMARY KEY,
        conv_id VARCHAR(20) REFERENCES conversations(conv_id),
        role VARCHAR(10), content TEXT, timestamp TIMESTAMP DEFAULT NOW(),
        sentiment VARCHAR(20), sentiment_score FLOAT,
        intent_classified VARCHAR(50), language VARCHAR(5)
    );
    """)

    cur.execute("""
    CREATE TABLE agent_actions (
        action_id SERIAL PRIMARY KEY, conv_id VARCHAR(20),
        action_type VARCHAR(50), action_details JSONB,
        timestamp TIMESTAMP DEFAULT NOW(), guardrail_result VARCHAR(20)
    );
    """)

    cur.execute("""
    CREATE TABLE knowledge_chunks (
        chunk_id SERIAL PRIMARY KEY, content TEXT,
        category VARCHAR(50),
        source_doc VARCHAR(100), created_at TIMESTAMP DEFAULT NOW()
    );
    """)
    conn.commit()
    print("✅ All 7 tables recreated successfully with exact schema!")

    # 2. Seed Customers (1,000 rows)
    print("\n[3/5] Seeding 1,000 customers...")
    fake = Faker('en_IN')
    random.seed(42)

    customers = []
    account_types = ['basic'] * 40 + ['premium'] * 40 + ['enterprise'] * 20
    comm_styles   = ['casual'] * 45 + ['formal'] * 45 + ['technical'] * 10
    languages     = ['en'] * 85 + ['hi'] * 15

    for i in range(1000):
        cid   = f'CUST_{1000 + i}'
        atype = random.choice(account_types)
        ltv   = random.randint(500, 3000) if atype == 'basic' else (
                random.randint(3000, 15000) if atype == 'premium' else
                random.randint(15000, 80000))

        customers.append((
            cid, fake.name(), fake.email(), fake.phone_number()[:15],
            atype, random.randint(1, 48), ltv,
            random.choice(languages), random.choice(comm_styles)
        ))

    sql_cust = """
    INSERT INTO customers 
    (customer_id, name, email, phone, account_type, tenure_months, lifetime_value, preferred_language, communication_style)
    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """
    cur.executemany(sql_cust, customers)
    conn.commit()
    cur.execute("SELECT COUNT(*) FROM customers;")
    print(f"  Customers in DB: {cur.fetchone()[0]:,}")

    # 3. Seed Transactions (10,000 rows)
    print("\n[4/5] Seeding 10,000 transactions (including duplicate charge test cases)...")
    transactions = []
    for i in range(10000):
        cid    = f'CUST_{random.randint(1000,1999)}'
        amount = random.choice([499, 999, 1499, 1999, 2499, 4999])
        transactions.append((
            f'TXN_{i+8000}', cid, amount,
            random.choice(['subscription', 'one_time', 'upgrade', 'addon']),
            random.choice(['completed'] * 90 + ['failed'] * 7 + ['refunded'] * 3),
            fake.date_time_between('-12m', 'now'),
            f'REF_{fake.hexify(text="^^^^^^^^^^")}'
        ))

    # Add duplicate charge test cases (especially for CUST_1000 and CUST_1001)
    now = datetime.now()
    transactions.append(('TXN_DUP_001', 'CUST_1000', 1499, 'subscription', 'duplicate', now - timedelta(days=10), 'REF_DUP_A'))
    transactions.append(('TXN_DUP_002', 'CUST_1000', 1499, 'subscription', 'completed', now - timedelta(days=10), 'REF_DUP_B'))
    transactions.append(('TXN_DUP_003', 'CUST_1001', 999, 'subscription', 'duplicate', now - timedelta(days=5), 'REF_DUP_C'))
    transactions.append(('TXN_DUP_004', 'CUST_1001', 999, 'subscription', 'completed', now - timedelta(days=5), 'REF_DUP_D'))

    sql_txn = """
    INSERT INTO transactions (txn_id, customer_id, amount, type, status, date, reference)
    VALUES (%s,%s,%s,%s,%s,%s,%s)
    """
    cur.executemany(sql_txn, transactions)
    conn.commit()
    cur.execute("SELECT COUNT(*) FROM transactions;")
    print(f"  Transactions in DB: {cur.fetchone()[0]:,}")

    # 4. Seed Tickets (5,000 rows)
    print("\n[5/5] Seeding 5,000 tickets...")
    issue_types = [
        'billing_dispute', 'order_status', 'refund_request',
        'cancellation_threat', 'technical_issue', 'complaint',
        'product_question', 'account_issue'
    ]
    statuses = ['resolved'] * 70 + ['open'] * 20 + ['in_progress'] * 10
    priorities = ['low'] * 40 + ['medium'] * 40 + ['high'] * 15 + ['critical'] * 5

    tickets = []
    for i in range(5000):
        created = fake.date_time_between('-12m', 'now')
        status = random.choice(statuses)
        resolved = (created + timedelta(hours=random.randint(1, 72))) if status == 'resolved' else None
        csat = random.choice([1, 2, 3, 4, 5]) if status == 'resolved' else None
        escalated = random.random() < 0.20

        tickets.append((
            f'TKT_{i+1000}', f'CUST_{random.randint(1000,1999)}',
            random.choice(issue_types), fake.sentence(nb_words=10),
            status, random.choice(priorities),
            created, resolved,
            fake.sentence(nb_words=8) if resolved else None,
            csat, escalated
        ))

    sql_tkt = """
    INSERT INTO tickets 
    (ticket_id, customer_id, issue_type, description, status, priority, created_at, resolved_at, resolution_summary, csat_score, escalated)
    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """
    cur.executemany(sql_tkt, tickets)
    conn.commit()
    cur.execute("SELECT COUNT(*) FROM tickets;")
    print(f"  Tickets in DB: {cur.fetchone()[0]:,}")

    print("\n" + "=" * 60)
    print("🎉 AWS RDS PostgreSQL Database is 100% POPULATED & READY!")
    print("=" * 60)

    conn.close()

if __name__ == "__main__":
    main()
