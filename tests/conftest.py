import os

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://kweli:kweli@127.0.0.1:5432/kweli_test")
os.environ.setdefault("CORS_ORIGINS", '["http://localhost:5173"]')
os.environ.setdefault("COOKIE_SECURE", "false")
os.environ.setdefault("PAYPAL_ENV", "sandbox")
