from celery import shared_task


@shared_task(name="process_example")
def process_example(example_id: int) -> dict:
    """Example async task that processes an example record."""
    # Placeholder — replace with real logic
    return {"example_id": example_id, "status": "processed"}
