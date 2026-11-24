# backend/fast_seed.py
import random
from datetime import datetime, timedelta
import psycopg2
from psycopg2.extras import execute_values
from faker import Faker

from src.utils.config import settings

def main():
    print("Connecting to RDS...")
    conn = psycopg2.connect(settings.DATABASE_URL)
    cur = conn.cursor()
    fake = Faker('en_IN')
    random.seed(42)

    # 1. Transactions (10,000 rows via fast execute_values)
    print("Inserting 10,000 transactions...")
    transactions = []
    for i in range(10000):
        cid = f'CUST_{random.randint(1000,1999)}'
        amount = random.choice([499, 999, 1499, 1999, 2499, 4999])
        transactions.append((
            f'TXN_{i+8000}', cid, amount,
            random.choice(['subscription', 'one_time', 'upgrade', 'addon']),
            random.choice(['completed'] * 90 + ['failed'] * 7 + ['refunded'] * 3),
            fake.date_time_between('-12m', 'now'),
            f'REF_{fake.hexify(text="^^^^^^^^^^")}'
        ))

    # Add duplicate charge test cases
    now = datetime.now()
    transactions.append(('TXN_DUP_001', 'CUST_1000', 1499, 'subscription', 'duplicate', now - timedelta(days=10), 'REF_DUP_A'))
    transactions.append(('TXN_DUP_002', 'CUST_1000', 1499, 'subscription', 'completed', now - timedelta(days=10), 'REF_DUP_B'))
    transactions.append(('TXN_DUP_003', 'CUST_1001', 999, 'subscription', 'duplicate', now - timedelta(days=5), 'REF_DUP_C'))
    transactions.append(('TXN_DUP_004', 'CUST_1001', 999, 'subscription', 'completed', now - timedelta(days=5), 'REF_DUP_D'))

    execute_values(
        cur,
        "INSERT INTO transactions (txn_id, customer_id, amount, type, status, date, reference) VALUES %s ON CONFLICT DO NOTHING;",
        transactions,
        page_size=2000
    )
    conn.commit()
    cur.execute("SELECT count(*) FROM transactions;")
    print(f"Transactions in DB: {cur.fetchone()[0]:,}")

    # 2. Tickets (5,000 rows via fast execute_values)
    print("Inserting 5,000 tickets...")
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

    execute_values(
        cur,
        "INSERT INTO tickets (ticket_id, customer_id, issue_type, description, status, priority, created_at, resolved_at, resolution_summary, csat_score, escalated) VALUES %s ON CONFLICT DO NOTHING;",
        tickets,
        page_size=2000
    )
    conn.commit()
    cur.execute("SELECT count(*) FROM tickets;")
    print(f"Tickets in DB: {cur.fetchone()[0]:,}")

    print("ALL DATA SEEDING COMPLETE!")
    conn.close()

if __name__ == "__main__":
    main()
