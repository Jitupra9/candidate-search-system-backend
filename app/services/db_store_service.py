# Replaces json_store.py — same interface, Postgres backend

async def update_document_status(db, document_id: str, status: str, error: str = None):
    doc = await db.query(Document).filter_by(document_id=document_id).first()
    doc.status = status
    if error:
        doc.error_message = error
    if status == "done":
        doc.processed_at = datetime.utcnow()
    await db.commit()

async def update_candidate_status(db, candidate_id: str, status: str, error: str = None):
    # same pattern
    ...

async def save_chat(db, chat_data: dict):
    record = ChatHistory(**chat_data)
    db.add(record)
    await db.commit()