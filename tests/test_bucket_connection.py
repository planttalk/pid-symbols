"""Manual connectivity helper for the Google Cloud Storage bucket."""

from __future__ import annotations

from google.api_core import exceptions
from google.cloud import storage


def test_bucket_connection(bucket_name: str) -> None:
    """Use ADC credentials to read metadata for *bucket_name*."""

    try:
        storage_client = storage.Client()
        bucket = storage_client.get_bucket(bucket_name)
    except exceptions.NotFound:
        print("Error: the bucket is not found.")
    except exceptions.Forbidden:
        print("Error: access denied for the provided credentials.")
    except Exception as exc:
        print(f"Error: {exc}")
    else:
        # Surface a few bucket attributes for manual verification.
        print(f"Connected to bucket: {bucket.name}")
        print(f"Location: {bucket.location}")
        print(f"Storage class: {bucket.storage_class}")


if __name__ == "__main__":
    test_bucket_connection("pid_automation_labs")
