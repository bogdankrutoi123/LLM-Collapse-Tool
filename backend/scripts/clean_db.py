"""
Cleans the database: removes all data except the admin user(s).
Run via:
    docker compose exec backend python scripts/clean_db.py
"""
import os
import sys

# allow running from repo root or from backend/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://llm_user:llm_password@db:5432/llm_detector",
)

TRUNCATE_SQL = """
TRUNCATE
    collapse_events,
    notifications,
    audit_logs,
    alert_rule_items,
    alert_rules,
    alert_thresholds,
    aggregated_metrics,
    benchmark_jobs,
    evaluation_items,
    evaluation_jobs,
    prompt_set_items,
    prompt_sets,
    prompt_metrics,
    prompts,
    model_versions,
    models,
    system_settings
RESTART IDENTITY CASCADE;
"""

DELETE_NON_ADMIN_SQL = "DELETE FROM users WHERE role != 'ADMIN'::userrole;"

LIST_ADMINS_SQL = "SELECT id, username, role FROM users WHERE role = 'ADMIN'::userrole;"


def main():
    engine = create_engine(DATABASE_URL)
    with engine.begin() as conn:
        print("Truncating all tables...")
        conn.execute(text(TRUNCATE_SQL))

        print("Removing non-admin users...")
        result = conn.execute(text(DELETE_NON_ADMIN_SQL))
        print(f"  Deleted {result.rowcount} non-admin user(s).")

        admins = conn.execute(text(LIST_ADMINS_SQL)).fetchall()
        if admins:
            print("Remaining admin accounts:")
            for row in admins:
                print(f"  id={row[0]}  username={row[1]}  role={row[2]}")
        else:
            print("WARNING: no admin users found — create one via create_admin.py or POST /api/v1/auth/bootstrap-admin.")

    print("Done.")


if __name__ == "__main__":
    main()
