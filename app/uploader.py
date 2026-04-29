"""
PDF配信URL発行：Google Cloud Storage

認証：ADC（Cloud Run自動 / ローカルは impersonate-service-account）
- バケット: GCS_BUCKET（デフォルト furulead-speed-reports）
- 配信URL: 7日間有効の署名付きURL

GDriveではなくGCSを使う理由: 個人Googleアカウント配下のSAはDrive容量を持たないため。
GCSはプロジェクト課金で容量制限なし。
"""
from __future__ import annotations
import os
import logging
from datetime import timedelta, datetime

log = logging.getLogger("uploader")

DEFAULT_BUCKET = os.environ.get("GCS_BUCKET", "furulead-speed-reports")
PROJECT_ID = os.environ.get("GCP_PROJECT", "furulead-speed-bot")
SIGNED_URL_TTL_DAYS = 7


_gcs = None


def _gcs_client():
    global _gcs
    if _gcs is None:
        from google.cloud import storage as gcs
        _gcs = gcs.Client(project=PROJECT_ID)
    return _gcs


def upload(pdf_path: str) -> str:
    """PDFをGCSにアップロード→署名付き公開URLを返す"""
    from google.cloud import storage  # noqa
    client = _gcs_client()
    bucket = client.bucket(DEFAULT_BUCKET)

    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    blob_name = f"reports/{ts}_{os.path.basename(pdf_path)}"
    blob = bucket.blob(blob_name)

    blob.upload_from_filename(pdf_path, content_type="application/pdf")

    # 署名付きURL（7日間有効）
    # Cloud RunのメタデータSAでもSignBlob APIで発行可能
    try:
        url = blob.generate_signed_url(
            version="v4",
            expiration=timedelta(days=SIGNED_URL_TTL_DAYS),
            method="GET",
        )
    except Exception as e:
        # SignBlob API失敗時の代替：公開リンクに切替
        log.warning(f"[uploader] signed URL発行失敗: {e}。公開URLにフォールバック")
        blob.make_public()
        url = blob.public_url

    log.info(f"[uploader] GCS uploaded: {url}")
    return url
