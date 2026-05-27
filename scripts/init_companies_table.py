from ar_db_handler import init_filings_db, sync_companies

conn = init_filings_db("data/filings.db")
result = sync_companies(conn, country_code="US")

print(result)  # SyncResult(period=..., upserted=..., delisted=..., country_code='US')
